"""ProcessSupervisor — the stateful registry for all exec'd processes.

One singleton instance is shared between exec_tool and process_tool.
"""
from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .buffer import CircularLineBuffer
from .exec_types import ProcessEntry

# GC: keep completed entries for 10 minutes after exit.
GC_RETENTION_MS: int = 10 * 60 * 1000
SESSION_CEILING_MS: int = 60 * 60 * 1000  # 1 hour absolute max per exec


@dataclass
class _LiveEntry:
    meta: ProcessEntry
    proc: subprocess.Popen | None
    stdout_buf: CircularLineBuffer
    stderr_buf: CircularLineBuffer
    session_dir: Path
    _reader_threads: list[threading.Thread] = field(default_factory=list)
    _exited_at: float | None = None   # unix timestamp when process exited


class ProcessSupervisor:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, _LiveEntry] = {}

    # ── Registration ───────────────────────────────────────────────────────

    def register(
        self,
        session_id: str,
        command: str,
        intent: str,
        cwd: str,
        shell: str,
        session_dir: Path,
    ) -> ProcessEntry:
        meta = ProcessEntry(
            session_id=session_id,
            command=command,
            intent=intent,
            cwd=cwd,
            shell=shell,
            pid=None,
            started_at=time.time(),
            state="pending",
        )
        stdout_buf = CircularLineBuffer(session_dir / "stdout.log")
        stderr_buf = CircularLineBuffer(session_dir / "stderr.log")
        entry = _LiveEntry(
            meta=meta,
            proc=None,
            stdout_buf=stdout_buf,
            stderr_buf=stderr_buf,
            session_dir=session_dir,
        )
        with self._lock:
            self._entries[session_id] = entry
        return meta

    # ── Attach spawned process ─────────────────────────────────────────────

    def attach(self, session_id: str, proc: subprocess.Popen) -> None:
        with self._lock:
            entry = self._entries[session_id]
        entry.proc = proc
        entry.meta.pid = proc.pid
        entry.meta.state = "running"

        # Start reader threads for stdout and stderr.
        t_out = threading.Thread(
            target=self._reader, args=(entry, proc.stdout, entry.stdout_buf), daemon=True
        )
        t_err = threading.Thread(
            target=self._reader, args=(entry, proc.stderr, entry.stderr_buf), daemon=True
        )
        t_out.start()
        t_err.start()
        entry._reader_threads = [t_out, t_err]

        # Start a watchdog thread to update state when process exits.
        threading.Thread(target=self._watchdog, args=(entry,), daemon=True).start()

    @staticmethod
    def _reader(
        entry: _LiveEntry,
        stream,
        buf: CircularLineBuffer,
    ) -> None:
        try:
            for raw_line in stream:
                if isinstance(raw_line, bytes):
                    line = raw_line.decode("utf-8", errors="replace").rstrip("\n\r")
                else:
                    line = raw_line.rstrip("\n\r")
                buf.write_line(line)
        except Exception:
            pass

    def _watchdog(self, entry: _LiveEntry) -> None:
        proc = entry.proc
        if proc is None:
            return

        # Enforce session ceiling.
        deadline = entry.meta.started_at + SESSION_CEILING_MS / 1000
        while True:
            ret = proc.poll()
            if ret is not None:
                # Wait for reader threads to drain.
                for t in entry._reader_threads:
                    t.join(timeout=2)
                entry.meta.exit_code = ret
                # Only transition to "done" if _kill_entry hasn't already
                # marked this entry as "killed". Without this guard the watchdog
                # races with _kill_entry and overwrites state="killed" → "done".
                if entry.meta.state != "killed":
                    entry.meta.state = "done"
                entry._exited_at = time.time()
                return
            if time.time() > deadline:
                self._kill_entry(entry, reason="session-limit")
                return
            time.sleep(0.1)

    # ── Process control ────────────────────────────────────────────────────

    def _kill_entry(self, entry: _LiveEntry, reason: str = "user") -> bool:
        """Returns True if the process was actually killed, False if it was already finished."""
        proc = entry.proc
        if proc is None or entry.meta.state in ("killed", "error", "done"):
            return False
        # Catch the race window: process exited but watchdog hasn't updated state yet.
        if proc.poll() is not None:
            return False
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        except Exception:
            pass
        # Wait for reader threads to drain so log file handles are released.
        for t in entry._reader_threads:
            t.join(timeout=2)
        entry.meta.state = "killed"
        entry.meta.killed_by = reason
        entry._exited_at = time.time()
        return True

    def kill(self, session_id: str, reason: str = "user") -> bool:
        with self._lock:
            entry = self._entries.get(session_id)
        if entry is None:
            return False
        return self._kill_entry(entry, reason=reason)

    # ── Stdin interaction ──────────────────────────────────────────────────

    def send_input(self, session_id: str, data: str, press_enter: bool = True) -> bool:
        with self._lock:
            entry = self._entries.get(session_id)
        if entry is None or entry.proc is None:
            return False
        if entry.proc.stdin is None or entry.proc.stdin.closed:
            return False
        try:
            text = data + ("\n" if press_enter else "")
            entry.proc.stdin.write(text.encode("utf-8"))
            entry.proc.stdin.flush()
            return True
        except Exception:
            return False

    def close_stdin(self, session_id: str) -> bool:
        with self._lock:
            entry = self._entries.get(session_id)
        if entry is None or entry.proc is None:
            return False
        try:
            entry.proc.stdin.close()
            return True
        except Exception:
            return False

    # ── Polling ────────────────────────────────────────────────────────────

    def poll(self, session_id: str) -> dict | None:
        with self._lock:
            entry = self._entries.get(session_id)
        if entry is None:
            return None

        tail_text, tail_lines = entry.stdout_buf.tail(n=50, max_bytes=8192)
        meta = entry.meta
        duration_ms = int((time.time() - meta.started_at) * 1000)

        return {
            "session_id": session_id,
            "state": meta.state,
            "exit_code": meta.exit_code,
            "killed_by": meta.killed_by,
            "pid": meta.pid,
            "duration_ms": duration_ms,
            "tail": tail_text,
            "tail_lines": tail_lines,
            "lines_so_far": entry.stdout_buf.total_lines,
        }

    def list_sessions(
        self, filter_state: Literal["running", "done", "killed", "all"] = "all"
    ) -> list[dict]:
        self._gc()
        with self._lock:
            entries = list(self._entries.values())

        result = []
        for e in entries:
            if filter_state != "all" and e.meta.state != filter_state:
                continue
            result.append({
                "session_id": e.meta.session_id,
                "state": e.meta.state,
                "command": e.meta.command,
                "started_at": e.meta.started_at,
                "duration_ms": int((time.time() - e.meta.started_at) * 1000),
                "exit_code": e.meta.exit_code,
            })
        return result

    # ── Log access ─────────────────────────────────────────────────────────

    def get_log(
        self,
        session_id: str,
        stream: Literal["stdout", "stderr"] = "stdout",
        offset: int = 0,
        limit: int = 32 * 1024,
    ) -> str | None:
        with self._lock:
            entry = self._entries.get(session_id)
        if entry is None:
            return None
        log_path = entry.session_dir / f"{stream}.log"
        if not log_path.exists():
            return ""
        with log_path.open("rb") as f:
            f.seek(offset)
            return f.read(limit).decode("utf-8", errors="replace")

    # ── Garbage collection ─────────────────────────────────────────────────

    def _gc(self) -> None:
        now = time.time()
        retention_s = GC_RETENTION_MS / 1000
        with self._lock:
            to_remove = [
                sid
                for sid, e in self._entries.items()
                if e._exited_at is not None and (now - e._exited_at) > retention_s
            ]
            for sid in to_remove:
                entry = self._entries.pop(sid)
                entry.stdout_buf.close()
                entry.stderr_buf.close()

    # ── Collect output for completed process ───────────────────────────────

    def collect_output(self, session_id: str) -> tuple[str, str]:
        """Return (stdout_text, stderr_text) for a completed process."""
        with self._lock:
            entry = self._entries.get(session_id)
        if entry is None:
            return "", ""
        stdout_tail, _ = entry.stdout_buf.tail(n=MAX_LINES_COLLECT, max_bytes=MAX_BYTES_COLLECT)
        stderr_tail, _ = entry.stderr_buf.tail(n=MAX_LINES_COLLECT, max_bytes=MAX_BYTES_COLLECT)
        return stdout_tail, stderr_tail


MAX_LINES_COLLECT = 2_000
MAX_BYTES_COLLECT = 32 * 1024


# ─── Singleton ────────────────────────────────────────────────────────────────

_supervisor: ProcessSupervisor | None = None
_supervisor_lock = threading.Lock()


def get_supervisor() -> ProcessSupervisor:
    global _supervisor
    with _supervisor_lock:
        if _supervisor is None:
            _supervisor = ProcessSupervisor()
    return _supervisor
