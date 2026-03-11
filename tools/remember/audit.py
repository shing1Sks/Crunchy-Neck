from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_lock = threading.Lock()


def _audit_path(workspace_root: str) -> Path:
    date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    p = Path(workspace_root) / ".agent" / "audit" / f"memory-{date_str}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def log_event(
    *,
    event: str,
    action: str,
    agent_session_id: str,
    workspace_root: str,
    memory_id: str | None = None,
    content_preview: str | None = None,
    query: str | None = None,
    n_results: int | None = None,
    hits_returned: int | None = None,
    tags: list[str] | None = None,
    error_code: str | None = None,
    **extra: Any,
) -> None:
    record: dict[str, Any] = {
        "event": event,
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "agent_session_id": agent_session_id,
        "action": action,
        "memory_id": memory_id,
        "content_preview": content_preview,
        "query": query,
        "n_results": n_results,
        "hits_returned": hits_returned,
        "tags": tags,
        "error_code": error_code,
    }
    record.update(extra)
    # Drop None values to keep records tidy.
    record = {k: v for k, v in record.items() if v is not None}

    line = json.dumps(record, ensure_ascii=False) + "\n"
    audit_file = _audit_path(workspace_root)

    with _lock:
        with audit_file.open("a", encoding="utf-8") as fh:
            fh.write(line)
