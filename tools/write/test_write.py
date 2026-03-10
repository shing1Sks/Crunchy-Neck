"""
test_write.py — 16 test cases for the write tool.

Run from the workspace root:
    python -m tools.write.test_write

Or directly from inside tools/write/:
    python test_write.py
"""
from __future__ import annotations

import json
import os
import sys

# Allow `python test_write.py` from inside tools/write/
if __name__ == "__main__" and __package__ is None:
    _workspace = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    )
    if _workspace not in sys.path:
        sys.path.insert(0, _workspace)
    __package__ = "tools.write"
import tempfile
from pathlib import Path

from .write_tool import write_command
from .write_types import WriteParams, WriteResultDone, WriteResultError

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
    def run(path: str, content: str, **kwargs):
        params = WriteParams(path=path, content=content, **kwargs)
        return write_command(params, workspace_root=workspace, agent_session_id="test_session")
    return run


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def main() -> None:
    with tempfile.TemporaryDirectory(
        prefix="crunchy_write_test_", ignore_cleanup_errors=True
    ) as workspace:
        run = make_runner(workspace)
        ws = Path(workspace)

        # ── 1. Smoke — new file ───────────────────────────────────────────
        section("1. Smoke — write a new file")
        r = run("hello.txt", "hello\nworld\n")
        check("status=done", r.status == "done")
        check("created=True", isinstance(r, WriteResultDone) and r.created is True)
        check("overwritten=False", isinstance(r, WriteResultDone) and r.overwritten is False)
        check("bytes_written correct",
              isinstance(r, WriteResultDone) and r.bytes_written == len("hello\nworld\n".encode("utf-8")))
        check("file on disk matches", (ws / "hello.txt").read_bytes() == b"hello\nworld\n")

        # ── 2. Overwrite existing file ────────────────────────────────────
        section("2. Overwrite — existing file")
        r = run("hello.txt", "new content\n")
        check("status=done", r.status == "done")
        check("created=False", isinstance(r, WriteResultDone) and r.created is False)
        check("overwritten=True", isinstance(r, WriteResultDone) and r.overwritten is True)
        check("file updated", (ws / "hello.txt").read_bytes() == b"new content\n")

        # ── 3. FILE_EXISTS — overwrite=False ──────────────────────────────
        section("3. FILE_EXISTS — overwrite=False on existing file")
        r = run("hello.txt", "should not write", overwrite=False)
        check("status=error", r.status == "error")
        check("error_code=FILE_EXISTS",
              isinstance(r, WriteResultError) and r.error_code == "FILE_EXISTS")
        check("file unchanged", (ws / "hello.txt").read_bytes() == b"new content\n")

        # ── 4. BLOCKED_PATH — traversal ───────────────────────────────────
        section("4. BLOCKED_PATH — ../ traversal")
        r = run("../../evil.txt", "pwned")
        check("status=error", r.status == "error")
        check("error_code=BLOCKED_PATH",
              isinstance(r, WriteResultError) and r.error_code == "BLOCKED_PATH")

        # ── 5. BLOCKED_PATH — .env write target ───────────────────────────
        section("5. BLOCKED_PATH — .env file target")
        r = run(".env", "SECRET=abc")
        check("status=error", r.status == "error")
        check("error_code=BLOCKED_PATH",
              isinstance(r, WriteResultError) and r.error_code == "BLOCKED_PATH")

        # ── 6. SIZE_LIMIT_EXCEEDED ────────────────────────────────────────
        section("6. SIZE_LIMIT_EXCEEDED — content too large")
        big = "x" * 1025
        r = run("big.txt", big, max_bytes=1024)
        check("status=error", r.status == "error")
        check("error_code=SIZE_LIMIT_EXCEEDED",
              isinstance(r, WriteResultError) and r.error_code == "SIZE_LIMIT_EXCEEDED")

        # ── 7. create_parents=True ────────────────────────────────────────
        section("7. create_parents=True — nested dirs auto-created")
        r = run("a/b/c/nested.txt", "deep\n")
        check("status=done", r.status == "done")
        check("nested file exists", (ws / "a" / "b" / "c" / "nested.txt").exists())
        check("content correct", (ws / "a" / "b" / "c" / "nested.txt").read_bytes() == b"deep\n")

        # ── 8. PARENT_NOT_FOUND — create_parents=False ────────────────────
        section("8. PARENT_NOT_FOUND — create_parents=False, missing parent")
        r = run("x/y/z/file.txt", "hello", create_parents=False)
        check("status=error", r.status == "error")
        check("error_code=PARENT_NOT_FOUND",
              isinstance(r, WriteResultError) and r.error_code == "PARENT_NOT_FOUND")

        # ── 9. Atomic write — no temp file left ───────────────────────────
        section("9. Atomic write — no temp file left after write")
        r = run("atomic.txt", "atomic content\n", atomic=True)
        check("status=done", r.status == "done")
        check("atomic=True in result", isinstance(r, WriteResultDone) and r.atomic is True)
        tmp_files = list(ws.glob(".~atomic.txt.*.tmp"))
        check("no temp file left", len(tmp_files) == 0)
        check("content correct", (ws / "atomic.txt").read_bytes() == b"atomic content\n")

        # ── 10. Non-atomic write ──────────────────────────────────────────
        section("10. Non-atomic write — content correct")
        r = run("direct.txt", "direct content\n", atomic=False)
        check("status=done", r.status == "done")
        check("atomic=False in result", isinstance(r, WriteResultDone) and r.atomic is False)
        check("content correct", (ws / "direct.txt").read_bytes() == b"direct content\n")

        # ── 11. UTF-8 Unicode round-trip ──────────────────────────────────
        section("11. UTF-8 Unicode round-trip")
        content = "Hello, \u4e16\u754c! Ello\u2019 Mundo!\n"  # CJK + curly apostrophe
        r = run("unicode.txt", content)
        check("status=done", r.status == "done")
        check("bytes_written matches",
              isinstance(r, WriteResultDone) and r.bytes_written == len(content.encode("utf-8")))
        check("file content round-trips",
              (ws / "unicode.txt").read_bytes().decode("utf-8") == content)

        # ── 12. ENCODING_ERROR — surrogate characters ─────────────────────
        section("12. ENCODING_ERROR — content not encodable in utf-8")
        # \udcff is an unpaired surrogate — cannot be encoded in utf-8.
        bad_content = "hello \udcff world"
        r = run("bad.txt", bad_content)
        check("status=error", r.status == "error")
        check("error_code=ENCODING_ERROR",
              isinstance(r, WriteResultError) and r.error_code == "ENCODING_ERROR")

        # ── 13. lines_written count ───────────────────────────────────────
        section("13. lines_written — 'a\\nb\\nc' -> 3 lines")
        r = run("lines.txt", "a\nb\nc")
        check("status=done", r.status == "done")
        check("lines_written=3", isinstance(r, WriteResultDone) and r.lines_written == 3)

        # ── 14. Empty content ─────────────────────────────────────────────
        section("14. Empty content — bytes_written=0")
        r = run("empty.txt", "")
        check("status=done", r.status == "done")
        check("bytes_written=0", isinstance(r, WriteResultDone) and r.bytes_written == 0)
        check("lines_written=0", isinstance(r, WriteResultDone) and r.lines_written == 0)
        check("file exists and empty", (ws / "empty.txt").read_bytes() == b"")

        # ── 15. Audit log ─────────────────────────────────────────────────
        section("15. Audit log — write.start + write.done events")
        audit_dir = ws / ".agent" / "audit"
        audit_files = list(audit_dir.glob("file-ops-*.jsonl")) if audit_dir.exists() else []
        check("audit file exists", len(audit_files) > 0)
        if audit_files:
            lines = audit_files[0].read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(l)["event"] for l in lines if l.strip()]
            check("write.start event present", "write.start" in events)
            check("write.done event present", "write.done" in events)

        # ── 16. Atomic overwrite correctness ─────────────────────────────
        section("16. Atomic overwrite — file content correct after replace")
        original = "original line\n" * 100
        updated = "updated line\n" * 100
        run("replace_me.txt", original)
        r = run("replace_me.txt", updated, atomic=True)
        check("status=done", r.status == "done")
        check("file content is updated",
              (ws / "replace_me.txt").read_bytes() == updated.encode("utf-8"))
        check("original content gone",
              (ws / "replace_me.txt").read_bytes() != original.encode("utf-8"))

    # ── Summary ───────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = sum(1 for _, ok, _ in _results if not ok)
    print(f"  Results: {passed} passed, {failed} failed out of {len(_results)} checks")
    print(f"{'=' * 60}\n")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
