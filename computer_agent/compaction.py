"""
compaction.py — token estimation and context compaction for Scout's Responses API input_list.

The main agent's memory_compaction.py works on Chat Completions message lists.
Scout uses the Responses API input_list which has entirely different item shapes:
computer_call action items and computer_call_output items containing base64 screenshots.
This module is fully self-contained — no imports from agent_design.

Threshold: 255k tokens — safely below the 272k GPT-5.4 pricing-doubling threshold.
"""
from __future__ import annotations

import json
import re
import tiktoken
from dataclasses import dataclass
from typing import Literal, Union

_ENC = tiktoken.get_encoding("cl100k_base")
_BASE64_RE = re.compile(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+")

COMPACT_THRESHOLD = 255_000             # tokens — stay below 272k pricing cliff
COMPACTION_MODEL  = "gpt-5.2"          # cheaper model for the compaction call
KEEP_LAST_N       = 4                  # input_list items kept verbatim after compaction
_VISION_TOKENS_PER_SCREENSHOT = 300    # flat vision token estimate per screenshot


# ─── Compaction prompt (owned here, not in agent_design) ─────────────────────

_COMPACTION_PROMPT = """\
You are a context compaction engine for Scout, a computer-browsing subagent of Crunchy Neck.
Scout navigates the desktop: opening files, apps, browser tabs, and interacting with GUI elements.
Extract the complete session state so Scout can resume without prior messages.
Output ONLY the structured block. No preamble. No explanation.

---

## BROWSING OBJECTIVE
<What Scout was asked to find or do, verbatim>

## CURRENT LOCATION
<Exact URL if in a browser, or app name + window title if on the desktop>

## SESSION STATE
<Login status, open apps, active windows, clipboard contents, any auth tokens seen>

## CRITICAL VALUES
<All URLs, file paths, app names, IDs, form values, extracted data — anything found on screen.
Format: key: value>

## NAVIGATION HISTORY (compressed)
<Bullet list of locations visited / actions taken and what was found or done at each.
Keep it tight — just enough to understand the path taken.>

## DATA COLLECTED SO FAR
<Structured dump of all meaningful extracted data>

## ERRORS & DEAD ENDS
<Pages that failed, dialogs that blocked, CAPTCHAs, redirects that went nowhere>

## NEXT ACTION
<Exact next step: URL to navigate to, app to open, button to click>

PRIORITIZE recent context. Scout needs to know what it was doing, not just what was discussed.\
"""


# ─── Result types ─────────────────────────────────────────────────────────────

@dataclass(kw_only=True)
class CompactSkipped:
    status: Literal["skipped"] = "skipped"
    estimated_tokens: int = 0


@dataclass(kw_only=True)
class CompactDone:
    status: Literal["done"] = "done"
    tokens_before: int = 0
    items_before: int = 0
    items_after: int = 0


@dataclass(kw_only=True)
class CompactError:
    status: Literal["error"] = "error"
    detail: str = ""


CompactResult = Union[CompactSkipped, CompactDone, CompactError]


# ─── Token estimation ─────────────────────────────────────────────────────────

def estimate_tokens(input_list: list[dict]) -> int:
    """
    Estimate token count for a Responses API input_list.

    Base64 image blobs are stripped before tiktoken counting. Each
    computer_call_output item contributes a flat _VISION_TOKENS_PER_SCREENSHOT
    estimate instead (naive tiktoken on base64 would overcount by ~600×).
    """
    text_parts: list[str] = []
    screenshot_count = 0

    for item in input_list:
        itype = item.get("type", item.get("role", ""))

        if itype in ("user", "assistant"):
            content = item.get("content", "")
            if isinstance(content, str):
                text_parts.append(_strip_base64(content))

        elif itype == "computer_call":
            # GA: actions[] array; fall back to legacy single "action" dict
            actions = item.get("actions") or ([item["action"]] if "action" in item else [])
            for a in actions:
                text_parts.append(json.dumps(a))

        elif itype == "computer_call_output":
            screenshot_count += 1  # base64 lives in output.image_url — skip entirely

    raw_text = " ".join(text_parts)
    try:
        text_tokens = len(_ENC.encode(raw_text))
    except Exception:
        text_tokens = max(1, len(raw_text) // 4)

    return text_tokens + screenshot_count * _VISION_TOKENS_PER_SCREENSHOT


def _strip_base64(text: str) -> str:
    return _BASE64_RE.sub("[IMAGE]", text)


# ─── Serializer ───────────────────────────────────────────────────────────────

def _serialize(input_list: list[dict]) -> str:
    """
    Render a Responses API input_list as a readable transcript for GPT-5.2.
    Base64 blobs are replaced with [SCREENSHOT] markers.
    """
    lines: list[str] = []

    for item in input_list:
        itype = item.get("type", item.get("role", ""))

        if itype == "user":
            lines.append(f"[USER]\n{item.get('content', '')}\n---")

        elif itype == "assistant":
            lines.append(f"[ASSISTANT]\n{item.get('content', '')}\n---")

        elif itype == "computer_call":
            # GA: actions[] array; fall back to legacy single "action" dict
            actions = item.get("actions") or ([item["action"]] if "action" in item else [])
            for action in actions:
                action_type = action.get("type", "unknown")
                lines.append(
                    f"[SCOUT ACTION: {action_type}]\n"
                    f"{json.dumps(action, indent=2)}\n---"
                )

        elif itype == "computer_call_output":
            lines.append("[SCREENSHOT]\n---")

    return "\n\n".join(lines)


# ─── Compaction call ──────────────────────────────────────────────────────────

def _run_compaction(input_list: list[dict], api_key: str) -> str:
    """Call GPT-5.2 with the serialized history. Returns the compacted state string."""
    try:
        import openai
    except ImportError:
        raise RuntimeError("openai package is not installed. Run: pip install openai")

    transcript = _serialize(input_list)
    client = openai.OpenAI(api_key=api_key)

    try:
        response = client.chat.completions.create(
            model=COMPACTION_MODEL,
            max_completion_tokens=4096,
            reasoning_effort="low",
            messages=[
                {"role": "system", "content": _COMPACTION_PROMPT},
                {"role": "user", "content": "Conversation history to compact:\n\n" + transcript},
            ],
        )
    except Exception as exc:
        raise RuntimeError(f"Compaction API call failed: {exc}") from exc

    return response.choices[0].message.content


# ─── Apply compaction ─────────────────────────────────────────────────────────

def _apply_compaction(input_list: list[dict], compacted_text: str) -> list[dict]:
    """
    Rebuild the input_list after compaction:
        [original_task_msg, compacted_state_msg, ...last_4_items]

    Preserving input_list[0] ensures Scout always has its original objective
    even after multiple compaction cycles.
    """
    MARKER = "[COMPACTED SESSION STATE — history floor, not a user message]\n\n"
    compacted_item: dict = {"role": "user", "content": MARKER + compacted_text}

    first = input_list[0] if input_list else compacted_item
    tail  = input_list[-KEEP_LAST_N:] if len(input_list) > KEEP_LAST_N else list(input_list)

    return [first, compacted_item, *tail]


# ─── Public API ───────────────────────────────────────────────────────────────

def maybe_compact(
    input_list: list[dict],
    *,
    api_key: str,
) -> tuple[list[dict], CompactResult]:
    """
    Check token count and compact if at or above COMPACT_THRESHOLD (255k).

    Returns (input_list, result). On any error the original list is returned unchanged.

    Usage in agent.py:
        input_list, cr = maybe_compact(input_list, api_key=api_key)
        if cr.status == "done":
            _send_update(f"[scout] compacted ({cr.items_before}→{cr.items_after} items)")
        elif cr.status == "error":
            print(f"[compaction error] {cr.detail}")
    """
    if not input_list:
        return input_list, CompactError(detail="empty input_list")

    estimated = estimate_tokens(input_list)

    if estimated < COMPACT_THRESHOLD:
        return input_list, CompactSkipped(estimated_tokens=estimated)

    try:
        compacted_text = _run_compaction(input_list, api_key)
    except Exception as exc:
        return input_list, CompactError(detail=str(exc))

    new_list = _apply_compaction(input_list, compacted_text)

    return new_list, CompactDone(
        tokens_before=estimated,
        items_before=len(input_list),
        items_after=len(new_list),
    )
