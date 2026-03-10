"""Structured audit log writer.

Writes one JSON object per line (JSONL) to:
  {workspace_root}/.agent/audit/exec-{YYYY-MM-DD}.jsonl

Appended continuously — never fully parsed, just streamed.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from .safety import redact_command_for_log

_lock = threading.Lock()


def _audit_path(workspace_root: str) -> Path:
    date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    path = Path(workspace_root) / ".agent" / "audit" / f"exec-{date_str}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def log_event(
    *,
    event: str,
    session_id: str,
    agent_session_id: str,
    command: str,
    intent: str,
    cwd: str,
    shell: str,
    workspace_root: str,
    exit_code: int | None = None,
    duration_ms: int | None = None,
    killed_by: str | None = None,
    blocked_reason: str | None = None,
    env_keys_provided: list[str] | None = None,
    sensitive_keys_redacted: list[str] | None = None,
    background: bool = False,
) -> None:
    record = {
        "event": event,
        "session_id": session_id,
        "agent_session_id": agent_session_id,
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "command": redact_command_for_log(command),
        "intent": intent,
        "cwd": cwd,
        "shell": shell,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "killed_by": killed_by,
        "blocked_reason": blocked_reason,
        "env_keys_provided": env_keys_provided or [],
        "sensitive_keys_redacted": sensitive_keys_redacted or [],
        "background": background,
    }

    path = _audit_path(workspace_root)
    line = json.dumps(record, ensure_ascii=False)

    with _lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
