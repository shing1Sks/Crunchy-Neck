"""
test_skill_use.py — unit tests for skill_use.py

Run directly:
    python agent-design/tests/test_skill_use.py
"""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import sys
import tempfile
from pathlib import Path

# agent-design/ has a hyphen, so it is not a valid Python package name.
# Load skill_use.py directly via importlib — same pattern as test_memory_compaction.py.
_here = Path(__file__).resolve().parent.parent  # tests/ -> agent-design/
_spec = importlib.util.spec_from_file_location("skill_use", _here / "skill_use.py")
_mod = importlib.util.module_from_spec(_spec)   # type: ignore[arg-type]
sys.modules["skill_use"] = _mod
_spec.loader.exec_module(_mod)                  # type: ignore[union-attr]

_parse_frontmatter       = _mod._parse_frontmatter
_is_eligible             = _mod._is_eligible
_compact_path            = _mod._compact_path
_current_os              = _mod._current_os
scan_skills              = _mod.scan_skills
format_skills_for_prompt = _mod.format_skills_for_prompt
build_skill_section      = _mod.build_skill_section
MAX_SKILLS_IN_PROMPT     = _mod.MAX_SKILLS_IN_PROMPT
MAX_SKILLS_PROMPT_CHARS  = _mod.MAX_SKILLS_PROMPT_CHARS


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

def _write_skill(skills_dir: Path, name: str, frontmatter: str, body: str = "## When to use\ntest\n") -> None:
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    content = f"---\n{frontmatter}\n---\n\n{body}"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


def _make_workspace(tmp: Path) -> Path:
    ws = tmp / "workspace"
    (ws / "skills").mkdir(parents=True)
    return ws


def _make_skills_list(n: int) -> list[dict]:
    return [
        {"name": f"skill-{i}", "description": f"desc {i}",
         "location": f"skills/skill-{i}/SKILL.md", "meta": {}}
        for i in range(n)
    ]


# ── Tests: _parse_frontmatter ───────────────────────────────────────────────────

def test_parse_frontmatter_valid() -> None:
    section("_parse_frontmatter — valid YAML frontmatter")
    text = "---\nname: foo\ndescription: bar\n---\n# body"
    meta, body = _parse_frontmatter(text)
    check("name parsed", meta.get("name") == "foo", str(meta))
    check("description parsed", meta.get("description") == "bar", str(meta))
    check("body contains heading", "body" in body, repr(body))


def test_parse_frontmatter_no_fence() -> None:
    section("_parse_frontmatter — no --- fence -> empty meta")
    text = "# Just a heading\nsome text"
    meta, body = _parse_frontmatter(text)
    check("meta is empty", meta == {}, str(meta))
    check("body preserved", "heading" in body, repr(body))


def test_parse_frontmatter_empty_block() -> None:
    section("_parse_frontmatter — empty YAML block")
    meta, _ = _parse_frontmatter("---\n---\n# body")
    check("meta is empty dict", meta == {}, str(meta))


def test_parse_frontmatter_malformed_yaml() -> None:
    section("_parse_frontmatter — malformed YAML -> empty meta (no crash)")
    meta, _ = _parse_frontmatter("---\n: bad: yaml: [\n---\n# body")
    check("meta is empty", meta == {}, str(meta))


def test_parse_frontmatter_unclosed() -> None:
    section("_parse_frontmatter — unclosed fence -> empty meta")
    meta, _ = _parse_frontmatter("---\nname: foo\n# no closing ---")
    check("meta is empty", meta == {}, str(meta))


# ── Tests: _is_eligible ─────────────────────────────────────────────────────────

def test_eligible_empty_meta() -> None:
    section("_is_eligible — empty meta is eligible")
    check("eligible", _is_eligible({}) is True)


def test_eligible_enabled_false() -> None:
    section("_is_eligible — enabled: false -> excluded")
    check("excluded", _is_eligible({"enabled": False}) is False)


def test_eligible_disable_model_invocation() -> None:
    section("_is_eligible — disable-model-invocation: true -> excluded")
    check("excluded", _is_eligible({"disable-model-invocation": True}) is False)


def test_eligible_always_true_bypasses() -> None:
    section("_is_eligible — always: true bypasses binary check")
    meta = {
        "always": True,
        "metadata": {"requires": {"anyBins": ["__definitely_not_a_real_binary__"]}},
    }
    check("included despite missing binary", _is_eligible(meta) is True)


def test_eligible_missing_binary() -> None:
    section("_is_eligible — missing binary -> excluded")
    meta = {"metadata": {"requires": {"anyBins": ["__definitely_not_a_real_binary__"]}}}
    check("excluded", _is_eligible(meta) is False)


def test_eligible_present_binary() -> None:
    section("_is_eligible — present binary -> included")
    binary = "python3" if shutil.which("python3") else "python"
    meta = {"metadata": {"requires": {"anyBins": [binary]}}}
    check(f"included ({binary} found)", _is_eligible(meta) is True)


def test_eligible_missing_env_var() -> None:
    section("_is_eligible — missing env var -> excluded")
    env_key = "__TEST_SKILL_ENV_ABSENT__"
    os.environ.pop(env_key, None)
    meta = {"metadata": {"requires": {"env": [env_key]}}}
    check("excluded", _is_eligible(meta) is False)


def test_eligible_present_env_var() -> None:
    section("_is_eligible — present env var -> included")
    env_key = "__TEST_SKILL_ENV_PRESENT__"
    os.environ[env_key] = "1"
    try:
        meta = {"metadata": {"requires": {"env": [env_key]}}}
        check("included", _is_eligible(meta) is True)
    finally:
        os.environ.pop(env_key, None)


def test_eligible_os_mismatch() -> None:
    section("_is_eligible — OS mismatch -> excluded")
    wrong_os = "darwin" if platform.system() == "Windows" else "win32"
    meta = {"metadata": {"os": [wrong_os]}}
    check("excluded", _is_eligible(meta) is False)


def test_eligible_os_match() -> None:
    section("_is_eligible — OS match -> included")
    current = _current_os()
    meta = {"metadata": {"os": [current]}}
    check(f"included (os={current})", _is_eligible(meta) is True)


def test_eligible_empty_os_means_all() -> None:
    section("_is_eligible — empty os list -> all OSes included")
    check("included", _is_eligible({"metadata": {"os": []}}) is True)


# ── Tests: scan_skills ──────────────────────────────────────────────────────────

def test_scan_empty_skills_dir() -> None:
    section("scan_skills — empty skills/ dir")
    with tempfile.TemporaryDirectory() as tmp:
        ws = _make_workspace(Path(tmp))
        result = scan_skills(str(ws))
    check("returns empty list", result == [], str(result))


def test_scan_no_skills_dir() -> None:
    section("scan_skills — no skills/ dir at all")
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp) / "workspace"
        ws.mkdir()
        result = scan_skills(str(ws))
    check("returns empty list", result == [], str(result))


def test_scan_template_dir_skipped() -> None:
    section("scan_skills — _template/ dir is skipped")
    with tempfile.TemporaryDirectory() as tmp:
        ws = _make_workspace(Path(tmp))
        _write_skill(ws / "skills", "_template", "name: template\ndescription: skip me")
        result = scan_skills(str(ws))
    check("_template excluded", result == [], str(result))


def test_scan_valid_skill_discovered() -> None:
    section("scan_skills — valid skill is discovered")
    with tempfile.TemporaryDirectory() as tmp:
        ws = _make_workspace(Path(tmp))
        _write_skill(ws / "skills", "my-skill", "name: my-skill\ndescription: does cool things")
        skills = scan_skills(str(ws))
    check("one skill found", len(skills) == 1, str(len(skills)))
    check("name correct", skills[0]["name"] == "my-skill", skills[0].get("name", ""))
    check("description correct", skills[0]["description"] == "does cool things", skills[0].get("description", ""))
    check("location has SKILL.md", "SKILL.md" in skills[0]["location"], skills[0].get("location", ""))


def test_scan_missing_skill_md_skipped() -> None:
    section("scan_skills — dir without SKILL.md is skipped")
    with tempfile.TemporaryDirectory() as tmp:
        ws = _make_workspace(Path(tmp))
        (ws / "skills" / "no-file").mkdir()
        result = scan_skills(str(ws))
    check("empty result", result == [], str(result))


def test_scan_no_frontmatter_included() -> None:
    section("scan_skills — SKILL.md with no frontmatter -> included (meta={})")
    with tempfile.TemporaryDirectory() as tmp:
        ws = _make_workspace(Path(tmp))
        skill_dir = ws / "skills" / "bare"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Just a heading\n", encoding="utf-8")
        skills = scan_skills(str(ws))
    check("skill included", len(skills) == 1, str(len(skills)))


def test_scan_disable_model_invocation_excluded() -> None:
    section("scan_skills — disable-model-invocation: true -> excluded from prompt")
    with tempfile.TemporaryDirectory() as tmp:
        ws = _make_workspace(Path(tmp))
        _write_skill(
            ws / "skills", "user-only",
            "name: user-only\ndescription: slash cmd only\ndisable-model-invocation: true",
        )
        result = scan_skills(str(ws))
    check("excluded", result == [], str(result))


def test_scan_multiple_skills() -> None:
    section("scan_skills — multiple skills all discovered")
    with tempfile.TemporaryDirectory() as tmp:
        ws = _make_workspace(Path(tmp))
        for i in range(5):
            _write_skill(ws / "skills", f"skill-{i}", f"name: skill-{i}\ndescription: skill {i}")
        skills = scan_skills(str(ws))
    check("5 skills found", len(skills) == 5, str(len(skills)))


def test_scan_oversized_file_skipped() -> None:
    section("scan_skills — oversized SKILL.md (>256KB) is skipped")
    with tempfile.TemporaryDirectory() as tmp:
        ws = _make_workspace(Path(tmp))
        skill_dir = ws / "skills" / "big"
        skill_dir.mkdir()
        big_content = "---\nname: big\ndescription: huge\n---\n" + "x" * (256 * 1024 + 1)
        (skill_dir / "SKILL.md").write_text(big_content, encoding="utf-8")
        result = scan_skills(str(ws))
    check("oversized skill excluded", result == [], str(result))


# ── Tests: format_skills_for_prompt ────────────────────────────────────────────

def test_format_empty_list() -> None:
    section("format_skills_for_prompt — empty list -> valid XML shell")
    result = format_skills_for_prompt([])
    check("opens tag present", "<available_skills>" in result, result)
    check("closing tag present", "</available_skills>" in result, result)


def test_format_single_skill() -> None:
    section("format_skills_for_prompt — single skill appears")
    skills = _make_skills_list(1)
    result = format_skills_for_prompt(skills)
    check('name="skill-0" present', 'name="skill-0"' in result, result[:200])
    check("description present", "<description>desc 0</description>" in result, result[:200])


def test_format_respects_150_limit() -> None:
    section("format_skills_for_prompt — caps at 150 skills")
    result = format_skills_for_prompt(_make_skills_list(200))
    count = result.count("<skill name=")
    check(f"count={count} <= 150", count <= MAX_SKILLS_IN_PROMPT, str(count))


def test_format_respects_char_budget() -> None:
    section("format_skills_for_prompt — stays within 30,000 char budget")
    result = format_skills_for_prompt(_make_skills_list(400))
    check(
        f"len={len(result)} <= {MAX_SKILLS_PROMPT_CHARS + 50}",
        len(result) <= MAX_SKILLS_PROMPT_CHARS + 50,
        str(len(result)),
    )


def test_format_home_dir_compressed() -> None:
    section("format_skills_for_prompt — home dir path compressed to ~/")
    home = str(Path.home()).replace("\\", "/")
    skills = [{
        "name": "home-skill",
        "description": "lives in home",
        "location": f"{home}/skills/home-skill/SKILL.md",
        "meta": {},
    }]
    result = format_skills_for_prompt(skills)
    check("~/ present", "~/" in result, result[:200])
    check("raw home path absent", home not in result, result[:200])


# ── Tests: build_skill_section ──────────────────────────────────────────────────

def test_build_contains_mandatory_header() -> None:
    section("build_skill_section — mandatory header present")
    with tempfile.TemporaryDirectory() as tmp:
        ws = _make_workspace(Path(tmp))
        out = build_skill_section(str(ws))
    check("## Skills (mandatory) present", "## Skills (mandatory)" in out)
    check("Before replying: present", "Before replying:" in out)
    check("<available_skills> present", "<available_skills>" in out)


def test_build_contains_skill() -> None:
    section("build_skill_section — skill teaser appears in output")
    with tempfile.TemporaryDirectory() as tmp:
        ws = _make_workspace(Path(tmp))
        _write_skill(ws / "skills", "my-skill", "name: my-skill\ndescription: does cool things")
        out = build_skill_section(str(ws))
    check("skill name present", "my-skill" in out)
    check("skill description present", "does cool things" in out)


def test_build_no_skills_still_valid() -> None:
    section("build_skill_section — empty skills/ is still valid output")
    with tempfile.TemporaryDirectory() as tmp:
        ws = _make_workspace(Path(tmp))
        out = build_skill_section(str(ws))
    check("header present", "## Skills (mandatory)" in out)
    check("available_skills open", "<available_skills>" in out)
    check("available_skills close", "</available_skills>" in out)


def test_build_constraint_text() -> None:
    section("build_skill_section — constraint text present")
    with tempfile.TemporaryDirectory() as tmp:
        ws = _make_workspace(Path(tmp))
        out = build_skill_section(str(ws))
    check("constraint text present", "Never read more than one skill" in out)


# ── Runner ──────────────────────────────────────────────────────────────────────

def run_all() -> None:
    print("\n" + "=" * 60)
    print("  skill_use — test suite")
    print("=" * 60)

    # _parse_frontmatter
    test_parse_frontmatter_valid()
    test_parse_frontmatter_no_fence()
    test_parse_frontmatter_empty_block()
    test_parse_frontmatter_malformed_yaml()
    test_parse_frontmatter_unclosed()

    # _is_eligible
    test_eligible_empty_meta()
    test_eligible_enabled_false()
    test_eligible_disable_model_invocation()
    test_eligible_always_true_bypasses()
    test_eligible_missing_binary()
    test_eligible_present_binary()
    test_eligible_missing_env_var()
    test_eligible_present_env_var()
    test_eligible_os_mismatch()
    test_eligible_os_match()
    test_eligible_empty_os_means_all()

    # scan_skills
    test_scan_empty_skills_dir()
    test_scan_no_skills_dir()
    test_scan_template_dir_skipped()
    test_scan_valid_skill_discovered()
    test_scan_missing_skill_md_skipped()
    test_scan_no_frontmatter_included()
    test_scan_disable_model_invocation_excluded()
    test_scan_multiple_skills()
    test_scan_oversized_file_skipped()

    # format_skills_for_prompt
    test_format_empty_list()
    test_format_single_skill()
    test_format_respects_150_limit()
    test_format_respects_char_budget()
    test_format_home_dir_compressed()

    # build_skill_section
    test_build_contains_mandatory_header()
    test_build_contains_skill()
    test_build_no_skills_still_valid()
    test_build_constraint_text()

    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print(f"\n{'=' * 60}")
    print(f"  Results: {passed}/{total} passed")
    print("=" * 60)
    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    run_all()
