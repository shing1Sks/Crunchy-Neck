"""
session_wrapup_log.py — end-of-session memory writer for the Crunchy agent.

Runs once at session end. Makes a single LLM call to summarise the session,
then prepends the new entry to MEMORY.md and merges any ONGOING THREADS updates.

Public API:

    run_session_wrapup_log(messages, *, api_key, workspace_root, today, config)
        → SessionWrapupResult

Usage in the agent loop (at session end):

    from agent_design.session_wrapup_log import run_session_wrapup_log
    from datetime import date

    result = run_session_wrapup_log(
        messages,
        api_key=os.environ["OPENAI_API_KEY"],
        workspace_root=workspace_root,
        today=date.today().isoformat(),
    )
    if result.status == "error":
        print(f"[wrapup error] {result.error_message}", file=sys.stderr)

Standalone smoke-test (prints what it would write, does not modify MEMORY.md):

    python agent-design/session_wrapup_log.py [workspace_root]
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Union

# ---------------------------------------------------------------------------
# _serialize_history — inline copy; avoids importing memory_compaction.py
# (that module imports tiktoken at module level which may not be installed)
# ---------------------------------------------------------------------------

def _serialize_history(messages: list[dict]) -> str:
    """Render a message list as a plain-text conversation transcript."""
    import json as _json
    lines: list[str] = []
    for msg in messages:
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")
        if isinstance(content, str):
            lines.append(f"[{role}]\n{content}\n---")
        elif isinstance(content, list):
            parts: list[str] = []
            for block in content:
                btype = block.get("type", "")
                if btype == "text":
                    parts.append(block.get("text", ""))
                elif btype == "tool_use":
                    parts.append(f"tool_use: {block.get('name', '')} {_json.dumps(block.get('input', {}))}")
                elif btype == "tool_result":
                    result_content = block.get("content", "")
                    if isinstance(result_content, list):
                        result_content = " ".join(b.get("text", "") for b in result_content if isinstance(b, dict))
                    parts.append(f"TOOL RESULT: {result_content}")
            lines.append(f"[{role}]\n{chr(10).join(parts)}\n---")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SESSION_HEADING   = "### Session:"
_THREADS_HEADING   = "## Ongoing Threads"
_SESSION_LOG_HEADING = "## Session Log"

WRAPUP_MODEL: str = "gpt-5.2"
WRAPUP_MAX_TOKENS: int = 512
MAX_SESSIONS_IN_FILE: int = 60   # after this, oldest sessions fold into Long-term History


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class SessionWrapupConfig:
    model: str = WRAPUP_MODEL
    max_tokens: int = WRAPUP_MAX_TOKENS
    max_sessions_in_file: int = MAX_SESSIONS_IN_FILE


# ---------------------------------------------------------------------------
# Result types (discriminated union)
# ---------------------------------------------------------------------------

@dataclass(kw_only=True)
class SessionWrapupResultDone:
    status: Literal["done"] = "done"
    session_entry: str           # the ### Session: block that was written
    threads_updated: bool        # True if ONGOING THREADS were modified
    memory_md_path: str          # absolute path to the written MEMORY.md


@dataclass(kw_only=True)
class SessionWrapupResultError:
    status: Literal["error"] = "error"
    error_code: str
    error_message: str


SessionWrapupResult = Union[SessionWrapupResultDone, SessionWrapupResultError]


# ---------------------------------------------------------------------------
# LLM prompt
# ---------------------------------------------------------------------------

def _build_wrapup_prompt(serialised_history: str, today: str) -> str:
    return f"""\
You are summarising a completed agent session for persistent memory.

Given the conversation below, output EXACTLY this format — no prose, no explanation outside the blocks:

### Session: {today}
- Task: <what the user originally asked for, one line>
- Outcome: <completed / partial / abandoned — one line>
- Key outputs: <files created, values, URLs, decisions worth keeping — bullet list or "none">
- Carry-forward: <what the next session must know to continue — or "none">

ONGOING THREADS UPDATE:
- [KEEP] <thread name>: <updated status if changed>
- [ADD] <thread name>: <description of new ongoing work>
- [DONE] <thread name>: <mark as completed>
(omit the ONGOING THREADS UPDATE section entirely if no thread changes)

Conversation:
{serialised_history}"""


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

def _parse_wrapup_response(text: str) -> tuple[str, list[tuple[str, str, str]]]:
    """
    Split LLM output into (session_entry, thread_updates).

    session_entry  — the full "### Session: ..." block
    thread_updates — list of (action, name, detail) where action is KEEP/ADD/DONE
    """
    lines = text.strip().splitlines()

    session_lines: list[str] = []
    thread_lines: list[str] = []
    in_threads = False

    for line in lines:
        if line.strip().startswith("ONGOING THREADS UPDATE"):
            in_threads = True
            continue
        if in_threads:
            thread_lines.append(line)
        else:
            session_lines.append(line)

    session_entry = "\n".join(session_lines).strip()

    # Parse thread update lines: "- [ACTION] name: detail"
    thread_updates: list[tuple[str, str, str]] = []
    for line in thread_lines:
        stripped = line.strip()
        if not stripped.startswith("- ["):
            continue
        try:
            action_end = stripped.index("]")
            action = stripped[3:action_end].upper()  # KEEP / ADD / DONE
            rest = stripped[action_end + 1:].strip().lstrip("- ").strip()
            if ":" in rest:
                name, detail = rest.split(":", 1)
            else:
                name, detail = rest, ""
            thread_updates.append((action, name.strip(), detail.strip()))
        except (ValueError, IndexError):
            continue

    return session_entry, thread_updates


# ---------------------------------------------------------------------------
# MEMORY.md read + rebuild
# ---------------------------------------------------------------------------

def _read_memory_md(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _apply_thread_updates(
    threads_section: str, updates: list[tuple[str, str, str]]
) -> str:
    """
    Merge [ADD]/[KEEP]/[DONE] updates into the existing Ongoing Threads text.

    - DONE  → remove the thread line
    - KEEP  → update the line (or leave as-is if detail is empty)
    - ADD   → append new line
    """
    lines = threads_section.splitlines()
    header = lines[0] if lines else _THREADS_HEADING
    body_lines = lines[1:] if len(lines) > 1 else []

    for action, name, detail in updates:
        if action == "DONE":
            body_lines = [l for l in body_lines if name.lower() not in l.lower()]
        elif action == "KEEP" and detail:
            for idx, l in enumerate(body_lines):
                if name.lower() in l.lower():
                    body_lines[idx] = f"- [THREAD] {name}: {detail}"
                    break
        elif action == "ADD":
            body_lines.append(f"- [THREAD] {name}: {detail}")

    result_lines = [header] + body_lines
    return "\n".join(result_lines)


def _rebuild_memory_md(
    existing: str,
    session_entry: str,
    thread_updates: list[tuple[str, str, str]],
    max_sessions: int,
) -> tuple[str, bool]:
    """
    Insert session_entry at the top of the Session Log, merge thread updates.

    Returns (new_content, threads_updated).
    """
    lines = existing.splitlines() if existing.strip() else []

    # ── Split into sections ──────────────────────────────────────────────────
    threads_lines: list[str] = []
    session_log_header_lines: list[str] = []
    session_blocks: list[str] = []
    other_lines: list[str] = []  # lines before first known section

    i = 0
    found_threads = False
    found_session_log = False

    while i < len(lines):
        line = lines[i]

        if line.strip() == _THREADS_HEADING:
            found_threads = True
            threads_lines.append(line)
            i += 1
            while i < len(lines) and not lines[i].startswith("## "):
                threads_lines.append(lines[i])
                i += 1
            continue

        if line.strip() == _SESSION_LOG_HEADING:
            found_session_log = True
            session_log_header_lines.append(line)
            i += 1
            # collect comment lines at the top of Session Log
            while i < len(lines) and lines[i].strip().startswith("<!--"):
                session_log_header_lines.append(lines[i])
                i += 1
            # collect individual session blocks
            current_block: list[str] = []
            while i < len(lines):
                if lines[i].strip().startswith(_SESSION_HEADING):
                    if current_block:
                        session_blocks.append("\n".join(current_block).rstrip())
                    current_block = [lines[i]]
                elif lines[i].startswith("## "):
                    break
                else:
                    current_block.append(lines[i])
                i += 1
            if current_block:
                session_blocks.append("\n".join(current_block).rstrip())
            continue

        if not found_threads and not found_session_log:
            other_lines.append(line)
        i += 1

    # ── Apply thread updates ─────────────────────────────────────────────────
    threads_updated = bool(thread_updates)
    if threads_lines:
        if thread_updates:
            threads_section = _apply_thread_updates("\n".join(threads_lines), thread_updates)
            threads_lines = threads_section.splitlines()
    else:
        # Create section from scratch
        threads_lines = [_THREADS_HEADING, "<!-- Active tasks or projects spanning multiple sessions. -->"]
        if thread_updates:
            for action, name, detail in thread_updates:
                if action == "ADD":
                    threads_lines.append(f"- [THREAD] {name}: {detail}")

    if not found_threads:
        found_threads = True  # we just created it

    # ── Prepend new session entry ────────────────────────────────────────────
    session_blocks.insert(0, session_entry)

    # ── Enforce max_sessions cap: fold oldest into Long-term History ─────────
    if len(session_blocks) > max_sessions:
        overflow = session_blocks[max_sessions:]
        session_blocks = session_blocks[:max_sessions]
        # Append overflow as a collapsed long-term history note
        collapsed = "\n\n".join(overflow)
        session_blocks.append(
            "### Long-term History (auto-compacted)\n"
            + collapsed
        )

    if not session_log_header_lines:
        session_log_header_lines = [
            _SESSION_LOG_HEADING,
            "<!-- Most recent first. Older sessions are auto-compacted after "
            f"{max_sessions} entries. -->",
        ]

    # ── Reassemble ───────────────────────────────────────────────────────────
    parts: list[str] = []
    if other_lines:
        parts.append("\n".join(other_lines))
    if threads_lines:
        parts.append("\n".join(threads_lines))
    if session_log_header_lines:
        parts.append("\n".join(session_log_header_lines))
    for block in session_blocks:
        parts.append(block)

    new_content = "\n\n".join(parts).rstrip() + "\n"
    return new_content, threads_updated


# ---------------------------------------------------------------------------
# Atomic write (same pattern as tools/write/write_tool.py)
# ---------------------------------------------------------------------------

def _atomic_write(path: Path, content: str) -> None:
    tmp_path = path.parent / f".~{path.name}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        tmp_path.write_text(content, encoding="utf-8")
        os.replace(str(tmp_path), str(path))
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_session_wrapup_log(
    messages: list[dict],
    *,
    api_key: str,
    workspace_root: str,
    today: str,
    config: SessionWrapupConfig | None = None,
) -> SessionWrapupResult:
    """
    Summarise the session and write the log entry to MEMORY.md.

    Args:
        messages:        The full conversation history (list of {role, content} dicts).
        api_key:         OpenAI API key.
        workspace_root:  Workspace root — MEMORY.md is at <root>/MEMORY.md.
        today:           ISO date string e.g. "2026-03-12".
        config:          Optional SessionWrapupConfig; defaults used if None.

    Returns:
        SessionWrapupResultDone on success.
        SessionWrapupResultError on any failure; MEMORY.md is left unchanged.
    """
    cfg = config or SessionWrapupConfig()

    if not messages:
        return SessionWrapupResultError(
            error_code="EMPTY_HISTORY",
            error_message="No messages to summarise.",
        )

    # ── Serialise history ────────────────────────────────────────────────────
    try:
        serialised = _serialize_history(messages)
    except Exception as exc:
        return SessionWrapupResultError(
            error_code="INTERNAL",
            error_message=f"Failed to serialise message history: {exc}",
        )

    # ── LLM call ────────────────────────────────────────────────────────────
    try:
        import openai  # lazy import — same pattern as memory_compaction.py
    except ImportError:
        return SessionWrapupResultError(
            error_code="DEPENDENCY_MISSING",
            error_message="openai package not installed. Run: pip install openai",
        )

    prompt = _build_wrapup_prompt(serialised, today)

    try:
        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=cfg.model,
            max_completion_tokens=cfg.max_tokens,
            reasoning_effort="low",
            messages=[
                {"role": "system", "content": "You are a precise session summariser. Follow the output format exactly."},
                {"role": "user",   "content": prompt},
            ],
        )
        raw_output: str = response.choices[0].message.content or ""
    except Exception as exc:
        return SessionWrapupResultError(
            error_code="API_ERROR",
            error_message=str(exc),
        )

    # ── Parse response ───────────────────────────────────────────────────────
    session_entry, thread_updates = _parse_wrapup_response(raw_output)

    if not session_entry:
        return SessionWrapupResultError(
            error_code="INTERNAL",
            error_message="LLM returned empty session entry.",
        )

    # ── Read + rebuild MEMORY.md ─────────────────────────────────────────────
    memory_path = Path(workspace_root) / "MEMORY.md"
    existing = _read_memory_md(memory_path)

    new_content, threads_updated = _rebuild_memory_md(
        existing, session_entry, thread_updates, cfg.max_sessions_in_file
    )

    # ── Atomic write ─────────────────────────────────────────────────────────
    try:
        memory_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(memory_path, new_content)
    except Exception as exc:
        return SessionWrapupResultError(
            error_code="WRITE_FAILED",
            error_message=str(exc),
        )

    return SessionWrapupResultDone(
        session_entry=session_entry,
        threads_updated=threads_updated,
        memory_md_path=str(memory_path.resolve()),
    )


# ---------------------------------------------------------------------------
# Smoke-test entry point (dry-run: prints without writing)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    sample_messages = [
        {"role": "user",      "content": "Build me a skill scanner."},
        {"role": "assistant", "content": "Done — created agent-design/skill_use.py with 48 tests passing."},
    ]
    # Show what would be sent to the LLM
    serialised = _serialize_history(sample_messages)
    prompt = _build_wrapup_prompt(serialised, "2026-03-12")
    print("=== Wrapup prompt (dry-run) ===\n")
    print(prompt)
    print("\n=== (no MEMORY.md written in dry-run mode) ===")
