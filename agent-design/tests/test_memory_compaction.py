"""
test_memory_compaction.py — test suite for memory_compaction.py

Run from the workspace root:
    python -m agent_design.test_memory_compaction
or directly:
    python agent-design/test_memory_compaction.py
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

# agent-design/ has a hyphen so it is not a valid Python package name.
# Load memory_compaction.py directly via importlib.
import importlib.util
import pathlib

_here = pathlib.Path(__file__).resolve().parent.parent  # agent-design/tests/ -> agent-design/
_spec = importlib.util.spec_from_file_location(
    "memory_compaction", _here / "memory_compaction.py"
)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
sys.modules["memory_compaction"] = _mod
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

CompactionConfig = _mod.CompactionConfig
CompactionResultDone = _mod.CompactionResultDone
CompactionResultError = _mod.CompactionResultError
CompactionResultSkipped = _mod.CompactionResultSkipped
_extract_text = _mod._extract_text
_serialize_history = _mod._serialize_history
apply_compaction = _mod.apply_compaction
estimate_tokens = _mod.estimate_tokens
maybe_compact = _mod.maybe_compact
run_compaction = _mod.run_compaction
should_compact = _mod.should_compact

# ── Test harness ───────────────────────────────────────────────────────────────

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


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _str_messages(n: int = 10) -> list[dict]:
    msgs: list[dict] = []
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        msgs.append({"role": role, "content": f"Message {i}: " + ("word " * 50)})
    return msgs


def _tool_messages() -> list[dict]:
    return [
        {"role": "user", "content": "Run a tool for me."},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Sure, calling the tool."},
                {
                    "type": "tool_use",
                    "name": "exec",
                    "input": {"command": "ls -la", "intent": "list files"},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "call_001",
                    "content": "total 12\ndrwxr-xr-x 2 user user 4096 Jan 1 00:00 .",
                }
            ],
        },
    ]


def _fake_openai_module(compacted_text: str = "## ORIGINAL TASK\nTest task\n") -> dict:
    """Return a sys.modules patch dict with a fake openai module."""
    openai_mod = types.ModuleType("openai")

    mock_response = MagicMock()
    mock_response.choices[0].message.content = compacted_text

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    openai_mod.OpenAI = MagicMock(return_value=mock_client)
    return {"openai": openai_mod}


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_extract_text_string() -> None:
    section("_extract_text — plain string content")
    result = _extract_text("hello world")
    check("returns string as-is", result == "hello world", repr(result))


def test_extract_text_list() -> None:
    section("_extract_text — list content with multiple block types")
    content = [
        {"type": "text", "text": "intro"},
        {"type": "tool_use", "name": "exec", "input": {"cmd": "ls"}},
        {"type": "tool_result", "tool_use_id": "x", "content": "output here"},
    ]
    result = _extract_text(content)
    check("contains text block", "intro" in result, result)
    check("contains tool name", "exec" in result, result)
    check("contains tool result", "output here" in result, result)


def test_serialize_history_string_messages() -> None:
    section("_serialize_history — string-content messages")
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]
    result = _serialize_history(msgs)
    check("[USER] present", "[USER]" in result, result[:120])
    check("[ASSISTANT] present", "[ASSISTANT]" in result, result[:120])
    check("content present", "hello" in result and "hi there" in result, result[:120])
    check("separator present", "---" in result, result[:120])


def test_serialize_history_tool_blocks() -> None:
    section("_serialize_history — tool_use and tool_result blocks")
    msgs = _tool_messages()
    result = _serialize_history(msgs)
    check("tool_use rendered", "tool_use: exec" in result, result[:300])
    check("tool input rendered", '"command"' in result, result[:300])
    check("tool_result rendered", "TOOL RESULT" in result, result[:300])
    check("result content present", "total 12" in result, result[:300])


def test_estimate_tokens_string_messages() -> None:
    section("estimate_tokens — string-content messages")
    msgs = [{"role": "user", "content": "a" * 400}]
    est = estimate_tokens(msgs)
    check("estimate > 0", est > 0, str(est))
    check("rough range [50, 500]", 50 <= est <= 500, str(est))


def test_estimate_tokens_list_messages() -> None:
    section("estimate_tokens — list-content messages")
    msgs = _tool_messages()
    est = estimate_tokens(msgs)
    check("estimate > 0", est > 0, str(est))


def test_estimate_tokens_tiktoken_fallback() -> None:
    section("estimate_tokens — tiktoken absent -> char fallback")
    msgs = [{"role": "user", "content": "x" * 1000}]
    with patch.dict(sys.modules, {"tiktoken": None}):
        est = estimate_tokens(msgs)
    # 1000 chars / 4 = 250 tokens (heuristic)
    check("fallback estimate = 250", est == 250, str(est))


def test_should_compact_below_threshold() -> None:
    section("should_compact — below threshold -> False")
    msgs = [{"role": "user", "content": "hi"}]
    config = CompactionConfig(max_context_tokens=400_000, threshold_ratio=0.87)
    needs, est, thresh = should_compact(msgs, config)
    check("needs_compact=False", not needs, f"est={est}, thresh={thresh}")
    check("threshold = 348000", thresh == 348_000, str(thresh))


def test_should_compact_above_threshold() -> None:
    section("should_compact — above threshold -> True")
    # Manufacture a message whose estimated token count exceeds threshold.
    # 400_000 * 0.87 = 348_000 tokens -> need > 348_000 * 4 = 1_392_000 chars.
    big_content = "w " * 700_000   # ~1.4M chars -> ~350k tokens (heuristic)
    msgs = [{"role": "user", "content": big_content}]
    config = CompactionConfig(max_context_tokens=400_000, threshold_ratio=0.87)
    with patch.dict(sys.modules, {"tiktoken": None}):
        needs, est, thresh = should_compact(msgs, config)
    check("needs_compact=True", needs, f"est={est}, thresh={thresh}")


def test_apply_compaction_basic() -> None:
    section("apply_compaction — 10 messages -> keep_last_n=2")
    msgs = _str_messages(10)
    compacted = "## ORIGINAL TASK\nDo something\n"
    config = CompactionConfig(keep_last_n=2)
    result = apply_compaction(msgs, compacted, config)
    # msgs[-2] is assistant (index 8), msgs[-1] is user (index 9)
    # tail[0].role == "user" -> bridge inserted
    check("result length = 4", len(result) == 4, str(len(result)))
    check("first msg is compacted", "[COMPACTED CONVERSATION STATE" in result[0]["content"])
    check("compacted role=user", result[0]["role"] == "user")
    check("bridge inserted", result[1]["role"] == "assistant", result[1].get("content", ""))
    check("last 2 tail preserved", result[-2]["content"] == msgs[-2]["content"])
    check("last tail preserved", result[-1]["content"] == msgs[-1]["content"])


def test_apply_compaction_tail_starts_assistant() -> None:
    section("apply_compaction — tail starts with assistant -> no bridge")
    # With keep_last_n=2, tail = msgs[-2:] = [msgs[3], msgs[4]]
    # msgs[3]=assistant -> tail[0].role="assistant" -> no bridge inserted
    msgs = [
        {"role": "user", "content": "hello"},         # 0
        {"role": "assistant", "content": "reply"},    # 1
        {"role": "user", "content": "next"},          # 2
        {"role": "assistant", "content": "step 3"},   # 3 <- tail[0]
        {"role": "user", "content": "done"},          # 4 <- tail[1]
    ]
    config = CompactionConfig(keep_last_n=2)
    result = apply_compaction(msgs, "## COMPACTED\n", config)
    # tail[0] is assistant -> no bridge; result = [compacted, assistant, user]
    check("result length = 3", len(result) == 3, str(len(result)))
    check("first tail = assistant", result[1]["role"] == "assistant", result[1]["role"])
    check("no bridge inserted", result[1]["content"] == "step 3", result[1]["content"])


def test_apply_compaction_fewer_than_keep_last_n() -> None:
    section("apply_compaction — fewer messages than keep_last_n")
    msgs = [{"role": "user", "content": "only one"}]
    config = CompactionConfig(keep_last_n=2)
    result = apply_compaction(msgs, "## COMPACTED\n", config)
    check("all original msgs in tail", any(m["content"] == "only one" for m in result))
    check("compacted block first", "[COMPACTED CONVERSATION STATE" in result[0]["content"])


def test_apply_compaction_marker_prefix() -> None:
    section("apply_compaction — compacted message has marker prefix")
    msgs = _str_messages(4)
    result = apply_compaction(msgs, "## ORIGINAL TASK\ntest\n")
    check("marker present", result[0]["content"].startswith(
        "[COMPACTED CONVERSATION STATE — history floor, not a user message]"
    ), result[0]["content"][:80])
    check("compacted text follows marker", "## ORIGINAL TASK" in result[0]["content"])


def test_maybe_compact_empty_history() -> None:
    section("maybe_compact — empty messages -> EMPTY_HISTORY error")
    _, result = maybe_compact([], api_key="test-key")
    check("status=error", result.status == "error", str(result))
    check("error_code=EMPTY_HISTORY", result.error_code == "EMPTY_HISTORY", str(result))


def test_maybe_compact_skipped() -> None:
    section("maybe_compact — below threshold -> Skipped")
    msgs = [{"role": "user", "content": "hi"}]
    _, result = maybe_compact(msgs, api_key="test-key")
    check("status=skipped", result.status == "skipped", str(result))
    check("estimated_tokens > 0", result.estimated_tokens > 0, str(result))


def test_maybe_compact_done() -> None:
    section("maybe_compact — above threshold -> Done (mocked API)")
    big_content = "w " * 700_000
    # 6 messages; apply_compaction with keep_last_n=2 produces 3 (compacted + 2 tail)
    msgs = [
        {"role": "user", "content": big_content},
        {"role": "assistant", "content": "response A"},
        {"role": "user", "content": "follow-up B"},
        {"role": "assistant", "content": "response C"},
        {"role": "user", "content": "follow-up D"},
        {"role": "assistant", "content": "response E"},
    ]
    config = CompactionConfig(max_context_tokens=400_000, threshold_ratio=0.87)
    fake_openai = _fake_openai_module("## ORIGINAL TASK\nTest\n")
    with patch.dict(sys.modules, {"tiktoken": None, **fake_openai}):
        new_msgs, result = maybe_compact(msgs, api_key="test-key", config=config)
    check("status=done", result.status == "done", str(result))
    check("messages_before=6", result.messages_before == 6, str(result))
    check("messages_after < messages_before", result.messages_after < result.messages_before,
          str(result))
    check("preview present", len(result.compacted_text_preview) > 0, str(result))
    check("new_msgs is different list", new_msgs is not msgs)


def test_maybe_compact_dependency_missing() -> None:
    section("maybe_compact — openai absent -> DEPENDENCY_MISSING")
    big_content = "w " * 700_000
    msgs = [{"role": "user", "content": big_content}]
    config = CompactionConfig(max_context_tokens=400_000, threshold_ratio=0.87)
    with patch.dict(sys.modules, {"tiktoken": None, "openai": None}):
        returned_msgs, result = maybe_compact(msgs, api_key="key", config=config)
    check("status=error", result.status == "error", str(result))
    check("error_code=DEPENDENCY_MISSING", result.error_code == "DEPENDENCY_MISSING", str(result))
    check("original msgs returned", returned_msgs is msgs)


def test_maybe_compact_api_error() -> None:
    section("maybe_compact — API raises -> API_ERROR")
    big_content = "w " * 700_000
    msgs = [{"role": "user", "content": big_content}]
    config = CompactionConfig(max_context_tokens=400_000, threshold_ratio=0.87)

    openai_mod = types.ModuleType("openai")
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("connection refused")
    openai_mod.OpenAI = MagicMock(return_value=mock_client)

    with patch.dict(sys.modules, {"tiktoken": None, "openai": openai_mod}):
        returned_msgs, result = maybe_compact(msgs, api_key="key", config=config)
    check("status=error", result.status == "error", str(result))
    check("error_code=API_ERROR", result.error_code == "API_ERROR", str(result))
    check("original msgs returned", returned_msgs is msgs)


def test_computer_level_prompt() -> None:
    section("run_compaction — level='computer' uses computer prompt")
    msgs = [{"role": "user", "content": "open the file manager"}]
    captured: list[dict] = []

    openai_mod = types.ModuleType("openai")
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "## BROWSING OBJECTIVE\nOpen file manager\n"

    def capture_create(**kwargs):
        captured.append(kwargs)
        return mock_response

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = capture_create
    openai_mod.OpenAI = MagicMock(return_value=mock_client)

    with patch.dict(sys.modules, {"openai": openai_mod}):
        result = run_compaction(msgs, api_key="key", level="computer")

    check("returned compacted text", "BROWSING OBJECTIVE" in result, result[:80])
    check("computer system prompt used", captured and
          "computer" in captured[0]["messages"][0]["content"].lower(),
          captured[0]["messages"][0]["content"][:80] if captured else "no call")


# ── Runner ─────────────────────────────────────────────────────────────────────

def run_all() -> None:
    print("\n" + "=" * 60)
    print("  memory_compaction — test suite")
    print("=" * 60)

    test_extract_text_string()
    test_extract_text_list()
    test_serialize_history_string_messages()
    test_serialize_history_tool_blocks()
    test_estimate_tokens_string_messages()
    test_estimate_tokens_list_messages()
    test_estimate_tokens_tiktoken_fallback()
    test_should_compact_below_threshold()
    test_should_compact_above_threshold()
    test_apply_compaction_basic()
    test_apply_compaction_tail_starts_assistant()
    test_apply_compaction_fewer_than_keep_last_n()
    test_apply_compaction_marker_prefix()
    test_maybe_compact_empty_history()
    test_maybe_compact_skipped()
    test_maybe_compact_done()
    test_maybe_compact_dependency_missing()
    test_maybe_compact_api_error()
    test_computer_level_prompt()

    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print(f"\n{'=' * 60}")
    print(f"  Results: {passed}/{total} passed")
    print("=" * 60)
    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    run_all()
