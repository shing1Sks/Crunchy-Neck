"""
identity_and_memory.py — identity section builder for the Crunchy agent system prompt.

Produces three combined system-prompt sections in one call:
    Section 1  — Identity (who Crunchy is)
    Section 7  — Memory Rules (how to use USER.md, MEMORY.md, and remember())
    Section 14 — Bootstrap Files (USER.md full + MEMORY.md capped extract)

Three public functions:

    load_user_md(workspace_root)                  → str
    load_memory_md_extract(workspace_root, *, max_sessions=8)  → str
    build_identity_section(workspace_root, *, agent_name="Crunchy")  → str

Usage in the system-prompt builder:

    from agent_design.identity import build_identity_section

    section = build_identity_section(workspace_root)
    # Insert at the top of the system prompt (Sections 1 + 7 + 14)

Standalone smoke-test:

    python agent-design/identity_and_memory.py [workspace_root]
"""

from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_USER_MD_BYTES: int = 32 * 1024       # 32 KB — USER.md should stay lean
MAX_MEMORY_MD_BYTES: int = 256 * 1024    # 256 KB — total file size cap for reading
DEFAULT_MAX_SESSIONS: int = 8            # how many Session Log blocks to inject

_SESSION_HEADING = "### Session:"
_THREADS_HEADING = "## Ongoing Threads"
_SESSION_LOG_HEADING = "## Session Log"

# ---------------------------------------------------------------------------
# USER.md loader
# ---------------------------------------------------------------------------

def load_user_md(workspace_root: str) -> str:
    """
    Read USER.md from the workspace root in full.

    Returns the file content, or "" if the file does not exist.
    Truncates with a warning comment if the file exceeds MAX_USER_MD_BYTES.
    """
    path = Path(workspace_root) / "USER.md"
    if not path.is_file():
        return ""

    try:
        raw = path.read_bytes()
    except OSError:
        return ""

    if len(raw) > MAX_USER_MD_BYTES:
        truncated = raw[:MAX_USER_MD_BYTES].decode("utf-8", errors="replace")
        return truncated + "\n<!-- USER.md truncated: file exceeds 32 KB -->"

    return raw.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# MEMORY.md capped-extract loader
# ---------------------------------------------------------------------------

def load_memory_md_extract(workspace_root: str, *, max_sessions: int = DEFAULT_MAX_SESSIONS) -> str:
    """
    Read a capped extract from MEMORY.md.

    Always includes:
        - The full "## Ongoing Threads" section
    Includes up to max_sessions most-recent "### Session:" blocks from "## Session Log".

    Returns "" if the file does not exist.
    """
    path = Path(workspace_root) / "MEMORY.md"
    if not path.is_file():
        return ""

    try:
        raw = path.read_bytes()
    except OSError:
        return ""

    if len(raw) > MAX_MEMORY_MD_BYTES:
        raw = raw[:MAX_MEMORY_MD_BYTES]

    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()

    threads_lines: list[str] = []
    session_blocks: list[list[str]] = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # Capture Ongoing Threads section
        if line.strip() == _THREADS_HEADING:
            threads_lines.append(line)
            i += 1
            while i < len(lines) and not lines[i].startswith("## "):
                threads_lines.append(lines[i])
                i += 1
            continue

        # Capture individual Session blocks inside Session Log
        if line.strip().startswith(_SESSION_HEADING):
            block: list[str] = [line]
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(_SESSION_HEADING) and not lines[i].startswith("## "):
                block.append(lines[i])
                i += 1
            session_blocks.append(block)
            continue

        i += 1

    # Build output
    parts: list[str] = []

    if threads_lines:
        # Strip trailing blank lines from threads section
        while threads_lines and not threads_lines[-1].strip():
            threads_lines.pop()
        parts.append("\n".join(threads_lines))

    if session_blocks:
        # Sessions are stored most-recent-first; take the first max_sessions
        kept = session_blocks[:max_sessions]
        session_text_lines = [_SESSION_LOG_HEADING, ""]
        for block in kept:
            session_text_lines.extend(block)
            session_text_lines.append("")
        parts.append("\n".join(session_text_lines).rstrip())

    return "\n\n".join(parts) if parts else ""


# ---------------------------------------------------------------------------
# System-prompt section builder
# ---------------------------------------------------------------------------

_IDENTITY_HEADER = """\
## Identity

You are {agent_name}, a personal autonomous agent built exclusively for your user.
You are not a generic assistant. You operate with full context of who your user is,
what they have been working on, and how they prefer to work.\
"""

_MEMORY_RULES = """\
## Memory Rules (mandatory)

USER.md — your knowledge of the user: identity, preferences, technical profile,
and working style. When you discover a new stable fact or preference mid-session,
call edit/write on USER.md immediately. Do not wait. A stable fact is anything
that would still be true next week.

MEMORY.md — recent session log. You do NOT write to MEMORY.md during a session.
It is updated automatically after the session ends. Use it only for high-level
orientation — what was last worked on, what threads are ongoing.

For any specific past work, values, outputs, or decisions: ALWAYS call the
remember() tool to search long-term memory. Never rely on MEMORY.md alone for
specifics — it is a summary, not a record. If the user asks about past sessions,
past files created, past decisions, or anything historical: call remember() first.\
"""

_USER_MD_MISSING = (
    "(USER.md not found — ask the user for their name and preferred working style, "
    "then create USER.md immediately using the write tool.)"
)

_MEMORY_MD_MISSING = "(No prior sessions found.)"


def build_identity_section(workspace_root: str, *, agent_name: str = "Crunchy") -> str:
    """
    Build the combined identity + memory rules + bootstrap files section.

    Returns a single string ready to be inserted at the top of the system prompt
    (covers Sections 1, 7, and 14 from Core-Agent-Design-And-Prompt.md).
    """
    user_md = load_user_md(workspace_root)
    memory_extract = load_memory_md_extract(workspace_root)

    user_block = user_md.strip() if user_md.strip() else _USER_MD_MISSING
    memory_block = memory_extract.strip() if memory_extract.strip() else _MEMORY_MD_MISSING

    return "\n\n".join([
        _IDENTITY_HEADER.format(agent_name=agent_name),
        _MEMORY_RULES,
        "## User Profile\n\n" + user_block,
        "## Recent Session Context\n\n" + memory_block,
    ])


# ---------------------------------------------------------------------------
# Smoke-test entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    print(build_identity_section(root))
