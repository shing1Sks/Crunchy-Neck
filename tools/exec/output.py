"""Output post-processing: ANSI stripping and truncation."""
from __future__ import annotations

import re

# ─── ANSI stripping ───────────────────────────────────────────────────────────

# Matches CSI sequences (ESC [ ... m) and OSC sequences (ESC ] ... ST/BEL).
_ANSI_RE = re.compile(
    r"\x1b"              # ESC
    r"(?:"
    r"\[[0-9;]*[A-Za-z]"  # CSI: ESC [ ... letter  (colors, cursor movement)
    r"|"
    r"\][^\x07\x1b]*"     # OSC: ESC ] ... (until BEL or next ESC)
    r"(?:\x07|\x1b\\)"    #   terminated by BEL or ST (ESC \)
    r")"
)


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


# ─── Truncation ───────────────────────────────────────────────────────────────

MAX_RETURN_BYTES: int = 32 * 1024   # 32 KB
MAX_RETURN_LINES: int = 2_000


def truncate(
    text: str,
    session_id: str,
    stream: str = "stdout",
    log_path: str = "",
) -> tuple[str, bool, str | None]:
    """Tail-preferred truncation.

    Returns (text, was_truncated, truncation_note).
    """
    lines = text.splitlines(keepends=True)
    total_lines = len(lines)
    encoded = text.encode("utf-8")
    total_bytes = len(encoded)

    # Check if truncation is needed.
    if total_lines <= MAX_RETURN_LINES and total_bytes <= MAX_RETURN_BYTES:
        return text, False, None

    # Truncate: keep last MAX_RETURN_LINES.
    tail_lines = lines[-MAX_RETURN_LINES:]
    tail_text = "".join(tail_lines)

    # Also enforce byte cap on the tail.
    tail_encoded = tail_text.encode("utf-8")
    if len(tail_encoded) > MAX_RETURN_BYTES:
        tail_encoded = tail_encoded[-MAX_RETURN_BYTES:]
        tail_text = tail_encoded.decode("utf-8", errors="replace")
        # Re-align to line boundary.
        first_nl = tail_text.find("\n")
        if first_nl != -1:
            tail_text = tail_text[first_nl + 1:]

    kept_lines = tail_text.count("\n") + (1 if tail_text and not tail_text.endswith("\n") else 0)
    note = (
        f"Output truncated: showing last {kept_lines} lines of {total_lines} total lines "
        f"({total_bytes // 1024}KB). "
    )
    if log_path:
        note += f"Full {stream}: {log_path}"

    return tail_text, True, note
