#!/usr/bin/env python3
"""
open-crunchy-agent.py — OpenCrunchy personal agent, Groq/Kimi K2 variant.

Usage:
    python open-crunchy-agent.py [--medium terminal|telegram] [--workspace /path]

Mirrors crunchy-neck-agent.py exactly but runs on:
    Model:   moonshotai/kimi-k2-instruct-0905 (via Groq Cloud)
    API key: GROQ_API_KEY

Each "session" = one user message in → agent tool loop → final reply → wrapup.
History persists across sessions for the lifetime of the process.
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import date
from pathlib import Path


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OpenCrunchy Agent (Groq/Kimi K2)")
    parser.add_argument(
        "--medium",
        choices=["telegram", "terminal"],
        default="terminal",
        help="Communication medium (default: terminal)",
    )
    parser.add_argument(
        "--workspace",
        default=os.getcwd(),
        help="Workspace root directory (default: current working directory)",
    )
    return parser.parse_args()


def _load_env(workspace_root: str) -> None:
    """Load .env from workspace root; fallback to cwd."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = Path(workspace_root) / ".env"
    if env_path.is_file():
        load_dotenv(env_path)
    else:
        load_dotenv()


# ── Live update helpers (no AI — pure string formatting) ──────────────────────

def _first_lines(text: str, n: int = 3, max_chars: int = 200) -> str:
    """Return first n non-empty lines of text, capped at max_chars."""
    lines = [line for line in text.splitlines() if line.strip()][:n]
    result = "\n".join(lines)
    return result[:max_chars]


def _send_update(msg: str, title: str, *, medium: str, workspace_root: str, session_id: str) -> None:
    """Fire-and-forget update ping. Never raises."""
    try:
        from tools import ping_command, PingParams
        params = PingParams(
            msg=msg,
            type="update",
            medium=medium,
            title=title,
            edit_last_update=True,
        )
        ping_command(params, workspace_root=workspace_root, agent_session_id=session_id)
    except Exception:  # noqa: BLE001
        pass


def _send_final_response(content: str, *, medium: str, workspace_root: str, session_id: str) -> None:
    """Send the agent's final answer as a persistent 'chat' message on Telegram."""
    if medium != "telegram":
        return
    try:
        from tools import ping_command, PingParams
        params = PingParams(
            msg=content,
            type="chat",
            medium="telegram",
        )
        ping_command(params, workspace_root=workspace_root, agent_session_id=session_id)
    except Exception:  # noqa: BLE001
        pass


def _delete_status_message(*, workspace_root: str) -> None:
    """Delete the last 'Working on it...' update message from Telegram, if any."""
    try:
        from comm_channels._state import load_state, save_state
        from comm_channels.telegram.config import load_config
        from comm_channels.telegram.client import delete_message
        state = load_state(workspace_root)
        msg_id: int | None = state.get("last_update_message_id")
        if msg_id is None:
            return
        cfg = load_config(workspace_root)
        delete_message(cfg.bot_token, cfg.chat_id, msg_id)
        state.pop("last_update_message_id", None)
        save_state(workspace_root, state)
    except Exception:  # noqa: BLE001
        pass


def _send_thinking_snippet(content: str, *, medium: str, workspace_root: str, session_id: str) -> None:
    """Send first 2-3 lines of the model's text content as a thinking update."""
    snippet = _first_lines(content, n=3, max_chars=200)
    if snippet:
        _send_update(snippet, title="thinking", medium=medium, workspace_root=workspace_root, session_id=session_id)


def _send_tool_intent_update(tool_name: str, arguments_json: str, *, medium: str, workspace_root: str, session_id: str) -> None:
    """Send a brief update before a tool call: '[tool_name] <truncated args>'."""
    args_flat = arguments_json.replace("\n", " ").replace("  ", " ")
    if len(args_flat) > 120:
        args_flat = args_flat[:117] + "..."
    msg = f"[{tool_name}] {args_flat}"
    _send_update(msg, title="tool", medium=medium, workspace_root=workspace_root, session_id=session_id)


def _send_tool_result_update(tool_name: str, result_json: str, *, medium: str, workspace_root: str, session_id: str) -> None:
    """Send first 3 non-empty lines of the tool result as an update."""
    import json as _json
    try:
        data = _json.loads(result_json)
        if isinstance(data, dict):
            text = (
                data.get("output")
                or data.get("content")
                or data.get("stdout")
                or data.get("text")
                or data.get("error")
                or _json.dumps(data, default=str)
            )
            text = str(text)
        else:
            text = str(data)
    except Exception:  # noqa: BLE001
        text = result_json

    snippet = _first_lines(text, n=3, max_chars=200)
    if snippet:
        msg = f"[{tool_name}] → {snippet}"
        _send_update(msg, title="result", medium=medium, workspace_root=workspace_root, session_id=session_id)


# ── Session initiation ────────────────────────────────────────────────────────

def _await_user_message(medium: str, workspace_root: str) -> str | None:
    """
    Block until the user sends a message. Returns None to signal shutdown.

    terminal: simple input() — lowest overhead, clearest UX.
    telegram: long-poll via ping_command query:msg with a 1-hour timeout.
              On timeout it loops and keeps waiting (agent is always listening).
    """
    if medium == "terminal":
        try:
            msg = input("\nYou: ").strip()
            return msg or None
        except (EOFError, KeyboardInterrupt):
            return None

    # Telegram path
    from tools import ping_command, PingParams
    listen_id = "listen_" + uuid.uuid4().hex[:8]
    params = PingParams(
        msg="Listening...",
        type="query:msg",
        medium="telegram",
        timeout=3600,
    )
    result = ping_command(params, workspace_root=workspace_root, agent_session_id=listen_id)
    if result.status == "response":
        return result.response
    elif result.status == "error" and result.error_code == "timeout":
        return _await_user_message(medium, workspace_root)
    else:
        print(f"[open-crunchy] receive error: {result}", file=sys.stderr)
        return None


# ── Session wrapup ────────────────────────────────────────────────────────────

def _run_wrapup(
    messages: list[dict],
    *,
    api_key: str,
    workspace_root: str,
    wrapup_config,
) -> None:
    """Summarise session and write to MEMORY.md. Errors are logged, never fatal."""
    try:
        from agent_design.session_wrapup_log import run_session_wrapup_log
        result = run_session_wrapup_log(
            messages,
            api_key=api_key,
            workspace_root=workspace_root,
            today=date.today().isoformat(),
            config=wrapup_config,
        )
        if result.status == "error":
            print(f"[wrapup error] {result.error_message}", file=sys.stderr)
        else:
            print(f"[wrapup] logged to {result.memory_md_path}", file=sys.stderr)
    except Exception as e:  # noqa: BLE001
        print(f"[wrapup exception] {e}", file=sys.stderr)


# ── Agent turn (inner tool-call loop) ────────────────────────────────────────

MAX_TOOL_ROUNDS = 40


def _run_agent_turn(
    messages: list[dict],
    *,
    client,
    tools: list[dict],
    api_key: str,
    workspace_root: str,
    agent_session_id: str,
    medium: str,
    compaction_config,
    chat_fn,
    dispatch_fn,
) -> tuple[list[dict], bool]:
    """
    Run the inner tool-call loop for one user session.

    Loop: compact → call model → if tool calls dispatch them → repeat.
    Exits when model produces a text response with no tool calls, or MAX_TOOL_ROUNDS hit.

    Returns (messages, tools_were_called).
    """
    from agent_design.memory_compaction import maybe_compact
    from agent_utils.tool_dispatcher import ImageDispatchResult

    tools_were_called = False

    for _ in range(MAX_TOOL_ROUNDS):
        # ── Compact if approaching context limit ─────────────────────────────
        messages, compact_result = maybe_compact(
            messages,
            api_key=api_key,
            level="orchestrator",
            config=compaction_config,
        )
        if compact_result.status == "done":
            print(
                f"[compaction] {compact_result.messages_before} → {compact_result.messages_after} messages",
                file=sys.stderr,
            )
        elif compact_result.status == "error":
            print(f"[compaction error] {compact_result.error_message}", file=sys.stderr)

        # ── Call the model ────────────────────────────────────────────────────
        try:
            response = chat_fn(client, messages=messages, tools=tools)
        except Exception as e:  # noqa: BLE001
            print(f"[api error] {e}", file=sys.stderr)
            messages.append({"role": "assistant", "content": f"[internal error — API call failed: {e}]"})
            break

        choice = response.choices[0]
        assistant_msg = choice.message

        # ── Thinking snippet (model text alongside / before tool calls) ───────
        if assistant_msg.content:
            _send_thinking_snippet(
                assistant_msg.content,
                medium=medium,
                workspace_root=workspace_root,
                session_id=agent_session_id,
            )

        # ── Build assistant message dict for history ──────────────────────────
        msg_dict: dict = {"role": "assistant", "content": assistant_msg.content}
        tool_calls = assistant_msg.tool_calls  # list[ToolCall] | None

        if tool_calls:
            msg_dict["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ]

        messages.append(msg_dict)

        # ── No tool calls → model is done for this turn ───────────────────────
        if not tool_calls:
            if assistant_msg.content:
                print(f"\nOpenCrunchy: {assistant_msg.content}")
                if medium == "telegram":
                    _delete_status_message(workspace_root=workspace_root)
                _send_final_response(
                    assistant_msg.content,
                    medium=medium,
                    workspace_root=workspace_root,
                    session_id=agent_session_id,
                )
            break

        # ── Dispatch each tool call ───────────────────────────────────────────
        tools_were_called = True
        pending_image_blocks: list[dict] = []

        for tc in tool_calls:
            tool_name = tc.function.name
            arguments_json = tc.function.arguments or "{}"

            _send_tool_intent_update(
                tool_name, arguments_json,
                medium=medium, workspace_root=workspace_root, session_id=agent_session_id,
            )

            print(
                f"[tool] {tool_name}({arguments_json[:100]}{'...' if len(arguments_json) > 100 else ''})",
                file=sys.stderr,
            )

            result_content = dispatch_fn(
                tool_name,
                arguments_json,
                workspace_root=workspace_root,
                agent_session_id=agent_session_id,
                medium=medium,
            )

            if isinstance(result_content, ImageDispatchResult):
                tool_str = result_content.tool_text
                pending_image_blocks.append(result_content.image_block)
            else:
                tool_str = result_content

            _send_tool_result_update(
                tool_name, tool_str,
                medium=medium, workspace_root=workspace_root, session_id=agent_session_id,
            )

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_str,
            })

        if pending_image_blocks:
            messages.append({
                "role": "user",
                "content": pending_image_blocks,
            })

    else:
        # Exceeded MAX_TOOL_ROUNDS
        messages.append({
            "role": "assistant",
            "content": "[agent: exceeded maximum tool call rounds — stopping to avoid infinite loop]",
        })
        print("[warning] hit MAX_TOOL_ROUNDS", file=sys.stderr)

    return messages, tools_were_called


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()
    workspace_root: str = str(Path(args.workspace).resolve())
    medium: str = args.medium

    # 1. Load environment
    _load_env(workspace_root)

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print(
            "[error] GROQ_API_KEY is not set.\n"
            "        Add it to .env in the workspace root or set it in your environment.",
            file=sys.stderr,
        )
        sys.exit(1)

    # 2. Ensure workspace root is importable
    if workspace_root not in sys.path:
        sys.path.insert(0, workspace_root)

    # 3. Import heavy modules after env/path setup
    from agent_utils.system_prompt import build_system_prompt
    from agent_utils.tool_schemas import get_openai_tools
    from agent_utils.tool_dispatcher import dispatch
    from agent_utils.groq_helpers import make_groq_client, groq_chat_complete, GROQ_MODEL, GROQ_BASE_URL
    from agent_design.memory_compaction import CompactionConfig
    from agent_design.session_wrapup_log import SessionWrapupConfig

    # 4. Build frozen system prompt
    system_prompt = build_system_prompt(
        workspace_root=workspace_root,
        agent_name="OpenCrunchy",
        medium=medium,
        model=GROQ_MODEL,
    )

    # 5. Initialise Groq client and tool list (reused for all sessions)
    client = make_groq_client(api_key)
    tools = get_openai_tools()

    # Groq/Kimi K2 configs — 262K context window, no reasoning_effort
    compaction_config = CompactionConfig(
        max_context_tokens=262_144,
        threshold_ratio=0.88,        # trigger at ~230K; leaves 32K headroom for 16K output + buffer
        keep_last_n=2,
        model=GROQ_MODEL,
        compaction_max_tokens=4096,
        base_url=GROQ_BASE_URL,
    )
    wrapup_config = SessionWrapupConfig(
        model=GROQ_MODEL,
        max_tokens=512,
        base_url=GROQ_BASE_URL,
    )

    # 6. Persistent message history (accumulates across sessions)
    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    print(f"[open-crunchy] ready — model={GROQ_MODEL}, medium={medium}, workspace={workspace_root}")

    # 7. Outer loop: one iteration = one user session
    while True:
        user_msg = _await_user_message(medium, workspace_root)

        if user_msg is None:
            print("[open-crunchy] shutting down.")
            break

        agent_session_id = "session_" + uuid.uuid4().hex[:8]
        messages.append({"role": "user", "content": user_msg})

        if medium == "telegram":
            _send_update(
                "Working on it...",
                title="OpenCrunchy",
                medium=medium,
                workspace_root=workspace_root,
                session_id=agent_session_id,
            )

        # Inner tool-call loop
        messages, tools_were_called = _run_agent_turn(
            messages,
            client=client,
            tools=tools,
            api_key=api_key,
            workspace_root=workspace_root,
            agent_session_id=agent_session_id,
            medium=medium,
            compaction_config=compaction_config,
            chat_fn=groq_chat_complete,
            dispatch_fn=dispatch,
        )

        if medium == "telegram":
            _delete_status_message(workspace_root=workspace_root)

        # Session wrapup — only when tools ran (skip pure chat turns)
        if tools_were_called:
            _run_wrapup(
                messages,
                api_key=api_key,
                workspace_root=workspace_root,
                wrapup_config=wrapup_config,
            )


if __name__ == "__main__":
    main()
