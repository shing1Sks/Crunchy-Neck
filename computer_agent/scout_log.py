"""
scout_log.py — structured per-session JSONL logger for Scout.

One log file per Scout run, written to:
    <workspace_root>/.agent/scout/logs/YYYYMMDD_<session_id>.jsonl

Each line is a JSON event record.  Events cover:
    session.start / session.end
    turn.start
    model.response          — summary of what the model returned
    action.execute          — action about to run
    action.result           — what execute_action returned
    action.error            — exception during execution
    screenshot.taken        — after each computer_call batch
    signal.detected         — DONE / FAILED / NEED_INPUT + payload
    text.output             — raw model text (first 500 chars)
    implicit_done           — model returned text without DONE prefix
    no_progress             — turn with no action and no text
    compaction.skipped      — token estimate below threshold
    compaction.done         — before/after stats
    compaction.error        — detail string

Usage:
    from computer_agent.scout_log import ScoutLog
    log = ScoutLog(workspace_root=..., agent_session_id=...)
    log.session_start(task=..., mode=..., max_turns=...)
    log.turn_start(turn=0, input_list_len=2, estimated_tokens=42)
    log.action_execute(turn=0, action={...})
    log.action_result(turn=0, desc="clicked (100, 200)")
    log.screenshot_taken(turn=0)
    log.signal_detected(turn=0, signal="DONE", payload="scraped 5 results")
    log.session_end(status="done", deliverable="...", turns_used=2)
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_lock = threading.Lock()


class ScoutLog:
    def __init__(self, *, workspace_root: str, agent_session_id: str) -> None:
        self._session_id = agent_session_id
        self._start_time = time.monotonic()

        date_str = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
        log_dir = Path(workspace_root) / ".agent" / "scout" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        # Sanitise session_id for filenames
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in agent_session_id)
        self._path = log_dir / f"{date_str}_{safe_id}.jsonl"

    # ── Public event methods ──────────────────────────────────────────────────

    def session_start(self, *, task: str, mode: str, max_turns: int) -> None:
        self._write("session.start", task=task[:300], mode=mode, max_turns=max_turns)

    def session_end(
        self,
        *,
        status: str,
        turns_used: int,
        deliverable: str | None = None,
        reason: str | None = None,
    ) -> None:
        elapsed = round(time.monotonic() - self._start_time, 2)
        self._write(
            "session.end",
            status=status,
            turns_used=turns_used,
            elapsed_s=elapsed,
            deliverable=_trim(deliverable, 500),
            reason=_trim(reason, 300),
        )

    def turn_start(self, *, turn: int, input_list_len: int, estimated_tokens: int) -> None:
        self._write(
            "turn.start",
            turn=turn,
            input_list_len=input_list_len,
            estimated_tokens=estimated_tokens,
        )

    def model_response(self, *, turn: int, item_types: list[str]) -> None:
        self._write("model.response", turn=turn, item_types=item_types)

    def text_output(self, *, turn: int, text: str) -> None:
        self._write("text.output", turn=turn, text=_trim(text, 500))

    def action_execute(self, *, turn: int, action: dict) -> None:
        # Log action but strip any large embedded data (e.g. base64)
        safe = {k: (v if not isinstance(v, str) or len(v) < 200 else v[:200] + "…")
                for k, v in action.items()}
        self._write("action.execute", turn=turn, action=safe)

    def action_result(self, *, turn: int, desc: str) -> None:
        self._write("action.result", turn=turn, desc=desc)

    def action_error(self, *, turn: int, action_type: str, error: str) -> None:
        self._write("action.error", turn=turn, action_type=action_type, error=error)

    def screenshot_taken(self, *, turn: int) -> None:
        self._write("screenshot.taken", turn=turn)

    def signal_detected(self, *, turn: int, signal: str, payload: str) -> None:
        self._write("signal.detected", turn=turn, signal=signal, payload=_trim(payload, 400))

    def implicit_done(self, *, turn: int, text: str) -> None:
        self._write(
            "implicit_done",
            turn=turn,
            note="model returned text without DONE prefix — treating as done",
            text=_trim(text, 500),
        )

    def no_progress(self, *, turn: int) -> None:
        self._write(
            "no_progress",
            turn=turn,
            note="no action executed and no text output — stopping",
        )

    def need_input_sent(self, *, turn: int, question: str) -> None:
        self._write("need_input.sent", turn=turn, question=_trim(question, 300))

    def need_input_reply(self, *, turn: int, reply: str) -> None:
        self._write("need_input.reply", turn=turn, reply=_trim(reply, 300))

    def need_input_timeout(self, *, turn: int) -> None:
        self._write("need_input.timeout", turn=turn, note="user query timed out")

    def compaction_skipped(self, *, turn: int, estimated_tokens: int) -> None:
        self._write(
            "compaction.skipped",
            turn=turn,
            estimated_tokens=estimated_tokens,
        )

    def compaction_done(
        self, *, turn: int, tokens_before: int, items_before: int, items_after: int
    ) -> None:
        self._write(
            "compaction.done",
            turn=turn,
            tokens_before=tokens_before,
            items_before=items_before,
            items_after=items_after,
        )

    def compaction_error(self, *, turn: int, detail: str) -> None:
        self._write("compaction.error", turn=turn, detail=detail)

    def api_error(self, *, turn: int, error: str) -> None:
        self._write("api.error", turn=turn, error=error)

    def chrome_launch(self, *, profile: str) -> None:
        self._write("chrome.launch", profile=profile)

    def chrome_launch_error(self, *, error: str) -> None:
        self._write("chrome.launch_error", error=error)

    # ── Internal writer ───────────────────────────────────────────────────────

    def _write(self, event: str, **fields: Any) -> None:
        record: dict[str, Any] = {
            "event": event,
            "ts": datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds"),
            "session_id": self._session_id,
        }
        record.update({k: v for k, v in fields.items() if v is not None})

        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        with _lock:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line)

    @property
    def log_path(self) -> str:
        return str(self._path)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _trim(s: str | None, n: int) -> str | None:
    if s is None:
        return None
    return s[:n] + ("…" if len(s) > n else "")
