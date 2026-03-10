"""Structured audit log writer for comm_channels.

Writes one JSON object per line (JSONL) to:
  {workspace_root}/.agent/audit/ping-{YYYY-MM-DD}.jsonl
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_lock = threading.Lock()


def _audit_path(workspace_root: str) -> Path:
    date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    path = Path(workspace_root) / ".agent" / "audit" / f"ping-{date_str}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def log_event(
    *,
    event: str,
    agent_session_id: str,
    workspace_root: str,
    medium: str | None = None,
    type: str | None = None,
    status: str | None = None,
    error_code: str | None = None,
    detail: str | None = None,
    **extra: Any,
) -> None:
    record: dict[str, Any] = {
        "event": event,
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "agent_session_id": agent_session_id,
        "medium": medium,
        "type": type,
        "status": status,
        "error_code": error_code,
        "detail": detail,
    }
    record.update(extra)
    # Drop None values to keep records tidy
    record = {k: v for k, v in record.items() if v is not None}

    path = _audit_path(workspace_root)
    line = json.dumps(record, ensure_ascii=False)

    with _lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
