"""
test_edit.py — 17 test cases for the edit tool.

Run from the workspace root:
    python -m tools.edit.test_edit

Or directly from inside tools/edit/:
    python test_edit.py
"""
from __future__ import annotations

import json
import os
import sys

# Allow `python test_edit.py` from inside tools/edit/
if __name__ == "__main__" and __package__ is None:
    _workspace = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    )
    if _workspace not in sys.path:
        sys.path.insert(0, _workspace)
    __package__ = "tools.edit"
import tempfile
from pathlib import Path

from .edit_tool import edit_command
from .edit_types import EditParams, EditResultDone, EditResultError

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
    def run(path: str, old: str, new: str, **kwargs):
        params = EditParams(path=path, old=old, new=new, **kwargs)
        return edit_command(params, workspace_root=workspace, agent_session_id="test_session")
    return run


def write_file(ws: Path, name: str, content: str) -> Path:
    p = ws / name
    p.write_bytes(content.encode("utf-8"))
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def main() -> None:
    with tempfile.TemporaryDirectory(
        prefix="crunchy_edit_test_", ignore_cleanup_errors=True
    ) as workspace:
        run = make_runner(workspace)
        ws = Path(workspace)

        # ── 1. Smoke — single replacement ────────────────────────────────
        section("1. Smoke — single replacement")
        write_file(ws, "greet.txt", "hello world\n")
        r = run("greet.txt", "world", "Python")
        check("status=done", r.status == "done")
        check("replacements_made=1", isinstance(r, EditResultDone) and r.replacements_made == 1)
        check("file content correct",
              (ws / "greet.txt").read_bytes() == b"hello Python\n")

        # ── 2. OLD_NOT_FOUND ──────────────────────────────────────────────
        section("2. OLD_NOT_FOUND — string not in file")
        write_file(ws, "a.txt", "hello\n")
        r = run("a.txt", "xyz", "abc")
        check("status=error", r.status == "error")
        check("error_code=OLD_NOT_FOUND",
              isinstance(r, EditResultError) and r.error_code == "OLD_NOT_FOUND")

        # ── 3. OLD_AMBIGUOUS — duplicate old, allow_multiple=False ────────
        section("3. OLD_AMBIGUOUS — duplicate match, allow_multiple=False")
        write_file(ws, "dup.txt", "foo foo\n")
        r = run("dup.txt", "foo", "bar", allow_multiple=False)
        check("status=error", r.status == "error")
        check("error_code=OLD_AMBIGUOUS",
              isinstance(r, EditResultError) and r.error_code == "OLD_AMBIGUOUS")
        check("count in message",
              isinstance(r, EditResultError) and "2" in r.error_message)

        # ── 4. allow_multiple=True — replaces all occurrences ─────────────
        section("4. allow_multiple=True — replaces all")
        write_file(ws, "dup2.txt", "foo foo foo\n")
        r = run("dup2.txt", "foo", "bar", allow_multiple=True)
        check("status=done", r.status == "done")
        check("replacements_made=3",
              isinstance(r, EditResultDone) and r.replacements_made == 3)
        check("file content correct",
              (ws / "dup2.txt").read_bytes() == b"bar bar bar\n")

        # ── 5. Delete via empty new ───────────────────────────────────────
        section("5. Delete via empty new string")
        write_file(ws, "del.txt", "hello world\n")
        r = run("del.txt", " world", "")
        check("status=done", r.status == "done")
        check("file content correct",
              (ws / "del.txt").read_bytes() == b"hello\n")

        # ── 6. Multi-line old string ──────────────────────────────────────
        section("6. Multi-line old string")
        write_file(ws, "multi.txt", "line1\nline2\nline3\n")
        r = run("multi.txt", "line1\nline2", "replaced")
        check("status=done", r.status == "done")
        check("file content correct",
              (ws / "multi.txt").read_bytes() == b"replaced\nline3\n")

        # ── 7. dry_run=True — file unchanged ─────────────────────────────
        section("7. dry_run=True — file not modified")
        write_file(ws, "dry.txt", "original content\n")
        r = run("dry.txt", "original", "changed", dry_run=True)
        check("status=done", r.status == "done")
        check("dry_run=True in result",
              isinstance(r, EditResultDone) and r.dry_run is True)
        check("file unchanged",
              (ws / "dry.txt").read_bytes() == b"original content\n")

        # ── 8. diff_preview populated ─────────────────────────────────────
        section("8. diff_preview always populated")
        write_file(ws, "diff.txt", "before\n")
        r = run("diff.txt", "before", "after")
        check("status=done", r.status == "done")
        check("diff_preview not None",
              isinstance(r, EditResultDone) and r.diff_preview is not None)
        check("diff has --- header",
              isinstance(r, EditResultDone) and r.diff_preview is not None
              and "---" in r.diff_preview)
        check("diff has +after line",
              isinstance(r, EditResultDone) and r.diff_preview is not None
              and "+after" in r.diff_preview)

        # ── 9. lines_added / lines_removed ───────────────────────────────
        section("9. lines_added / lines_removed stats")
        write_file(ws, "stats.txt", "one line\n")
        r = run("stats.txt", "one line", "line a\nline b\nline c")
        check("status=done", r.status == "done")
        check("lines_added=3", isinstance(r, EditResultDone) and r.lines_added == 3)
        check("lines_removed=1", isinstance(r, EditResultDone) and r.lines_removed == 1)

        # ── 10. BLOCKED_PATH — traversal ──────────────────────────────────
        section("10. BLOCKED_PATH — ../ traversal")
        r = run("../../etc/hosts", "old", "new")
        check("status=error", r.status == "error")
        check("error_code=BLOCKED_PATH",
              isinstance(r, EditResultError) and r.error_code == "BLOCKED_PATH")

        # ── 11. NOT_FOUND ─────────────────────────────────────────────────
        section("11. NOT_FOUND — non-existent file")
        r = run("no_such.txt", "old", "new")
        check("status=error", r.status == "error")
        check("error_code=NOT_FOUND",
              isinstance(r, EditResultError) and r.error_code == "NOT_FOUND")

        # ── 12. IS_DIRECTORY ──────────────────────────────────────────────
        section("12. IS_DIRECTORY")
        (ws / "adir").mkdir(exist_ok=True)
        r = run("adir", "old", "new")
        check("status=error", r.status == "error")
        check("error_code=IS_DIRECTORY",
              isinstance(r, EditResultError) and r.error_code == "IS_DIRECTORY")

        # ── 13. ENCODING_ERROR — invalid encoding name ────────────────────
        section("13. ENCODING_ERROR — unknown encoding name")
        write_file(ws, "enc.txt", "hello\n")
        r = run("enc.txt", "hello", "world", encoding="utf-99")
        check("status=error", r.status == "error")
        check("error_code=ENCODING_ERROR",
              isinstance(r, EditResultError) and r.error_code == "ENCODING_ERROR")

        # ── 14. Atomic write — content correct after edit ─────────────────
        section("14. Atomic write — content correct")
        write_file(ws, "atom.txt", "alpha beta\n")
        r = run("atom.txt", "alpha", "ALPHA", atomic=True)
        check("status=done", r.status == "done")
        check("content correct",
              (ws / "atom.txt").read_bytes() == b"ALPHA beta\n")
        tmp_files = list(ws.glob(".~atom.txt.*.tmp"))
        check("no temp file left", len(tmp_files) == 0)

        # ── 15. Unicode preserved through edit ───────────────────────────
        section("15. Unicode preserved — UTF-8 file stays valid after edit")
        uni_content = "Hello, \u4e16\u754c!\nGoodbye, \u4e16\u754c!\n"
        write_file(ws, "uni.txt", uni_content)
        r = run("uni.txt", "Hello", "Hi")
        check("status=done", r.status == "done")
        on_disk = (ws / "uni.txt").read_bytes().decode("utf-8")
        check("file is valid UTF-8 after edit", True)  # read_bytes().decode() would have raised
        check("content correct", on_disk == uni_content.replace("Hello", "Hi"))

        # ── 16. Audit — edit.start + edit.done ───────────────────────────
        section("16. Audit log — edit.start + edit.done events")
        audit_dir = ws / ".agent" / "audit"
        audit_files = list(audit_dir.glob("file-ops-*.jsonl")) if audit_dir.exists() else []
        check("audit file exists", len(audit_files) > 0)
        if audit_files:
            lines = audit_files[0].read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(l)["event"] for l in lines if l.strip()]
            check("edit.start event present", "edit.start" in events)
            check("edit.done event present", "edit.done" in events)

        # ── 17. Audit — dry_run emits edit.dry_run ───────────────────────
        section("17. Audit — dry_run emits edit.dry_run (not edit.done)")
        write_file(ws, "dryaudit.txt", "ping\n")
        run("dryaudit.txt", "ping", "pong", dry_run=True)
        audit_files = list(audit_dir.glob("file-ops-*.jsonl")) if audit_dir.exists() else []
        if audit_files:
            lines = audit_files[0].read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(l)["event"] for l in lines if l.strip()]
            check("edit.dry_run event present", "edit.dry_run" in events)

    # ── Summary ───────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = sum(1 for _, ok, _ in _results if not ok)
    print(f"  Results: {passed} passed, {failed} failed out of {len(_results)} checks")
    print(f"{'=' * 60}\n")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
