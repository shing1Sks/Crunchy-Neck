"""
system_prompt.py — assembles the frozen system prompt for the Crunchy Neck agent.

Called once at startup; the result is passed as the system message for every
OpenAI call in the session and is never rebuilt mid-session.

Section order (mirrors Core-Agent-Design-And-Prompt.md):
    1, 7, 14  — Identity + Memory Rules + Bootstrap files  (identity_and_memory.py)
    2         — Tooling overview                            (inline)
    3         — Tool call style                             (inline)
    4         — Safety                                      (inline)
    5         — CLI Quick Reference                         (inline)
    6         — Skills                                      (skill_use.py)
    8-13      — Runtime metadata                            (inline)
    15-17     — Messaging + ping protocol                   (inline)
    personality — PERSONALITY.md verbatim
"""
from __future__ import annotations

import platform
import sys
from datetime import datetime, timezone
from pathlib import Path


def build_system_prompt(
    *,
    workspace_root: str,
    agent_name: str = "Crunchy",
    medium: str = "terminal",
    model: str = "gpt-5.2",
) -> str:
    """
    Build and return the complete frozen system prompt string.
    Sections are separated by '\\n\\n---\\n\\n' for readability.
    """
    # Import lazily so startup can finish before heavy modules load
    from agent_design.identity_and_memory import build_identity_section
    from agent_design.skill_use import build_skill_section

    sections: list[str] = [
        # 1 + 7 + 14
        build_identity_section(workspace_root, agent_name=agent_name),
        # 2
        _TOOLING_SECTION,
        # 3
        _TOOL_CALL_STYLE,
        # 4
        _SAFETY_SECTION,
        # 5
        _cli_reference(workspace_root),
        # 6
        build_skill_section(workspace_root),
        # 8-13
        _runtime_metadata(workspace_root, model, medium),
        # 15-17
        _messaging_protocol(medium),
        # personality
        _load_personality(workspace_root),
    ]

    return "\n\n---\n\n".join(s for s in sections if s.strip())


# ── Section 2 — Tooling overview ─────────────────────────────────────────────

_TOOLING_SECTION = """\
## Tools Available

exec             — run shell commands (sync or background; returns stdout/stderr)
process          — manage background processes (poll, kill, send-keys, get-log)
read             — read file contents with optional pagination
write            — create or overwrite files (atomic by default)
edit             — surgical in-place string replacement (no full rewrite needed)
remember         — semantic long-term memory (store / query / list / delete)
ping_user        — send messages or questions to the user (update / chat / query:msg / query:options)
send_user_media  — send files to the user (photo, document, video, audio)
snapshot         — capture a desktop screenshot
tts              — text-to-speech synthesis via Inworld API
image_gen        — generate images via Gemini
web_search       — search the web (built-in OpenAI tool)

Context window: 400,000 tokens. History is compacted automatically at 90% capacity."""

# ── Section 3 — Tool call style ───────────────────────────────────────────────

_TOOL_CALL_STYLE = """\
## Tool Call Style

- Narrate briefly before multi-step tool chains: "Let me check the file first."
- Do NOT narrate before every single tool call — only when it helps the user follow along.
- After a failed tool call: explain what failed, then retry with a correction.
- Never loop on the same failing call more than twice without stopping to ask the user.
- exec() requires an 'intent' field. Be specific — vague intent ("running command") is rejected."""

# ── Section 4 — Safety ────────────────────────────────────────────────────────

_SAFETY_SECTION = """\
## Safety

- Never delete files without explicit user confirmation.
- Never expose secrets in command strings — use exec()'s env dict instead.
- Never execute commands that could destroy system state unless explicitly asked.
- If a task would be irreversible, confirm first.
- You can refuse tasks that are unambiguously harmful."""

# ── Section 5 — CLI Quick Reference ──────────────────────────────────────────

def _cli_reference(workspace_root: str) -> str:
    return (
        "## CLI Quick Reference\n\n"
        f"Workspace root: {workspace_root}\n\n"
        "Key locations:\n"
        "  USER.md     — user profile and preferences (update if you learn new facts)\n"
        "  MEMORY.md   — auto-written after each session (read-only during a session)\n"
        "  skills/     — skill library; each skill in its own subdirectory with SKILL.md\n"
        "  .agent/     — runtime data: logs, memory index, tts output, images, snapshots\n"
    )

# ── Sections 8-13 — Runtime metadata ─────────────────────────────────────────

def _runtime_metadata(workspace_root: str, model: str, medium: str) -> str:
    now = datetime.now(timezone.utc)
    return (
        "## Runtime\n\n"
        f"- model: {model}\n"
        f"- workspace: {workspace_root}\n"
        f"- medium: {medium}\n"
        f"- date: {now.date().isoformat()}\n"
        f"- time_utc: {now.strftime('%H:%M')}\n"
        f"- platform: {sys.platform}\n"
        f"- os_version: {platform.version()}\n"
        f"- python: {sys.version.split()[0]}\n"
    )

# ── Sections 15-17 — Messaging + ping protocol ────────────────────────────────

def _messaging_protocol(medium: str) -> str:
    return (
        "## Messaging Protocol\n\n"
        f"Current comm medium: '{medium}'.\n\n"
        "ping_user type options:\n"
        "  update       — live status update (edits previous update in-place on Telegram)\n"
        "  chat         — one-way informational message\n"
        "  query:msg    — ask a free-text question; blocks until user replies\n"
        "  query:options — present a button choice; blocks until user selects\n\n"
        f"Always pass medium='{medium}' unless intentionally overriding.\n\n"
        "## Silent Replies\n\n"
        "When a tool call returns everything the user asked for, "
        "you may omit a final text reply. Only reply when you have something meaningful to add.\n\n"
        "## Heartbeat / Progress\n\n"
        "Before starting any long multi-step task, send a brief 'update' ping so the user "
        "knows work has started. Send another when the task is complete."
    )

# ── Personality ───────────────────────────────────────────────────────────────

def _load_personality(workspace_root: str) -> str:
    path = Path(workspace_root) / "PERSONALITY.md"
    if not path.is_file():
        return ""
    try:
        content = path.read_text(encoding="utf-8").strip()
        return "## Personality\n\n" + content
    except OSError:
        return ""
