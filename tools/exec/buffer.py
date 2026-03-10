"""CircularLineBuffer — in-memory rotating line store with disk spillover.

Every exec process gets two of these (stdout / stderr).
- In-memory: last MAX_LINES lines (oldest dropped on overflow).
- Disk: every line streamed to a log file — always complete, never truncated.
"""
from __future__ import annotations

import os
import threading
from collections import deque
from pathlib import Path


MAX_LINES: int = 10_000
MAX_BYTES: int = 4 * 1024 * 1024  # 4 MB in-memory cap


class CircularLineBuffer:
    def __init__(self, log_path: Path) -> None:
        self._lock = threading.Lock()
        self._lines: deque[str] = deque(maxlen=MAX_LINES)
        self._total_lines: int = 0
        self._total_bytes: int = 0
        self._overflow_count: int = 0

        # Disk spillover — open in append+write, unbuffered line-by-line.
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_file = log_path.open("a", encoding="utf-8", buffering=1)

    # ── Write ──────────────────────────────────────────────────────────────

    def write_line(self, line: str) -> None:
        """Add one line (should NOT include trailing newline — we add it)."""
        with self._lock:
            encoded_len = len(line.encode("utf-8"))

            # Disk: always write full history.
            self._log_file.write(line + "\n")

            # Memory: track overflow.
            if len(self._lines) == MAX_LINES:
                self._overflow_count += 1

            # Enforce byte cap: drop oldest until we're under MAX_BYTES.
            while self._lines and self._total_bytes + encoded_len > MAX_BYTES:
                dropped = self._lines.popleft()
                self._total_bytes -= len(dropped.encode("utf-8"))
                self._overflow_count += 1

            self._lines.append(line)
            self._total_bytes += encoded_len
            self._total_lines += 1

    def write_chunk(self, chunk: str) -> None:
        """Split a raw output chunk into lines and write each."""
        # Keep partial last line across chunks.
        lines = chunk.split("\n")
        for line in lines[:-1]:
            self.write_line(line)
        # If chunk ends with \n, lines[-1] is "" — skip it.
        # Otherwise it's a partial line; keep it pending (caller responsibility).
        # For simplicity we flush partial lines immediately.
        if lines[-1]:
            self.write_line(lines[-1])

    # ── Read ───────────────────────────────────────────────────────────────

    def tail(self, n: int = 50, max_bytes: int = 8192) -> tuple[str, int]:
        """Return (text, line_count) for the last n lines, capped at max_bytes."""
        with self._lock:
            lines = list(self._lines)

        tail_lines = lines[-n:] if len(lines) > n else lines
        text = "\n".join(tail_lines)

        # Byte cap — trim from the front of the string if needed.
        encoded = text.encode("utf-8")
        if len(encoded) > max_bytes:
            text = encoded[-max_bytes:].decode("utf-8", errors="replace")
            # Re-align to a line boundary.
            first_newline = text.find("\n")
            if first_newline != -1:
                text = text[first_newline + 1:]

        return text, len(tail_lines)

    @property
    def total_lines(self) -> int:
        return self._total_lines

    @property
    def overflow_count(self) -> int:
        return self._overflow_count

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def close(self) -> None:
        with self._lock:
            if not self._log_file.closed:
                self._log_file.flush()
                self._log_file.close()
