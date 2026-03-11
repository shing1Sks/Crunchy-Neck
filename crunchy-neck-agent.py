#!/usr/bin/env python3
"""
crunchy-neck-agent.py — Crunchy Neck personal agent, main entry point.

Usage:
    python crunchy-neck-agent.py [--medium terminal|telegram] [--workspace /path]

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
    parser = argparse.ArgumentParser(description="Crunchy Neck Agent")
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


def _send_thinking_snippet(content: str, *, medium: str, workspace_root: str, session_id: str) -> None:
    """Send first 2-3 lines of the model's text content as a thinking update."""
    snippet = _first_lines(content, n=3, max_chars=200)
    if snippet:
        _send_update(snippet, title="thinking", medium=medium, workspace_root=workspace_root, session_id=session_id)


def _send_tool_intent_update(tool_name: str, arguments_json: str, *, medium: str, workspace_root: str, session_id: str) -> None:
    """Send a brief update before a tool call: '[tool_name] <truncated args>'."""
    # Flatten args to a single readable line
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
        # Try to get meaningful text out of common result shapes
        if isinstance(data, dict):
            # Prefer 'output', 'content', 'stdout', 'text', or fall back to whole dict
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
        # Keep listening
        return _await_user_message(medium, workspace_root)
    else:
        print(f"[crunchy] receive error: {result}", file=sys.stderr)
        return None


# ── Session wrapup ────────────────────────────────────────────────────────────

def _run_wrapup(messages: list[dict], *, api_key: str, workspace_root: str) -> None:
    """Summarise session and write to MEMORY.md. Errors are logged, never fatal."""
    try:
        from agent_design.session_wrapup_log import run_session_wrapup_log
        result = run_session_wrapup_log(
            messages,
            api_key=api_key,
            workspace_root=workspace_root,
            today=date.today().isoformat(),
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

    Returns (messages, tools_were_called) — caller uses tools_were_called to decide
    whether a session wrapup is worth running.
    """
    from agent_design.memory_compaction import maybe_compact

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
                print(f"\nCrunchy: {assistant_msg.content}")
            break

        # ── Dispatch each tool call ───────────────────────────────────────────
        tools_were_called = True
        for tc in tool_calls:
            tool_name = tc.function.name
            arguments_json = tc.function.arguments or "{}"

            # Intent update (before call)
            _send_tool_intent_update(
                tool_name, arguments_json,
                medium=medium, workspace_root=workspace_root, session_id=agent_session_id,
            )

            print(
                f"[tool] {tool_name}({arguments_json[:100]}{'...' if len(arguments_json) > 100 else ''})",
                file=sys.stderr,
            )

            result_json = dispatch_fn(
                tool_name,
                arguments_json,
                workspace_root=workspace_root,
                agent_session_id=agent_session_id,
                medium=medium,
            )

            # Result update (after call)
            _send_tool_result_update(
                tool_name, result_json,
                medium=medium, workspace_root=workspace_root, session_id=agent_session_id,
            )

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_json,
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

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print(
            "[error] OPENAI_API_KEY is not set.\n"
            "        Add it to .env in the workspace root or set it in your environment.",
            file=sys.stderr,
        )
        sys.exit(1)

    # 2. Ensure workspace root (and thus agent_utils) is importable
    if workspace_root not in sys.path:
        sys.path.insert(0, workspace_root)

    # 3. Import heavy modules after env/path setup
    from agent_utils.system_prompt import build_system_prompt
    from agent_utils.tool_schemas import get_openai_tools
    from agent_utils.tool_dispatcher import dispatch
    from agent_utils.openai_helpers import make_client, chat_complete
    from agent_design.memory_compaction import CompactionConfig

    # 4. Build frozen system prompt
    system_prompt = build_system_prompt(
        workspace_root=workspace_root,
        medium=medium,
    )

    # 5. Initialise OpenAI client and tool list (reused for all sessions)
    client = make_client(api_key)
    tools = get_openai_tools()
    compaction_config = CompactionConfig()

    # 6. Persistent message history (accumulates across sessions)
    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    print(f"[crunchy] ready — medium={medium}, workspace={workspace_root}")

    # 7. Outer loop: one iteration = one user session
    while True:
        user_msg = _await_user_message(medium, workspace_root)

        if user_msg is None:
            print("[crunchy] shutting down.")
            break

        agent_session_id = "session_" + uuid.uuid4().hex[:8]
        messages.append({"role": "user", "content": user_msg})

        # Optional: notify agent is working (Telegram only — terminal user sees the prompt)
        if medium == "telegram":
            _send_update(
                "Working on it...",
                title="Crunchy",
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
            chat_fn=chat_complete,
            dispatch_fn=dispatch,
        )

        # Session wrapup — only when tools ran (skip pure chat turns)
        if tools_were_called:
            _run_wrapup(messages, api_key=api_key, workspace_root=workspace_root)


if __name__ == "__main__":
    main()
