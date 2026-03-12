"""
agent.py — main Responses API loop for Scout (computer agent).

Public API:
    run(config, *, workspace_root, agent_session_id, api_key) -> AgentResult

Loop: compact → call model → execute computer_call actions → take screenshot →
      parse DONE/NEED_INPUT/FAILED signals → repeat.

Logs every turn to .agent/scout/logs/<date>_<session_id>.jsonl via ScoutLog.
"""
from __future__ import annotations

import asyncio
import sys
from typing import Any

import openai

from comm_channels.ping_tool import ping_user
from comm_channels.ping_types import PingParams, PingResultResponse
from computer_agent.actions import execute_action
from computer_agent.browser import launch_chrome
from computer_agent.compaction import maybe_compact
from computer_agent.models import AgentResult, AgentResultDone, AgentResultFailed, RunConfig
from computer_agent.prompts import get_system_prompt
from computer_agent.scout_log import ScoutLog
from computer_agent.screenshot import take_screenshot

_MODEL = "gpt-5.4"


# ─── Public entry point ───────────────────────────────────────────────────────

def run(
    config: RunConfig,
    *,
    workspace_root: str,
    agent_session_id: str,
    api_key: str,
) -> AgentResult:
    """Synchronous entry point — wraps the async loop."""
    return asyncio.run(
        _run_async(
            config,
            workspace_root=workspace_root,
            agent_session_id=agent_session_id,
            api_key=api_key,
        )
    )


# ─── Async loop ───────────────────────────────────────────────────────────────

async def _run_async(
    config: RunConfig,
    *,
    workspace_root: str,
    agent_session_id: str,
    api_key: str,
) -> AgentResult:
    log = ScoutLog(workspace_root=workspace_root, agent_session_id=agent_session_id)
    log.session_start(task=config.task, mode=config.mode, max_turns=config.max_turns)
    _update(f"[scout] log → {log.log_path}", config, workspace_root, agent_session_id)

    client = openai.OpenAI(api_key=api_key)

    # ── Launch browser if needed ─────────────────────────────────────────────
    chrome_proc = None
    if config.mode == "browser" and config.launch_browser:
        try:
            chrome_proc = launch_chrome(profile_name=config.profile)
            log.chrome_launch(profile=config.profile)
            _update(
                f"[scout] Chrome ready (profile: {config.profile})",
                config, workspace_root, agent_session_id,
            )
        except Exception as exc:
            log.chrome_launch_error(error=str(exc))
            log.session_end(status="failed", turns_used=0, reason=f"Chrome launch failed: {exc}")
            return AgentResultFailed(reason=f"Chrome launch failed: {exc}")

    # ── CUA tool definition (GA format — no extra fields) ────────────────────
    computer_tool: dict[str, Any] = {"type": "computer"}

    # ── Seed input_list ──────────────────────────────────────────────────────
    b64_init, _ = take_screenshot()
    system_prompt = get_system_prompt(config.mode)
    input_list: list[dict] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": config.task},
                {"type": "input_image", "image_url": f"data:image/png;base64,{b64_init}"},
            ],
        },
    ]

    result: AgentResult = AgentResultFailed(reason="max_turns exceeded")

    try:
        for turn in range(config.max_turns):
            # ── Compact if approaching context limit ─────────────────────────
            from computer_agent.compaction import estimate_tokens
            est = estimate_tokens(input_list)
            log.turn_start(turn=turn, input_list_len=len(input_list), estimated_tokens=est)

            input_list, cr = maybe_compact(input_list, api_key=api_key)
            if cr.status == "done":
                log.compaction_done(
                    turn=turn,
                    tokens_before=cr.tokens_before,
                    items_before=cr.items_before,
                    items_after=cr.items_after,
                )
                _update(
                    f"[scout] compacted context ({cr.items_before}→{cr.items_after} items)",
                    config, workspace_root, agent_session_id,
                )
            elif cr.status == "skipped":
                log.compaction_skipped(turn=turn, estimated_tokens=cr.estimated_tokens)
            elif cr.status == "error":
                log.compaction_error(turn=turn, detail=cr.detail)
                print(f"[scout compaction error] {cr.detail}", file=sys.stderr)

            # ── Call model ───────────────────────────────────────────────────
            try:
                response = client.responses.create(
                    model=_MODEL,
                    tools=[computer_tool],
                    input=input_list,
                )
            except Exception as exc:
                log.api_error(turn=turn, error=str(exc))
                print(f"[scout api error] {exc}", file=sys.stderr)
                result = AgentResultFailed(reason=f"API error: {exc}")
                break

            # Log summary of what model returned
            item_types = [getattr(it, "type", type(it).__name__) for it in response.output]
            log.model_response(turn=turn, item_types=item_types)

            # ── Process output items ─────────────────────────────────────────
            did_action = False
            signal: str | None = None
            last_text: str = ""

            for item in response.output:
                item_type = getattr(item, "type", None)

                # ── computer_call → execute all actions → one screenshot ─────
                if item_type == "computer_call":
                    call_id = item.call_id

                    # GA: computer_call has actions[] (array), not single action
                    raw_actions = getattr(item, "actions", None) or getattr(item, "action", None)
                    if raw_actions is None:
                        raw_actions = []
                    if isinstance(raw_actions, dict):
                        raw_actions = [raw_actions]  # legacy single-action fallback

                    actions_list = [
                        a if isinstance(a, dict) else _to_dict(a)
                        for a in raw_actions
                    ]

                    # Echo the original computer_call item back (preserves all GA fields)
                    input_list.append(_to_dict(item))

                    # Execute each action in the batch
                    for action_dict in actions_list:
                        log.action_execute(turn=turn, action=action_dict)
                        try:
                            desc = await execute_action(action_dict)
                            log.action_result(turn=turn, desc=desc)
                        except Exception as exc:
                            atype = action_dict.get("type", "unknown")
                            log.action_error(turn=turn, action_type=atype, error=str(exc))
                            desc = f"action error: {exc}"
                        _update(f"[scout] {desc}", config, workspace_root, agent_session_id)

                    # One screenshot after the full batch
                    b64, _ = take_screenshot()
                    log.screenshot_taken(turn=turn)
                    input_list.append({
                        "type": "computer_call_output",
                        "call_id": call_id,
                        "output": {
                            "type": "computer_screenshot",
                            "image_url": f"data:image/png;base64,{b64}",
                        },
                    })
                    did_action = True

                # ── Text / message output → check for signals ────────────────
                elif item_type in ("text", "message") or hasattr(item, "content"):
                    text = _extract_text(item)
                    if text:
                        last_text = text
                        log.text_output(turn=turn, text=text)
                        input_list.append({"role": "assistant", "content": text})
                        signal = _parse_signal(text)
                        if signal:
                            log.signal_detected(
                                turn=turn,
                                signal=signal,
                                payload=_payload(text, signal),
                            )

            # ── Handle terminal signals ──────────────────────────────────────
            if signal == "DONE":
                deliverable = _payload(last_text, "DONE")
                result = AgentResultDone(deliverable=deliverable)
                break

            if signal == "FAILED":
                reason = _payload(last_text, "FAILED")
                result = AgentResultFailed(reason=reason)
                break

            if signal == "NEED_INPUT":
                question = _payload(last_text, "NEED_INPUT")
                log.need_input_sent(turn=turn, question=question)
                user_reply = _ask_user(question, config, workspace_root, agent_session_id)
                if user_reply is None:
                    log.need_input_timeout(turn=turn)
                    result = AgentResultFailed(reason="user query timed out")
                    break
                log.need_input_reply(turn=turn, reply=user_reply)
                input_list.append({"role": "user", "content": user_reply})
                continue  # next turn

            # ── No signal, no action ──────────────────────────────────────────
            if not did_action and signal is None:
                if last_text:
                    # Model returned content without a DONE: prefix — treat as implicit DONE
                    log.implicit_done(turn=turn, text=last_text)
                    result = AgentResultDone(deliverable=last_text)
                else:
                    log.no_progress(turn=turn)
                    print(
                        f"[scout] turn {turn}: no action or signal — stopping",
                        file=sys.stderr,
                    )
                    result = AgentResultFailed(
                        reason="no progress — agent produced no action or signal"
                    )
                break

    finally:
        if chrome_proc is not None:
            chrome_proc.terminate()
        log.session_end(
            status=result.status,
            turns_used=turn if "turn" in dir() else 0,
            deliverable=getattr(result, "deliverable", None),
            reason=getattr(result, "reason", None),
        )

    return result


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _update(msg: str, config: RunConfig, workspace_root: str, session_id: str) -> None:
    ping_user(
        PingParams(msg=msg, type="update", medium=config.medium, edit_last_update=True),
        workspace_root=workspace_root,
        agent_session_id=session_id,
    )


def _ask_user(
    question: str,
    config: RunConfig,
    workspace_root: str,
    session_id: str,
) -> str | None:
    pr = ping_user(
        PingParams(
            msg=question or "Scout needs input to continue.",
            type="query:msg",
            medium=config.medium,
            timeout=300,
        ),
        workspace_root=workspace_root,
        agent_session_id=session_id,
    )
    if isinstance(pr, PingResultResponse):
        return pr.response
    return None


def _parse_signal(text: str) -> str | None:
    t = text.strip()
    if t.startswith("DONE"):       return "DONE"
    if t.startswith("FAILED"):     return "FAILED"
    if t.startswith("NEED_INPUT"): return "NEED_INPUT"
    return None


def _payload(text: str, prefix: str) -> str:
    """Return the text after 'PREFIX:' / 'PREFIX ' on the first line."""
    line = text.strip().split("\n")[0]
    after = line[len(prefix):].lstrip(": ").strip()
    return after or text.strip()


def _extract_text(item: Any) -> str:
    """Pull plain text from a Responses API output item."""
    # Direct text attribute (TextOutputItem)
    t = getattr(item, "text", None)
    if isinstance(t, str):
        return t
    # Content list (MessageOutputItem)
    content = getattr(item, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            getattr(b, "text", "")
            for b in content
            if getattr(b, "type", "") == "output_text"
        )
    return ""


def _to_dict(obj: Any) -> dict:
    """Convert a pydantic/dataclass-like action object to a plain dict."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
    return {}
