"""
Scout (computer agent) test suite.

Run from workspace root:
    python -m computer_agent.test_scout                    # all unit tests
    python -m computer_agent.test_scout --live             # include live API runs (needs OPENAI_API_KEY)
    python -m computer_agent.test_scout --live --desktop   # live desktop-mode run only

Unit tests (no API key needed):
    1.  compaction - token estimator strips base64
    2.  compaction - skips when under threshold
    3.  compaction - serializer output format
    4.  compaction - apply preserves first item + tail
    5.  prompts    - get_system_prompt returns correct variant
    6.  screenshot - take_screenshot returns valid base64 PNG
    7.  screenshot - screen_size returns positive dimensions
    8.  actions    - execute_action(wait) non-blocking
    9.  actions    - execute_action returns description string
    10. browser    - find_chrome locates executable
    11. agent      - _parse_signal detects signals correctly
    12. agent      - _payload extracts text after prefix
    13. agent      - desktop mode config (no Chrome launch)
    14. models     - RunConfig defaults
"""
from __future__ import annotations

import asyncio
import os
import sys

# Windows terminals default to cp1252 which can't render Unicode box-drawing chars
# used by comm_channels/templates.py — force utf-8 for this test process.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Load .env so OPENAI_API_KEY is available for live tests
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# -- Helpers -------------------------------------------------------------------

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
SKIP = "\033[33mSKIP\033[0m"
_results: list[tuple[str, bool, str, bool]] = []   # name, ok, detail, skipped


def check(name: str, condition: bool, detail: str = "") -> None:
    _results.append((name, condition, detail, False))
    status = PASS if condition else FAIL
    detail_str = f"  -> {detail}" if detail else ""
    print(f"  [{status}] {name}{detail_str}")


def skip(name: str, reason: str = "") -> None:
    _results.append((name, True, reason, True))
    print(f"  [{SKIP}] {name}  ({reason})")


def section(title: str) -> None:
    print(f"\n{'-' * 60}")
    print(f"  {title}")
    print(f"{'-' * 60}")


# -- 1-4: Compaction unit tests ------------------------------------------------

def test_token_estimator_strips_base64() -> None:
    section("1. compaction - token estimator strips base64")
    from computer_agent.compaction import estimate_tokens

    items = [
        {"role": "user", "content": "post on linkedin"},
        {"type": "computer_call", "actions": [{"type": "click", "x": 100, "y": 200}]},
        {
            "type": "computer_call_output",
            "output": {
                "type": "computer_screenshot",
                "image_url": "data:image/png;base64,AAAA" + "B" * 100_000,
                "detail": "original",
            },
        },
    ]
    est = estimate_tokens(items)
    # Without stripping: 100k base64 chars -> ~75k tiktoken tokens
    # With stripping: ~10 text tokens + 300 vision = ~310
    check("estimate < 1000 tokens", est < 1_000, f"got {est}")
    check("estimate > 200 tokens (screenshot counted)", est >= 200, f"got {est}")


def test_compact_skips_under_threshold() -> None:
    section("2. compaction - skips when under threshold")
    from computer_agent.compaction import maybe_compact, COMPACT_THRESHOLD

    tiny = [{"role": "user", "content": "hello"}]
    _, cr = maybe_compact(tiny, api_key="fake-key-no-call-made")
    check("status=skipped", cr.status == "skipped", cr.status)
    check("threshold documented", COMPACT_THRESHOLD == 255_000, str(COMPACT_THRESHOLD))


def test_serializer_format() -> None:
    section("3. compaction - serializer output format")
    from computer_agent.compaction import _serialize

    items = [
        {"role": "user", "content": "go to google"},
        {"type": "computer_call", "call_id": "x", "actions": [{"type": "click", "x": 10, "y": 20}]},
        {"type": "computer_call_output", "call_id": "x", "output": {"image_url": "data:image/png;base64,AAA", "detail": "original"}},
        {"role": "assistant", "content": "DONE: visited google"},
    ]
    out = _serialize(items)
    check("[USER] block present",      "[USER]" in out)
    check("[SCOUT ACTION] block",      "[SCOUT ACTION: click]" in out)
    check("[SCREENSHOT] placeholder",  "[SCREENSHOT]" in out)
    check("[ASSISTANT] block",         "[ASSISTANT]" in out)
    check("no base64 blob in output",  "data:image/png;base64" not in out)


def test_apply_compaction_shape() -> None:
    section("4. compaction - _apply_compaction preserves first item + tail")
    from computer_agent.compaction import _apply_compaction

    items = [{"role": "user", "content": f"item {i}"} for i in range(10)]
    result = _apply_compaction(items, "compacted state here")

    check("first item preserved",        result[0] == items[0])
    check("compacted marker in item 1",  "COMPACTED SESSION STATE" in result[1]["content"])
    check("last 4 items in tail",        result[-1] == items[-1])
    check("tail length = 4",            result[-4:] == items[-4:])


# -- 5: Prompts ----------------------------------------------------------------

def test_prompts() -> None:
    section("5. prompts - get_system_prompt variants")
    from computer_agent.prompts import get_system_prompt

    bp = get_system_prompt("browser")
    dp = get_system_prompt("desktop")

    check("browser prompt non-empty",        len(bp) > 500)
    check("desktop prompt non-empty",        len(dp) > 500)
    check("browser contains Scout identity", "Scout" in bp)
    check("desktop contains Scout identity", "Scout" in dp)
    check("browser mentions login rules",    "Login" in bp or "login" in bp)
    check("desktop mentions Win key",        "Win" in dp)
    check("both mention DONE signal",        "DONE:" in bp and "DONE:" in dp)
    check("prompts differ",                  bp != dp)


# -- 6-7: Screenshot -----------------------------------------------------------

def test_screenshot() -> None:
    section("6. screenshot - take_screenshot captures screen")
    from computer_agent.screenshot import take_screenshot
    import base64

    b64, size = take_screenshot()
    w, h = size

    check("returns base64 string",       isinstance(b64, str) and len(b64) > 0)
    check("valid base64",                _is_valid_base64(b64), f"len={len(b64)}")
    check("PNG magic bytes",             base64.b64decode(b64[:12])[:4] == b'\x89PNG', "PNG header")
    check("positive dimensions",         w > 0 and h > 0, f"{w}x{h}")
    check("native resolution (no downscale)", w >= 800 and h >= 600, f"{w}x{h}")


def test_screen_size() -> None:
    section("7. screenshot - screen_size returns valid dimensions")
    from computer_agent.screenshot import screen_size

    w, h = screen_size()
    check("width > 0",   w > 0,    f"w={w}")
    check("height > 0",  h > 0,    f"h={h}")
    check("width >= 800",  w >= 800,  f"w={w}")
    check("height >= 600", h >= 600,  f"h={h}")


def _is_valid_base64(s: str) -> bool:
    import base64 as b64_mod
    try:
        b64_mod.b64decode(s + "==")
        return True
    except Exception:
        return False


# -- 8-9: Actions --------------------------------------------------------------

def test_action_wait() -> None:
    section("8. actions - execute_action wait is non-blocking async")
    from computer_agent.actions import execute_action
    import time

    start = time.time()
    desc = asyncio.run(execute_action({"type": "wait"}))
    elapsed = time.time() - start

    check("returns description string",   isinstance(desc, str))
    check("description mentions wait",    "wait" in desc.lower(), desc)
    check("respected ~2s fixed wait",     1.5 < elapsed < 4.0, f"{elapsed:.2f}s")


def test_action_unknown() -> None:
    section("9. actions - unknown action returns description, not exception")
    from computer_agent.actions import execute_action

    desc = asyncio.run(execute_action({"type": "does_not_exist"}))
    check("returns string",               isinstance(desc, str))
    check("mentions unknown",             "unknown" in desc.lower(), desc)


# -- 10: Browser ---------------------------------------------------------------

def test_find_chrome() -> None:
    section("10. browser - find_chrome locates executable")
    from computer_agent.browser import find_chrome
    import pathlib

    try:
        path = find_chrome()
        check("path is non-empty string", bool(path))
        check("file exists on disk",      pathlib.Path(path).exists(), path)
        check("ends with chrome.exe",     path.lower().endswith("chrome.exe"), path)
    except RuntimeError as e:
        skip("find_chrome", f"Chrome not found: {e}")


# -- 11-13: Agent helpers ------------------------------------------------------

def test_agent_parse_signal() -> None:
    section("11. agent - _parse_signal detects signals")
    from computer_agent.agent import _parse_signal

    check("DONE detected",         _parse_signal("DONE: all done") == "DONE")
    check("FAILED detected",       _parse_signal("FAILED: gave up") == "FAILED")
    check("NEED_INPUT detected",   _parse_signal("NEED_INPUT: log in please") == "NEED_INPUT")
    check("plain text -> None",     _parse_signal("clicking on button") is None)
    check("empty string -> None",   _parse_signal("") is None)


def test_agent_payload() -> None:
    section("12. agent - _payload extracts text after prefix")
    from computer_agent.agent import _payload

    check("DONE: payload",         _payload("DONE: task complete", "DONE") == "task complete")
    check("FAILED: payload",       _payload("FAILED: no access", "FAILED") == "no access")
    check("NEED_INPUT: payload",   _payload("NEED_INPUT: log in to LinkedIn", "NEED_INPUT") == "log in to LinkedIn")
    check("no colon - still works",_payload("DONE task complete", "DONE") == "task complete")


def test_desktop_mode_config() -> None:
    section("13. agent - desktop mode skips Chrome launch")
    from computer_agent.models import RunConfig

    cfg = RunConfig(task="open Notepad", mode="desktop", launch_browser=False)
    check("mode=desktop",          cfg.mode == "desktop")
    check("launch_browser=False",  cfg.launch_browser is False)
    check("medium default",        cfg.medium == "telegram")
    check("max_turns default",     cfg.max_turns == 60)


def test_models_defaults() -> None:
    section("14. models - RunConfig defaults")
    from computer_agent.models import RunConfig

    cfg = RunConfig(task="do something")
    check("mode default=browser",  cfg.mode == "browser")
    check("profile default",       cfg.profile == "default")
    check("launch_browser=True",   cfg.launch_browser is True)
    check("medium=telegram",       cfg.medium == "telegram")
    check("max_turns=60",          cfg.max_turns == 60)


# -- Live integration test (optional) -----------------------------------------

def test_live_run(mode: str = "browser") -> None:
    section(f"LIVE - run Scout in {mode} mode (real API call)")

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        skip(f"live {mode} run", "OPENAI_API_KEY not set")
        return

    from computer_agent.agent import run
    from computer_agent.models import RunConfig

    if mode == "browser":
        cfg = RunConfig(
            task=(
                "Navigate to https://en.wikipedia.org/wiki/Main_Page in the browser. "
                "Tell me the exact title text shown in the page's <h1> element "
                "(it should say 'Wikipedia, the free encyclopedia' or similar). "
                "Do NOT use any cached or already-open tab — type the URL into the address bar."
            ),
            mode="browser",
            medium="terminal",
            max_turns=15,
        )
    else:
        cfg = RunConfig(
            task=(
                "Open Notepad (press Win key, type 'notepad', press Enter). "
                "Once Notepad is open, type the text 'Hello World'. "
                "Then close Notepad without saving (click No if prompted to save). "
                "Signal DONE: works when Notepad is closed."
            ),
            mode="desktop",
            launch_browser=False,
            medium="terminal",
            max_turns=25,
        )

    print(f"  Running Scout task: {cfg.task!r}")
    result = run(
        cfg,
        workspace_root=os.getcwd(),
        agent_session_id="test_scout_live",
        api_key=api_key,
    )

    check(f"status is done or failed",  result.status in ("done", "failed"), result.status)
    payload = getattr(result, "deliverable", None) or getattr(result, "reason", "")
    check("non-empty result payload",   bool(payload), payload[:120])

    print(f"\n  Result -> [{result.status}] {payload[:200]}")


# -- Main ----------------------------------------------------------------------

def main() -> None:
    live = "--live" in sys.argv

    print("\n" + "=" * 60)
    print("  Scout (computer agent) - test suite")
    if live:
        print("  Mode: unit + live API (browser + desktop)")
    else:
        print("  Mode: unit only  (pass --live to include real API runs)")
    print("=" * 60)

    test_token_estimator_strips_base64()
    test_compact_skips_under_threshold()
    test_serializer_format()
    test_apply_compaction_shape()
    test_prompts()
    test_screenshot()
    test_screen_size()
    test_action_wait()
    test_action_unknown()
    test_find_chrome()
    test_agent_parse_signal()
    test_agent_payload()
    test_desktop_mode_config()
    test_models_defaults()

    if live:
        test_live_run("browser")
        test_live_run("desktop")

    # -- Summary ---------------------------------------------------------------
    passed  = sum(1 for _, ok, _, sk in _results if ok and not sk)
    failed  = sum(1 for _, ok, _, sk in _results if not ok)
    skipped = sum(1 for _, ok, _, sk in _results if sk)
    total   = len(_results)

    print(f"\n{'=' * 60}")
    print(f"  Results: {passed}/{total - skipped} passed", end="")
    if skipped:
        print(f"  |  {skipped} skipped", end="")
    if failed:
        print(f"  |  {failed} FAILED:")
        for name, ok, detail, _ in _results:
            if not ok:
                print(f"    x {name}  ({detail})")
    else:
        print("  - all good")
    print("=" * 60)

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
