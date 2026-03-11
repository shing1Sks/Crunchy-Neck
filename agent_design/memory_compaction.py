"""
memory_compaction.py — rolling-window context compaction for the Crunchy Neck agent loop.

Trigger logic (from Compaction.md):
    COMPACT_THRESHOLD = threshold_ratio * max_context_tokens
    if current_tokens >= COMPACT_THRESHOLD:
        compacted_state = run_compaction(full_history)
        new_history = [compacted_state, second_to_last, last]

Two compaction levels:
    "orchestrator" — summarises the orchestrator agent's full task state.
    "computer"     — summarises a computer/desktop-browsing subagent's session state.

The compaction call is made via OpenAI (GPT-5.2). The openai package is imported
lazily inside run_compaction so this module is importable even if openai is absent.

Usage in the agent loop:
    from agent_design.memory_compaction import maybe_compact

    messages, result = maybe_compact(messages, api_key=os.environ["OPENAI_API_KEY"])
    if result.status == "error":
        print(f"[compaction error] {result.error_message}", file=sys.stderr)
    elif result.status == "done":
        print(f"[compacted] {result.messages_before} → {result.messages_after} msgs")
"""

from __future__ import annotations

import json
import tiktoken
from dataclasses import dataclass, field
from typing import Literal, Union

_TIKTOKEN_ENC = tiktoken.get_encoding("cl100k_base")

# ── Constants ──────────────────────────────────────────────────────────────────

COMPACTION_MODEL: str = "gpt-5.2"
MAX_CONTEXT_TOKENS: int = 400_000        # GPT-5.2 context window
DEFAULT_THRESHOLD_RATIO: float = 0.90    # trigger at 90% capacity
DEFAULT_KEEP_LAST_N: int = 2
CHARS_PER_TOKEN: int = 4                 # heuristic fallback when tiktoken absent
COMPACTION_MAX_TOKENS: int = 4096        # max tokens for the compaction response

# ── Config ─────────────────────────────────────────────────────────────────────

@dataclass
class CompactionConfig:
    max_context_tokens: int = MAX_CONTEXT_TOKENS
    threshold_ratio: float = DEFAULT_THRESHOLD_RATIO   # 0.90 → 90%
    keep_last_n: int = DEFAULT_KEEP_LAST_N
    model: str = COMPACTION_MODEL
    compaction_max_tokens: int = COMPACTION_MAX_TOKENS


# ── Result types (discriminated union, matching project conventions) ────────────

CompactionErrorCode = Literal[
    "API_ERROR",
    "DEPENDENCY_MISSING",
    "EMPTY_HISTORY",
    "INTERNAL",
]

CompactionLevel = Literal["orchestrator", "computer"]


@dataclass(kw_only=True)
class CompactionResultSkipped:
    status: Literal["skipped"] = "skipped"
    estimated_tokens: int = 0
    threshold_tokens: int = 0


@dataclass(kw_only=True)
class CompactionResultDone:
    status: Literal["done"] = "done"
    estimated_tokens_before: int = 0
    messages_before: int = 0
    messages_after: int = 0
    compacted_text_preview: str = ""    # first 120 chars of compacted block


@dataclass(kw_only=True)
class CompactionResultError:
    status: Literal["error"] = "error"
    error_code: CompactionErrorCode = "INTERNAL"
    error_message: str = ""


CompactionResult = Union[
    CompactionResultSkipped,
    CompactionResultDone,
    CompactionResultError,
]


# ── Compaction prompts ─────────────────────────────────────────────────────────

ORCHESTRATOR_COMPACTION_PROMPT: str = """\
You are a context compaction engine for an orchestrator AI agent called Crunchy Neck.
Extract the complete operational state from the conversation below.
Output ONLY the structured block. No preamble. No explanation.

---

## ORIGINAL TASK
<User's exact request, verbatim>

## CURRENT PLAN
<Active plan with step numbers. Mark completed steps [x], active step [→], pending [ ]>

## TODO / CHECKLIST
<Any checklists being tracked, same marking convention>

## PROGRESS SUMMARY
<3-5 sentences: what's been done, what approach was taken, key decisions made>

## DELEGATIONS LOG
<What was handed off to which subagent, with the exact instruction given and the result returned.
Format:
- [codex | browser | computer | other] → "exact instruction" → result / status>

## CRITICAL VALUES
<Every key, ID, token, URL, file path, env var, config value that appeared.
When in doubt — include it. Format: key: value>

## SUBAGENT STATES
<If any subagent is mid-task, capture its current state here:
- what it was doing
- where it got to
- what it still needs to do>

## ERRORS & DEAD ENDS
<Failures, retries, abandoned approaches — and why>

## NEXT STEP
<Exact next action. Be specific. If delegating, say to whom and with what instruction.>

## OPEN QUESTIONS
<Unresolved uncertainties or things needing user input>

PRIORITIZE recent context over older history. The agent needs to know
what it was doing, not just what was discussed.
"""

COMPUTER_COMPACTION_PROMPT: str = """\
You are a context compaction engine for a computer-browsing subagent.
This subagent navigates the computer desktop: opening files, apps, browser tabs,
system UI, and interacting with GUI elements — not just web pages.
Extract the complete session state so the subagent can resume without prior messages.
Output ONLY the structured block. No preamble. No explanation.

---

## BROWSING OBJECTIVE
<What the subagent was asked to find or do, verbatim>

## CURRENT LOCATION
<Exact URL if in a browser, or app name + file path / window title if on the desktop>

## SESSION STATE
<Login status, open apps, active windows, clipboard contents, any auth tokens seen>

## CRITICAL VALUES
<All URLs, file paths, app names, IDs, form values, API keys, extracted data — anything found.
Format: key: value. If it appeared on screen — include it.>

## NAVIGATION HISTORY (compressed)
<Bullet list of locations visited / actions taken and what was found or done at each.
Keep it tight — just enough to understand the path taken.>

## DATA COLLECTED SO FAR
<Structured dump of all meaningful extracted data — tables as tables, JSON as JSON>

## ERRORS & DEAD ENDS
<Pages that failed, dialogs that blocked, CAPTCHAs, redirects that went nowhere,
approaches abandoned and why>

## NEXT ACTION
<Exact next step: URL to navigate to, app to open, button to click, or command to run>

PRIORITIZE recent context over older history. The agent needs to know
what it was doing, not just what was discussed.
"""

_COMPACTION_PROMPTS: dict[str, str] = {
    "orchestrator": ORCHESTRATOR_COMPACTION_PROMPT,
    "computer": COMPUTER_COMPACTION_PROMPT,
}


# ── Private helpers ────────────────────────────────────────────────────────────

def _extract_text(content: str | list | None) -> str:
    """Flatten message content to a plain string."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type", "text")
        if btype == "text":
            parts.append(block.get("text", ""))
        elif btype == "tool_use":
            parts.append(block.get("name", ""))
            parts.append(json.dumps(block.get("input", {})))
        elif btype == "tool_result":
            parts.append(_extract_text(block.get("content", "")))
    return " ".join(parts)


def _serialize_history(messages: list[dict]) -> str:
    """
    Render a messages list as a readable transcript for the compaction call.

    Format:
        [ROLE]
        <content text>
        ---

    Tool-use blocks:
        [ASSISTANT — tool_use: <name>]
        <JSON input>
        ---

    Tool-result blocks:
        [TOOL RESULT: <tool_use_id>]
        <content text>
        ---
    """
    lines: list[str] = []
    for msg in messages:
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")
        if isinstance(content, str):
            lines.append(f"[{role}]\n{content}\n---")
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type", "text")
                if btype == "text":
                    lines.append(f"[{role}]\n{block.get('text', '')}\n---")
                elif btype == "tool_use":
                    input_str = json.dumps(block.get("input", {}), indent=2)
                    lines.append(
                        f"[ASSISTANT — tool_use: {block.get('name', '')}]\n"
                        f"{input_str}\n---"
                    )
                elif btype == "tool_result":
                    inner = _extract_text(block.get("content", ""))
                    lines.append(
                        f"[TOOL RESULT: {block.get('tool_use_id', '')}]\n"
                        f"{inner}\n---"
                    )
    return "\n\n".join(lines)


# ── Public API ─────────────────────────────────────────────────────────────────

def estimate_tokens(messages: list[dict]) -> int:
    """
    Count tokens for a message list using tiktoken (cl100k_base).

    Falls back to char-count / 4 only if the encode call fails for an
    unexpected reason (e.g. surrogate characters). tiktoken is a required
    dependency and is imported at module level.
    """
    full_text = " ".join(_extract_text(msg.get("content", "")) for msg in messages)
    try:
        return len(_TIKTOKEN_ENC.encode(full_text))
    except Exception:
        return max(1, len(full_text) // CHARS_PER_TOKEN)


def should_compact(
    messages: list[dict],
    config: CompactionConfig = CompactionConfig(),
) -> tuple[bool, int, int]:
    """
    Return (needs_compact, estimated_tokens, threshold_tokens).

    Separating the raw numbers lets the caller log them without re-estimating.
    """
    estimated = estimate_tokens(messages)
    threshold = int(config.max_context_tokens * config.threshold_ratio)
    return estimated >= threshold, estimated, threshold


def run_compaction(
    messages: list[dict],
    *,
    api_key: str,
    level: CompactionLevel = "orchestrator",
    config: CompactionConfig = CompactionConfig(),
) -> str:
    """
    Call OpenAI with the full conversation history and a compaction prompt.
    Returns the raw compacted state string.

    Raises:
        ImportError   — openai package not installed
        RuntimeError  — API call failed
    """
    try:
        import openai
    except ImportError:
        raise ImportError(
            "openai package is not installed. Run: pip install openai"
        )

    if not messages:
        raise ValueError("Cannot compact an empty message list.")

    history_text = _serialize_history(messages)
    compaction_prompt = _COMPACTION_PROMPTS[level]

    client = openai.OpenAI(api_key=api_key)
    try:
        response = client.chat.completions.create(
            model=config.model,
            max_completion_tokens=config.compaction_max_tokens,
            reasoning_effort="low",
            messages=[
                {"role": "system", "content": compaction_prompt},
                {
                    "role": "user",
                    "content": (
                        "Here is the full conversation history to compact:\n\n"
                        + history_text
                    ),
                },
            ],
        )
    except Exception as exc:
        raise RuntimeError(f"Compaction API call failed: {exc}") from exc

    return response.choices[0].message.content


def apply_compaction(
    messages: list[dict],
    compacted_text: str,
    config: CompactionConfig = CompactionConfig(),
) -> list[dict]:
    """
    Rebuild the message list after compaction:

        [compacted_state_msg, *bridge?, *tail]

    The compacted block is inserted as role="user" with a marker prefix.
    Tail = the last keep_last_n messages from the original list.

    Turn-alternation fix: if the first tail message is also role="user",
    a minimal bridge assistant message is inserted between the compacted
    block and the tail so the API's strict user/assistant alternation holds.
    """
    MARKER = "[COMPACTED CONVERSATION STATE — history floor, not a user message]\n\n"
    compacted_msg: dict = {
        "role": "user",
        "content": MARKER + compacted_text,
    }

    keep = config.keep_last_n
    tail = messages[-keep:] if len(messages) >= keep else list(messages)

    new_messages: list[dict] = [compacted_msg]

    if tail and tail[0].get("role") == "user":
        new_messages.append({
            "role": "assistant",
            "content": "[Context restored from compacted state.]",
        })

    new_messages.extend(tail)
    return new_messages


def maybe_compact(
    messages: list[dict],
    *,
    api_key: str,
    level: CompactionLevel = "orchestrator",
    config: CompactionConfig = CompactionConfig(),
) -> tuple[list[dict], CompactionResult]:
    """
    Main entry point for the agent loop.

    Checks whether compaction is needed. If yes, runs compaction and returns
    the rebuilt message list. On any failure, returns the original list unchanged.

    Returns:
        (messages, result) where result is one of:
            CompactionResultSkipped  — threshold not crossed, nothing changed
            CompactionResultDone     — compaction ran and message list was rebuilt
            CompactionResultError    — something went wrong, original list returned

    Typical usage:
        messages, result = maybe_compact(messages, api_key=os.environ["OPENAI_API_KEY"])
        if result.status == "error":
            log(result.error_message)
        elif result.status == "done":
            log(f"compacted {result.messages_before} → {result.messages_after} msgs")
    """
    if not messages:
        return messages, CompactionResultError(
            error_code="EMPTY_HISTORY",
            error_message="Cannot compact an empty message list.",
        )

    needs_compact, estimated_tokens, threshold_tokens = should_compact(messages, config)

    if not needs_compact:
        return messages, CompactionResultSkipped(
            estimated_tokens=estimated_tokens,
            threshold_tokens=threshold_tokens,
        )

    try:
        compacted_text = run_compaction(
            messages,
            api_key=api_key,
            level=level,
            config=config,
        )
    except ImportError as exc:
        return messages, CompactionResultError(
            error_code="DEPENDENCY_MISSING",
            error_message=str(exc),
        )
    except RuntimeError as exc:
        return messages, CompactionResultError(
            error_code="API_ERROR",
            error_message=str(exc),
        )
    except Exception as exc:
        return messages, CompactionResultError(
            error_code="INTERNAL",
            error_message=f"Unexpected error during compaction: {exc}",
        )

    new_messages = apply_compaction(messages, compacted_text, config)

    return new_messages, CompactionResultDone(
        estimated_tokens_before=estimated_tokens,
        messages_before=len(messages),
        messages_after=len(new_messages),
        compacted_text_preview=(
            compacted_text[:120] + "..."
            if len(compacted_text) > 120
            else compacted_text
        ),
    )
