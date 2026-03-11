"""
skill_use.py — skill discovery, eligibility filtering, and system-prompt injection.

This module is the Python implementation of the skill selection protocol described
in Model-Skills-Architecture.md. It produces Section 6 ("Skills") of the system prompt.

Three public functions:

    scan_skills(workspace_root)          → list[dict]
    format_skills_for_prompt(skills)     → str   (<available_skills> XML block)
    build_skill_section(workspace_root)  → str   (mandatory header + XML block)

Usage in the system-prompt builder:

    from agent_design.skill_use import build_skill_section

    section_6 = build_skill_section(workspace_root)
    # Insert at Section 6 position (after CLI Quick Reference, before Memory Recall)

Standalone smoke-test:

    python -m agent_design.skill_use [workspace_root]
"""

from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# YAML frontmatter parsing — requires pyyaml (added to requirements.txt)
# ---------------------------------------------------------------------------

def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """
    Split a SKILL.md into (frontmatter_dict, body_text).

    SKILL.md files use YAML fenced between the first pair of '---' lines.
    Returns ({}, text) if no valid frontmatter is found.
    """
    try:
        import yaml  # pyyaml
    except ImportError:
        # Graceful degradation: treat every skill as having no frontmatter.
        return {}, text

    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text

    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break

    if end is None:
        return {}, text

    yaml_src = "".join(lines[1:end])
    body = "".join(lines[end + 1 :])

    try:
        data = yaml.safe_load(yaml_src) or {}
    except yaml.YAMLError:
        data = {}

    return data, body


# ---------------------------------------------------------------------------
# Eligibility logic
# ---------------------------------------------------------------------------

_PLATFORM_MAP = {
    "Windows": "win32",
    "Darwin":  "darwin",
    "Linux":   "linux",
}

def _current_os() -> str:
    return _PLATFORM_MAP.get(platform.system(), platform.system().lower())


def _is_eligible(meta: dict[str, Any]) -> bool:
    """
    Return True if a skill should be included in the system prompt.

    Rules (all must pass unless always=true):
      - enabled: false              → excluded
      - disable-model-invocation    → excluded (user-only slash-cmd skill)
      - always: true                → bypass remaining checks, include
      - requires.anyBins            → at least one binary must be on PATH
      - requires.env                → all listed env vars must be set
      - os                          → current OS must be in the list
    """
    if not meta.get("enabled", True):
        return False

    if meta.get("disable-model-invocation", False):
        return False

    if meta.get("always", False):
        return True

    skill_meta: dict[str, Any] = meta.get("metadata", {}) or {}
    requires: dict[str, Any] = skill_meta.get("requires", {}) or {}

    # Binary check: any of the listed binaries must exist on PATH
    any_bins: list[str] = requires.get("anyBins", []) or []
    if any_bins and not any(shutil.which(b) for b in any_bins):
        return False

    # Env var check: all listed vars must be present
    env_vars: list[str] = requires.get("env", []) or []
    if any(not os.environ.get(v) for v in env_vars):
        return False

    # OS check: current OS must be in the allowed list
    allowed_os: list[str] = skill_meta.get("os", []) or []
    if allowed_os and _current_os() not in allowed_os:
        return False

    return True


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

MAX_CANDIDATES_PER_ROOT = 300
MAX_SKILLS_LOADED       = 200
MAX_SKILL_FILE_BYTES    = 256 * 1024  # 256 KB


def scan_skills(workspace_root: str) -> list[dict[str, Any]]:
    """
    Scan <workspace_root>/skills/ for eligible skills.

    Returns a list of dicts:
        {
            "name":        str,   # skill folder name
            "description": str,   # from frontmatter
            "location":    str,   # relative path to SKILL.md (workspace-relative)
            "meta":        dict,  # full frontmatter dict
        }

    Skills in _template/ are always skipped.
    """
    skills_dir = Path(workspace_root) / "skills"
    if not skills_dir.is_dir():
        return []

    results: list[dict[str, Any]] = []
    candidates = 0

    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        if skill_dir.name.startswith("_"):
            continue  # skip _template and any other internal dirs

        candidates += 1
        if candidates > MAX_CANDIDATES_PER_ROOT:
            break

        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            continue

        if skill_file.stat().st_size > MAX_SKILL_FILE_BYTES:
            continue  # oversized — skip

        try:
            text = skill_file.read_text(encoding="utf-8")
        except OSError:
            continue

        meta, _ = _parse_frontmatter(text)

        if not _is_eligible(meta):
            continue

        description: str = meta.get("description", "").strip()
        name: str = meta.get("name", skill_dir.name).strip()

        # Location stored as workspace-relative forward-slash path
        try:
            location = skill_file.relative_to(workspace_root).as_posix()
        except ValueError:
            location = str(skill_file)

        results.append(
            {
                "name":        name,
                "description": description,
                "location":    location,
                "meta":        meta,
            }
        )

        if len(results) >= MAX_SKILLS_LOADED:
            break

    return results


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

MAX_SKILLS_IN_PROMPT    = 150
MAX_SKILLS_PROMPT_CHARS = 30_000


def _compact_path(path: str) -> str:
    """Replace the home directory prefix with ~/ to save tokens."""
    home = str(Path.home()).replace("\\", "/")
    path = path.replace("\\", "/")
    if path.startswith(home):
        return "~/" + path[len(home):].lstrip("/")
    return path


def format_skills_for_prompt(skills: list[dict[str, Any]]) -> str:
    """
    Build the <available_skills> XML block from a list of eligible skill dicts.

    Enforces:
        - max 150 skills
        - max 30,000 characters total
    """
    if not skills:
        return "<available_skills>\n</available_skills>"

    lines: list[str] = ["<available_skills>"]
    char_count = len(lines[0]) + 1  # +1 for newline

    for skill in skills[:MAX_SKILLS_IN_PROMPT]:
        location  = _compact_path(skill["location"])
        name      = skill["name"]
        desc      = skill["description"]

        entry = (
            f'<skill name="{name}" location="{location}">\n'
            f"  <description>{desc}</description>\n"
            f"</skill>"
        )

        if char_count + len(entry) + 1 > MAX_SKILLS_PROMPT_CHARS:
            break  # budget exhausted — stop adding

        lines.append(entry)
        char_count += len(entry) + 1

    lines.append("</available_skills>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# System-prompt section builder
# ---------------------------------------------------------------------------

_MANDATORY_HEADER = """\
## Skills (mandatory)

Before replying: scan <available_skills> <description> entries.
- If exactly one skill clearly applies: read its SKILL.md at <location> \
using the `read` tool, then follow it.
- If multiple could apply: choose the most specific one, then read and follow it.
- If none clearly apply: do not read any SKILL.md.

Constraints:
  - Never read more than one skill up front.
  - Only read after selecting — never speculatively.
  - Skills live at: <workspace>/skills/<skill-name>/SKILL.md
"""


def build_skill_section(workspace_root: str) -> str:
    """
    Build the complete Section 6 ("Skills") for the system prompt.

    Returns the mandatory instruction header followed by the
    <available_skills> XML block (which may be empty if no skills are eligible).

    This is the only function the system-prompt builder needs to call.
    """
    skills = scan_skills(workspace_root)
    xml_block = format_skills_for_prompt(skills)
    return _MANDATORY_HEADER + "\n" + xml_block


# ---------------------------------------------------------------------------
# Smoke-test entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    print(build_skill_section(root))
