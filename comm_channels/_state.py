"""Persistent state for the comm_channels Telegram medium.

State file: {workspace_root}/.agent/comm/telegram_state.json

Currently tracked:
  last_update_message_id : int | None  — message_id of the most recent
                                          update-type message sent to the
                                          channel; used for in-place editing.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

_lock = threading.Lock()


def _state_path(workspace_root: str) -> Path:
    p = Path(workspace_root) / ".agent" / "comm" / "telegram_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_state(workspace_root: str) -> dict[str, Any]:
    """Return the persisted state dict, or {} on missing / corrupt file."""
    p = _state_path(workspace_root)
    if not p.exists():
        return {}
    with _lock:
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}


def save_state(workspace_root: str, state: dict[str, Any]) -> None:
    """Overwrite the state file with *state*."""
    p = _state_path(workspace_root)
    with _lock:
        p.write_text(json.dumps(state, indent=2), encoding="utf-8")
