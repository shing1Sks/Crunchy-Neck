"""
test_read.py — 17 test cases for the read tool.

Run from the workspace root:
    python -m tools.read.test_read

Or directly from inside tools/read/:
    python test_read.py
"""
from __future__ import annotations

import base64
import json
import os
import sys

# Allow `python test_read.py` from inside tools/read/
if __name__ == "__main__" and __package__ is None:
    _workspace = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    )
    if _workspace not in sys.path:
        sys.path.insert(0, _workspace)
    __package__ = "tools.read"
import tempfile
from pathlib import Path

from .read_tool import read_command
from .read_types import ReadParams, ReadResultDone, ReadResultError

# ---------------------------------------------------------------------------
# Test harness helpers
# ---------------------------------------------------------------------------
_results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    _results.append((name, condition, detail))
    status = "\033[32mPASS\033[0m" if condition else "\033[31mFAIL\033[0m"
    suffix = f"  ({detail})" if detail and not condition else ""
    print(f"  [{status}] {name}{suffix}")


def section(title: str) -> None:
    print(f"\n{'-' * 60}")
    print(f"  {title}")
    print(f"{'-' * 60}")


def make_runner(workspace: str):
    def run(path: str, **kwargs) -> object:
        params = ReadParams(path=path, **kwargs)
        return read_command(params, workspace_root=workspace, agent_session_id="test_session")
    return run


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def main() -> None:
    with tempfile.TemporaryDirectory(
        prefix="crunchy_read_test_", ignore_cleanup_errors=True
    ) as workspace:
        run = make_runner(workspace)
        ws = Path(workspace)

        # ── 1. Smoke ──────────────────────────────────────────────────────
        section("1. Smoke — read a known file")
        (ws / "hello.txt").write_bytes(b"hello\nworld\n")
        r = run("hello.txt")
        check("status=done", r.status == "done")
        check("content correct", isinstance(r, ReadResultDone) and r.content == "hello\nworld\n")
        check("size_bytes > 0", isinstance(r, ReadResultDone) and r.size_bytes > 0)
        check("total_lines=2", isinstance(r, ReadResultDone) and r.total_lines == 2)
        check("lines_returned=2", isinstance(r, ReadResultDone) and r.lines_returned == 2)
        check("truncated=False", isinstance(r, ReadResultDone) and r.truncated is False)

        # ── 2. NOT_FOUND ──────────────────────────────────────────────────
        section("2. NOT_FOUND — non-existent path")
        r = run("no_such_file.txt")
        check("status=error", r.status == "error")
        check("error_code=NOT_FOUND", isinstance(r, ReadResultError) and r.error_code == "NOT_FOUND")

        # ── 3. IS_DIRECTORY ───────────────────────────────────────────────
        section("3. IS_DIRECTORY — path is a directory")
        (ws / "adir").mkdir(exist_ok=True)
        r = run("adir")
        check("status=error", r.status == "error")
        check("error_code=IS_DIRECTORY", isinstance(r, ReadResultError) and r.error_code == "IS_DIRECTORY")

        # ── 4. BLOCKED_PATH — path traversal ─────────────────────────────
        section("4. BLOCKED_PATH — ../ traversal")
        r = run("../../etc/passwd")
        check("status=error", r.status == "error")
        check("error_code=BLOCKED_PATH", isinstance(r, ReadResultError) and r.error_code == "BLOCKED_PATH")

        # ── 5. BLOCKED_PATH — symlink escaping workspace ──────────────────
        section("5. BLOCKED_PATH — symlink to outside workspace")
        outside = ws.parent / "outside_target.txt"
        outside.write_text("secret", encoding="utf-8")
        link = ws / "evil_link.txt"
        try:
            link.symlink_to(outside)
            r = run("evil_link.txt")
            check("status=error", r.status == "error")
            check("error_code=BLOCKED_PATH", isinstance(r, ReadResultError) and r.error_code == "BLOCKED_PATH")
        except (OSError, NotImplementedError):
            # Symlinks require elevated privileges on some Windows configurations.
            check("symlink test skipped (no privilege)", True, "skipped")
            check("symlink test skipped (no privilege)", True, "skipped")
        finally:
            outside.unlink(missing_ok=True)

        # ── 6. BLOCKED_PATH — .env file ───────────────────────────────────
        section("6. BLOCKED_PATH — .env file")
        (ws / ".env").write_text("SECRET=abc", encoding="utf-8")
        r = run(".env")
        check("status=error", r.status == "error")
        check("error_code=BLOCKED_PATH", isinstance(r, ReadResultError) and r.error_code == "BLOCKED_PATH")

        # ── 7. UTF-8 non-ASCII round-trip ─────────────────────────────────
        section("7. UTF-8 non-ASCII — CJK characters")
        (ws / "cjk.txt").write_bytes("こんにちは\n世界\n".encode("utf-8"))
        r = run("cjk.txt")
        check("status=done", r.status == "done")
        check("content matches", isinstance(r, ReadResultDone) and r.content == "こんにちは\n世界\n")
        check("encoding=utf-8", isinstance(r, ReadResultDone) and r.encoding == "utf-8")

        # ── 8. Latin-1 fallback ───────────────────────────────────────────
        section("8. Latin-1 fallback when UTF-8 fails")
        latin_bytes = bytes([0xE9, 0xE0, 0xFC])  # é à ü in latin-1, invalid UTF-8
        (ws / "latin.txt").write_bytes(latin_bytes)
        r = run("latin.txt", encoding="utf-8")
        check("status=done (fallback succeeded)", r.status == "done")
        check("encoding changed to latin-1", isinstance(r, ReadResultDone) and r.encoding == "latin-1")

        # ── 9. ENCODING_ERROR — invalid encoding name ─────────────────────
        section("9. ENCODING_ERROR — unknown encoding name")
        (ws / "sample.txt").write_text("hello", encoding="utf-8")
        r = run("sample.txt", encoding="utf-99")
        check("status=error", r.status == "error")
        check("error_code=ENCODING_ERROR", isinstance(r, ReadResultError) and r.error_code == "ENCODING_ERROR")

        # ── 10. Pagination — start_line + num_lines ───────────────────────
        section("10. Pagination — start_line + num_lines")
        fifty = "".join(f"line{i}\n" for i in range(50))
        (ws / "fifty.txt").write_bytes(fifty.encode("utf-8"))
        r = run("fifty.txt", start_line=10, num_lines=10)
        check("status=done", r.status == "done")
        check("lines_returned=10", isinstance(r, ReadResultDone) and r.lines_returned == 10)
        check("total_lines=50", isinstance(r, ReadResultDone) and r.total_lines == 50)
        check("first line is line10", isinstance(r, ReadResultDone) and r.content.startswith("line10\n"))

        # ── 11. Pagination — start_line past EOF ──────────────────────────
        section("11. Pagination — start_line past EOF")
        r = run("fifty.txt", start_line=1000)
        check("status=done", r.status == "done")
        check("content empty", isinstance(r, ReadResultDone) and r.content == "")
        check("lines_returned=0", isinstance(r, ReadResultDone) and r.lines_returned == 0)

        # ── 12. max_bytes truncation ──────────────────────────────────────
        section("12. max_bytes truncation")
        big = "x" * 4096
        (ws / "big.txt").write_text(big, encoding="utf-8")
        r = run("big.txt", max_bytes=512)
        check("status=done", r.status == "done")
        check("truncated=True", isinstance(r, ReadResultDone) and r.truncated is True)
        check("content <= 512 bytes", isinstance(r, ReadResultDone) and len(r.content.encode("utf-8")) <= 512)

        # ── 13. Binary — binary="error" ───────────────────────────────────
        section("13. Binary — binary='error'")
        (ws / "bin.dat").write_bytes(b"\x00\x01\x02\x03binary")
        r = run("bin.dat", binary="error")
        check("status=error", r.status == "error")
        check("error_code=BINARY_FILE", isinstance(r, ReadResultError) and r.error_code == "BINARY_FILE")

        # ── 14. Binary — binary="base64" ──────────────────────────────────
        section("14. Binary — binary='base64'")
        raw_bytes = b"\x00\x01\x02\x03binary"
        (ws / "bin2.dat").write_bytes(raw_bytes)
        r = run("bin2.dat", binary="base64")
        check("status=done", r.status == "done")
        check("encoding=base64", isinstance(r, ReadResultDone) and r.encoding == "base64")
        check("content is valid base64",
              isinstance(r, ReadResultDone) and base64.b64decode(r.content) == raw_bytes)

        # ── 15. Binary — binary="skip" ────────────────────────────────────
        section("15. Binary — binary='skip'")
        r = run("bin.dat", binary="skip")
        check("status=done", r.status == "done")
        check("content empty", isinstance(r, ReadResultDone) and r.content == "")
        check("truncated=True", isinstance(r, ReadResultDone) and r.truncated is True)

        # ── 16. Empty file ────────────────────────────────────────────────
        section("16. Empty file")
        (ws / "empty.txt").write_bytes(b"")
        r = run("empty.txt")
        check("status=done", r.status == "done")
        check("size_bytes=0", isinstance(r, ReadResultDone) and r.size_bytes == 0)
        check("total_lines=0", isinstance(r, ReadResultDone) and r.total_lines == 0)
        check("content empty", isinstance(r, ReadResultDone) and r.content == "")
        check("truncated=False", isinstance(r, ReadResultDone) and r.truncated is False)

        # ── 17. Audit log written ─────────────────────────────────────────
        section("17. Audit log — read.start + read.done events")
        audit_dir = ws / ".agent" / "audit"
        audit_files = list(audit_dir.glob("file-ops-*.jsonl")) if audit_dir.exists() else []
        check("audit file exists", len(audit_files) > 0)
        if audit_files:
            lines = audit_files[0].read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(l)["event"] for l in lines if l.strip()]
            check("read.start event present", "read.start" in events)
            check("read.done event present", "read.done" in events)

    # ── Summary ───────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = sum(1 for _, ok, _ in _results if not ok)
    print(f"  Results: {passed} passed, {failed} failed out of {len(_results)} checks")
    print(f"{'=' * 60}\n")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
