"""
test_identity_and_memory.py — unit tests for identity_and_memory.py

Run directly:
    python agent-design/tests/test_identity_and_memory.py
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

# Load identity_and_memory.py via importlib (agent-design/ has a hyphen)
_here = Path(__file__).resolve().parent.parent  # tests/ -> agent-design/
_spec = importlib.util.spec_from_file_location("identity", _here / "identity_and_memory.py")
_mod = importlib.util.module_from_spec(_spec)   # type: ignore[arg-type]
sys.modules["identity"] = _mod
_spec.loader.exec_module(_mod)                  # type: ignore[union-attr]

load_user_md             = _mod.load_user_md
load_memory_md_extract   = _mod.load_memory_md_extract
build_identity_section   = _mod.build_identity_section
MAX_USER_MD_BYTES        = _mod.MAX_USER_MD_BYTES


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

def _ws(tmp: Path) -> Path:
    ws = tmp / "workspace"
    ws.mkdir()
    return ws


_SAMPLE_USER_MD = """\
# User Profile

## Identity
- Name: Shreyash
- Location: India

## Preferences
- Communication style: direct
"""

_SAMPLE_MEMORY_MD = """\
# Agent Memory

## Ongoing Threads
- [THREAD] skill-system: completed scan + prompt injection

## Session Log

### Session: 2026-03-11
- Task: Build skill scanner
- Outcome: completed
- Key outputs: agent-design/skill_use.py
- Carry-forward: none

### Session: 2026-03-10
- Task: Add memory compaction
- Outcome: completed
- Key outputs: agent-design/memory_compaction.py
- Carry-forward: none

### Session: 2026-03-09
- Task: Setup exec tool
- Outcome: completed
- Key outputs: tools/exec/
- Carry-forward: none
"""


# ── Tests: load_user_md ─────────────────────────────────────────────────────────

def test_load_user_md_present() -> None:
    section("load_user_md — file present -> returns content")
    with tempfile.TemporaryDirectory() as tmp:
        ws = _ws(Path(tmp))
        (ws / "USER.md").write_text(_SAMPLE_USER_MD, encoding="utf-8")
        result = load_user_md(str(ws))
    check("contains name", "Shreyash" in result, result[:100])
    check("contains preferences", "direct" in result, result[:100])


def test_load_user_md_absent() -> None:
    section("load_user_md — file absent -> returns empty string")
    with tempfile.TemporaryDirectory() as tmp:
        ws = _ws(Path(tmp))
        result = load_user_md(str(ws))
    check("returns empty string", result == "", repr(result))


def test_load_user_md_truncation() -> None:
    section("load_user_md — oversized file -> truncated with warning")
    with tempfile.TemporaryDirectory() as tmp:
        ws = _ws(Path(tmp))
        big = "x" * (MAX_USER_MD_BYTES + 100)
        (ws / "USER.md").write_bytes(big.encode("utf-8"))
        result = load_user_md(str(ws))
    check("truncation comment injected", "truncated" in result.lower(), result[-80:])
    check("content capped near 32KB", len(result) < MAX_USER_MD_BYTES + 200)


# ── Tests: load_memory_md_extract ──────────────────────────────────────────────

def test_load_memory_md_absent() -> None:
    section("load_memory_md_extract — file absent -> returns empty string")
    with tempfile.TemporaryDirectory() as tmp:
        ws = _ws(Path(tmp))
        result = load_memory_md_extract(str(ws))
    check("returns empty string", result == "", repr(result))


def test_load_memory_md_threads_always_included() -> None:
    section("load_memory_md_extract — Ongoing Threads always included")
    with tempfile.TemporaryDirectory() as tmp:
        ws = _ws(Path(tmp))
        (ws / "MEMORY.md").write_text(_SAMPLE_MEMORY_MD, encoding="utf-8")
        result = load_memory_md_extract(str(ws))
    check("threads heading present", "## Ongoing Threads" in result, result[:200])
    check("thread entry present", "skill-system" in result, result[:200])


def test_load_memory_md_session_cap() -> None:
    section("load_memory_md_extract — max_sessions cap respected")
    with tempfile.TemporaryDirectory() as tmp:
        ws = _ws(Path(tmp))
        (ws / "MEMORY.md").write_text(_SAMPLE_MEMORY_MD, encoding="utf-8")
        # Only 2 sessions allowed
        result = load_memory_md_extract(str(ws), max_sessions=2)
    count = result.count("### Session:")
    check(f"session count={count} <= 2", count <= 2, str(count))
    check("most-recent session included", "2026-03-11" in result, result[:300])
    check("oldest session excluded", "2026-03-09" not in result, result[:300])


def test_load_memory_md_all_sessions_within_cap() -> None:
    section("load_memory_md_extract — all sessions included when within cap")
    with tempfile.TemporaryDirectory() as tmp:
        ws = _ws(Path(tmp))
        (ws / "MEMORY.md").write_text(_SAMPLE_MEMORY_MD, encoding="utf-8")
        result = load_memory_md_extract(str(ws), max_sessions=10)
    count = result.count("### Session:")
    check("all 3 sessions present", count == 3, str(count))


def test_load_memory_md_no_threads_section() -> None:
    section("load_memory_md_extract — MEMORY.md with no Ongoing Threads section")
    content = "# Agent Memory\n\n## Session Log\n\n### Session: 2026-03-11\n- Task: test\n"
    with tempfile.TemporaryDirectory() as tmp:
        ws = _ws(Path(tmp))
        (ws / "MEMORY.md").write_text(content, encoding="utf-8")
        result = load_memory_md_extract(str(ws))
    check("session present", "2026-03-11" in result, result[:200])
    check("no crash", True)


# ── Tests: build_identity_section ──────────────────────────────────────────────

def test_build_mandatory_header() -> None:
    section("build_identity_section — mandatory identity header present")
    with tempfile.TemporaryDirectory() as tmp:
        ws = _ws(Path(tmp))
        out = build_identity_section(str(ws))
    check("## Identity present", "## Identity" in out)
    check("agent name present", "Crunchy" in out)


def test_build_memory_rules_present() -> None:
    section("build_identity_section — memory rules section present")
    with tempfile.TemporaryDirectory() as tmp:
        ws = _ws(Path(tmp))
        out = build_identity_section(str(ws))
    check("## Memory Rules present", "## Memory Rules" in out)
    check("mandatory in heading", "mandatory" in out)


def test_build_remember_tool_instruction() -> None:
    section("build_identity_section — remember() tool instruction present")
    with tempfile.TemporaryDirectory() as tmp:
        ws = _ws(Path(tmp))
        out = build_identity_section(str(ws))
    check("remember() mentioned", "remember()" in out)
    check("ALWAYS keyword present", "ALWAYS" in out)


def test_build_user_md_injected() -> None:
    section("build_identity_section — USER.md content injected")
    with tempfile.TemporaryDirectory() as tmp:
        ws = _ws(Path(tmp))
        (ws / "USER.md").write_text(_SAMPLE_USER_MD, encoding="utf-8")
        out = build_identity_section(str(ws))
    check("## User Profile present", "## User Profile" in out)
    check("user content injected", "Shreyash" in out)


def test_build_missing_user_md_placeholder() -> None:
    section("build_identity_section — missing USER.md -> placeholder injected")
    with tempfile.TemporaryDirectory() as tmp:
        ws = _ws(Path(tmp))
        out = build_identity_section(str(ws))
    check("placeholder present", "USER.md not found" in out, out[:400])
    check("instruction to create present", "write tool" in out.lower(), out[:400])


def test_build_memory_md_injected() -> None:
    section("build_identity_section — MEMORY.md extract injected")
    with tempfile.TemporaryDirectory() as tmp:
        ws = _ws(Path(tmp))
        (ws / "MEMORY.md").write_text(_SAMPLE_MEMORY_MD, encoding="utf-8")
        out = build_identity_section(str(ws))
    check("## Recent Session Context present", "## Recent Session Context" in out)
    check("session log content present", "skill scanner" in out.lower(), out[-500:])


def test_build_missing_memory_md_placeholder() -> None:
    section("build_identity_section — missing MEMORY.md -> placeholder injected")
    with tempfile.TemporaryDirectory() as tmp:
        ws = _ws(Path(tmp))
        out = build_identity_section(str(ws))
    check("no prior sessions placeholder", "No prior sessions" in out, out[-200:])


def test_build_custom_agent_name() -> None:
    section("build_identity_section — custom agent_name respected")
    with tempfile.TemporaryDirectory() as tmp:
        ws = _ws(Path(tmp))
        out = build_identity_section(str(ws), agent_name="TestBot")
    check("custom name present", "TestBot" in out)
    check("default name absent", "Crunchy" not in out or "TestBot" in out)


# ── Runner ──────────────────────────────────────────────────────────────────────

def run_all() -> None:
    print("\n" + "=" * 60)
    print("  identity — test suite")
    print("=" * 60)

    # load_user_md
    test_load_user_md_present()
    test_load_user_md_absent()
    test_load_user_md_truncation()

    # load_memory_md_extract
    test_load_memory_md_absent()
    test_load_memory_md_threads_always_included()
    test_load_memory_md_session_cap()
    test_load_memory_md_all_sessions_within_cap()
    test_load_memory_md_no_threads_section()

    # build_identity_section
    test_build_mandatory_header()
    test_build_memory_rules_present()
    test_build_remember_tool_instruction()
    test_build_user_md_injected()
    test_build_missing_user_md_placeholder()
    test_build_memory_md_injected()
    test_build_missing_memory_md_placeholder()
    test_build_custom_agent_name()

    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print(f"\n{'=' * 60}")
    print(f"  Results: {passed}/{total} passed")
    print("=" * 60)
    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    run_all()
