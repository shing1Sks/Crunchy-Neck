"""
test_session_wrapup_log.py — unit tests for session_wrapup_log.py

Run directly:
    python agent-design/tests/test_session_wrapup_log.py
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

# Load session_wrapup_log.py via importlib (agent-design/ has a hyphen)
_here = Path(__file__).resolve().parent.parent  # tests/ -> agent-design/
_spec = importlib.util.spec_from_file_location(
    "session_wrapup_log", _here / "session_wrapup_log.py"
)
_mod = importlib.util.module_from_spec(_spec)   # type: ignore[arg-type]
sys.modules["session_wrapup_log"] = _mod
_spec.loader.exec_module(_mod)                  # type: ignore[union-attr]

run_session_wrapup_log  = _mod.run_session_wrapup_log
SessionWrapupConfig     = _mod.SessionWrapupConfig
_parse_wrapup_response  = _mod._parse_wrapup_response
_rebuild_memory_md      = _mod._rebuild_memory_md
_apply_thread_updates   = _mod._apply_thread_updates


# ── Test harness ────────────────────────────────────────────────────────────────

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


# ── Fixtures ────────────────────────────────────────────────────────────────────

_SAMPLE_MESSAGES = [
    {"role": "user",      "content": "Build me a skill scanner."},
    {"role": "assistant", "content": "Done — created agent-design/skill_use.py."},
]

_SAMPLE_RESPONSE = """\
### Session: 2026-03-12
- Task: Build skill scanner
- Outcome: completed
- Key outputs: agent-design/skill_use.py
- Carry-forward: none

ONGOING THREADS UPDATE:
- [ADD] skill-system: scanner built and tested
- [DONE] old-thread: finished
"""

_EXISTING_MEMORY = """\
# Agent Memory

## Ongoing Threads
- [THREAD] old-thread: in progress

## Session Log
<!-- Most recent first. -->

### Session: 2026-03-11
- Task: previous task
- Outcome: completed
- Key outputs: none
- Carry-forward: none
"""


def _fake_openai(response_text: str) -> dict:
    """Return a sys.modules patch dict with a fake openai module."""
    openai_mod = types.ModuleType("openai")
    mock_response = MagicMock()
    mock_response.choices[0].message.content = response_text
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    openai_mod.OpenAI = MagicMock(return_value=mock_client)
    return {"openai": openai_mod}


# ── Tests: _parse_wrapup_response ───────────────────────────────────────────────

def test_parse_session_entry_extracted() -> None:
    section("_parse_wrapup_response — session entry extracted")
    entry, threads = _parse_wrapup_response(_SAMPLE_RESPONSE)
    check("entry starts with ### Session:", entry.startswith("### Session:"), entry[:80])
    check("entry contains Task line", "- Task:" in entry, entry[:200])
    check("entry contains Outcome", "- Outcome:" in entry, entry[:200])


def test_parse_thread_updates_extracted() -> None:
    section("_parse_wrapup_response — thread updates parsed")
    _, threads = _parse_wrapup_response(_SAMPLE_RESPONSE)
    actions = [t[0] for t in threads]
    check("ADD action parsed", "ADD" in actions, str(threads))
    check("DONE action parsed", "DONE" in actions, str(threads))
    check("ADD thread name correct", any(t[1] == "skill-system" for t in threads), str(threads))
    check("DONE thread name correct", any(t[1] == "old-thread" for t in threads), str(threads))


def test_parse_no_thread_section() -> None:
    section("_parse_wrapup_response — no ONGOING THREADS section -> empty list")
    response = "### Session: 2026-03-12\n- Task: test\n- Outcome: done\n- Key outputs: none\n- Carry-forward: none"
    entry, threads = _parse_wrapup_response(response)
    check("entry not empty", bool(entry), entry[:80])
    check("threads is empty list", threads == [], str(threads))


# ── Tests: _apply_thread_updates ───────────────────────────────────────────────

def test_apply_thread_add() -> None:
    section("_apply_thread_updates — ADD creates new thread line")
    threads_section = "## Ongoing Threads\n- [THREAD] existing: still running"
    result = _apply_thread_updates(threads_section, [("ADD", "new-thread", "just started")])
    check("new thread added", "new-thread" in result, result)
    check("existing thread kept", "existing" in result, result)


def test_apply_thread_done_removes() -> None:
    section("_apply_thread_updates — DONE removes the thread line")
    threads_section = "## Ongoing Threads\n- [THREAD] to-remove: in progress\n- [THREAD] keep: alive"
    result = _apply_thread_updates(threads_section, [("DONE", "to-remove", "finished")])
    check("thread removed", "to-remove" not in result, result)
    check("other thread kept", "keep" in result, result)


def test_apply_thread_keep_updates() -> None:
    section("_apply_thread_updates — KEEP updates existing thread detail")
    threads_section = "## Ongoing Threads\n- [THREAD] my-project: old status"
    result = _apply_thread_updates(threads_section, [("KEEP", "my-project", "new status")])
    check("new status present", "new status" in result, result)


# ── Tests: _rebuild_memory_md ───────────────────────────────────────────────────

def test_rebuild_prepends_session() -> None:
    section("_rebuild_memory_md — new session prepended (most-recent-first)")
    new_entry = "### Session: 2026-03-12\n- Task: new\n- Outcome: done\n- Key outputs: none\n- Carry-forward: none"
    new_content, _ = _rebuild_memory_md(_EXISTING_MEMORY, new_entry, [], max_sessions=10)
    idx_new = new_content.find("2026-03-12")
    idx_old = new_content.find("2026-03-11")
    check("new session before old session", idx_new < idx_old, f"new={idx_new} old={idx_old}")


def test_rebuild_from_empty_memory() -> None:
    section("_rebuild_memory_md — empty existing -> creates from scratch")
    entry = "### Session: 2026-03-12\n- Task: first\n- Outcome: done\n- Key outputs: none\n- Carry-forward: none"
    new_content, _ = _rebuild_memory_md("", entry, [], max_sessions=10)
    check("session entry present", "2026-03-12" in new_content, new_content[:300])
    check("Ongoing Threads section created", "## Ongoing Threads" in new_content, new_content[:200])


def test_rebuild_thread_updates_merged() -> None:
    section("_rebuild_memory_md — thread updates merged into Ongoing Threads")
    entry = "### Session: 2026-03-12\n- Task: t\n- Outcome: done\n- Key outputs: none\n- Carry-forward: none"
    new_content, threads_updated = _rebuild_memory_md(
        _EXISTING_MEMORY, entry,
        [("ADD", "new-thread", "started"), ("DONE", "old-thread", "")],
        max_sessions=10,
    )
    check("threads_updated=True", threads_updated is True)
    check("new thread added", "new-thread" in new_content, new_content[:400])
    check("old thread removed", "old-thread" not in new_content.split("## Session Log")[0], new_content[:400])


def test_rebuild_session_cap_enforced() -> None:
    section("_rebuild_memory_md — max_sessions cap collapses overflow")
    # Build existing with 3 sessions
    existing = "# Agent Memory\n\n## Ongoing Threads\n\n## Session Log\n\n"
    for i in range(3):
        existing += f"### Session: 2026-03-0{i+1}\n- Task: t{i}\n- Outcome: done\n- Key outputs: none\n- Carry-forward: none\n\n"
    new_entry = "### Session: 2026-03-12\n- Task: new\n- Outcome: done\n- Key outputs: none\n- Carry-forward: none"
    # Allow only 3 sessions total; 4th will trigger overflow compaction
    new_content, _ = _rebuild_memory_md(existing, new_entry, [], max_sessions=3)
    count = new_content.count("### Session:")
    check(f"session count <= 4 (3 + compacted block)", count <= 4, str(count))
    check("new session present", "2026-03-12" in new_content, new_content[:400])


# ── Tests: run_session_wrapup_log ───────────────────────────────────────────────

def test_run_empty_history() -> None:
    section("run_session_wrapup_log — empty messages -> EMPTY_HISTORY error")
    with tempfile.TemporaryDirectory() as tmp:
        result = run_session_wrapup_log(
            [], api_key="test-key", workspace_root=tmp, today="2026-03-12"
        )
    check("status=error", result.status == "error", str(result))
    check("error_code=EMPTY_HISTORY", result.error_code == "EMPTY_HISTORY", str(result))


def test_run_dependency_missing() -> None:
    section("run_session_wrapup_log — openai absent -> DEPENDENCY_MISSING")
    with tempfile.TemporaryDirectory() as tmp:
        with patch.dict(sys.modules, {"openai": None}):
            result = run_session_wrapup_log(
                _SAMPLE_MESSAGES, api_key="key", workspace_root=tmp, today="2026-03-12"
            )
    check("status=error", result.status == "error", str(result))
    check("error_code=DEPENDENCY_MISSING", result.error_code == "DEPENDENCY_MISSING", str(result))


def test_run_api_error() -> None:
    section("run_session_wrapup_log — API raises -> API_ERROR, MEMORY.md unchanged")
    with tempfile.TemporaryDirectory() as tmp:
        openai_mod = types.ModuleType("openai")
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("network error")
        openai_mod.OpenAI = MagicMock(return_value=mock_client)
        with patch.dict(sys.modules, {"openai": openai_mod}):
            result = run_session_wrapup_log(
                _SAMPLE_MESSAGES, api_key="key", workspace_root=tmp, today="2026-03-12"
            )
        memory_path = Path(tmp) / "MEMORY.md"
        check("status=error", result.status == "error", str(result))
        check("error_code=API_ERROR", result.error_code == "API_ERROR", str(result))
        check("MEMORY.md not created", not memory_path.exists())


def test_run_success_creates_memory_md() -> None:
    section("run_session_wrapup_log — success -> MEMORY.md created with session entry")
    with tempfile.TemporaryDirectory() as tmp:
        with patch.dict(sys.modules, _fake_openai(_SAMPLE_RESPONSE)):
            result = run_session_wrapup_log(
                _SAMPLE_MESSAGES, api_key="key", workspace_root=tmp, today="2026-03-12"
            )
        memory_path = Path(tmp) / "MEMORY.md"
        check("status=done", result.status == "done", str(result))
        check("MEMORY.md created", memory_path.exists())
        content = memory_path.read_text(encoding="utf-8")
        check("session entry in file", "2026-03-12" in content, content[:300])
        check("memory_md_path returned", result.memory_md_path != "")


def test_run_success_threads_updated() -> None:
    section("run_session_wrapup_log — response with thread updates -> threads_updated=True")
    with tempfile.TemporaryDirectory() as tmp:
        with patch.dict(sys.modules, _fake_openai(_SAMPLE_RESPONSE)):
            result = run_session_wrapup_log(
                _SAMPLE_MESSAGES, api_key="key", workspace_root=tmp, today="2026-03-12"
            )
    check("status=done", result.status == "done", str(result))
    check("threads_updated=True", result.threads_updated is True)


def test_run_success_appends_to_existing() -> None:
    section("run_session_wrapup_log — existing MEMORY.md -> new entry prepended")
    with tempfile.TemporaryDirectory() as tmp:
        memory_path = Path(tmp) / "MEMORY.md"
        memory_path.write_text(_EXISTING_MEMORY, encoding="utf-8")
        with patch.dict(sys.modules, _fake_openai(_SAMPLE_RESPONSE)):
            result = run_session_wrapup_log(
                _SAMPLE_MESSAGES, api_key="key", workspace_root=tmp, today="2026-03-12"
            )
        content = memory_path.read_text(encoding="utf-8")
    check("status=done", result.status == "done", str(result))
    check("new session in file", "2026-03-12" in content, content[:400])
    check("old session still present", "2026-03-11" in content, content[:400])
    idx_new = content.find("2026-03-12")
    idx_old = content.find("2026-03-11")
    check("new session before old", idx_new < idx_old, f"new={idx_new} old={idx_old}")


# ── Runner ──────────────────────────────────────────────────────────────────────

def run_all() -> None:
    print("\n" + "=" * 60)
    print("  session_wrapup_log — test suite")
    print("=" * 60)

    # _parse_wrapup_response
    test_parse_session_entry_extracted()
    test_parse_thread_updates_extracted()
    test_parse_no_thread_section()

    # _apply_thread_updates
    test_apply_thread_add()
    test_apply_thread_done_removes()
    test_apply_thread_keep_updates()

    # _rebuild_memory_md
    test_rebuild_prepends_session()
    test_rebuild_from_empty_memory()
    test_rebuild_thread_updates_merged()
    test_rebuild_session_cap_enforced()

    # run_session_wrapup_log
    test_run_empty_history()
    test_run_dependency_missing()
    test_run_api_error()
    test_run_success_creates_memory_md()
    test_run_success_threads_updated()
    test_run_success_appends_to_existing()

    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print(f"\n{'=' * 60}")
    print(f"  Results: {passed}/{total} passed")
    print("=" * 60)
    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    run_all()
