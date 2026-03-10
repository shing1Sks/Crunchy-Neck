from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..file_safety import _file_ops_audit_lock as _lock


def _audit_path(workspace_root: str) -> Path:
    date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    p = Path(workspace_root) / ".agent" / "audit" / f"file-ops-{date_str}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def log_event(
    *,
    event: str,
    path: str,
    agent_session_id: str,
    workspace_root: str,
    encoding: str | None = None,
    size_bytes: int | None = None,
    lines_returned: int | None = None,
    truncated: bool | None = None,
    error_code: str | None = None,
    blocked_reason: str | None = None,
    **extra: Any,
) -> None:
    record: dict[str, Any] = {
        "event": event,
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "agent_session_id": agent_session_id,
        "path": path,
        "encoding": encoding,
        "size_bytes": size_bytes,
        "lines_returned": lines_returned,
        "truncated": truncated,
        "error_code": error_code,
        "blocked_reason": blocked_reason,
    }
    record.update(extra)
    # Drop None values to keep records tidy.
    record = {k: v for k, v in record.items() if v is not None}

    line = json.dumps(record, ensure_ascii=False) + "\n"
    audit_file = _audit_path(workspace_root)

    with _lock:
        with audit_file.open("a", encoding="utf-8") as fh:
            fh.write(line)
