"""process() — companion to exec().

Routes poll / kill / send-keys / submit / close-stdin / list / get-log
actions to the shared ProcessSupervisor singleton.
"""
from __future__ import annotations

import time

from ..exec.supervisor import get_supervisor
from .proc_types import ProcessParams


def process_command(params: ProcessParams) -> dict:
    supervisor = get_supervisor()

    match params.action:
        case "poll":
            if not params.session_id:
                return _err("session_id is required for poll")
            result = supervisor.poll(params.session_id)
            if result is None:
                return _err(f"Session '{params.session_id}' not found or expired.", code="SESSION_EXPIRED")
            # Shape the poll result for the agent.
            state = result["state"]
            base = {
                "action": "poll",
                "session_id": params.session_id,
                "state": state,
                "pid": result["pid"],
                "duration_ms": result["duration_ms"],
                "exit_code": result["exit_code"],
                "tail": result["tail"],
                "tail_lines": result["tail_lines"],
                "lines_so_far": result["lines_so_far"],
            }
            if state in ("done", "killed"):
                base["hint"] = (
                    f"Process finished (exit_code={result['exit_code']}). "
                    "You can call process({action:'get-log', session_id}) for full output."
                )
            else:
                base["hint"] = (
                    f"Process still running ({result['duration_ms']}ms elapsed). "
                    f"Poll again or call process({{action:'kill', session_id:'{params.session_id}'}}) to stop."
                )
            return base

        case "kill":
            if not params.session_id:
                return _err("session_id is required for kill")
            ok = supervisor.kill(params.session_id, reason="user")
            if not ok:
                return _err(f"Session '{params.session_id}' not found or already finished.", code="SESSION_EXPIRED")
            return {
                "action": "kill",
                "session_id": params.session_id,
                "killed": True,
                "hint": "Process killed. Poll once to confirm final state.",
            }

        case "send-keys":
            if not params.session_id:
                return _err("session_id is required for send-keys")
            if params.keys is None:
                return _err("keys is required for send-keys")
            ok = supervisor.send_input(params.session_id, params.keys, press_enter=params.press_enter)
            if not ok:
                return _err(f"Could not write to stdin for session '{params.session_id}'.", code="STDIN_CLOSED")
            return {
                "action": "send-keys",
                "session_id": params.session_id,
                "sent": params.keys + ("\n" if params.press_enter else ""),
                "ok": True,
            }

        case "submit":
            # Alias for send-keys with press_enter=True.
            if not params.session_id:
                return _err("session_id is required for submit")
            if params.keys is None:
                return _err("keys is required for submit")
            ok = supervisor.send_input(params.session_id, params.keys, press_enter=True)
            if not ok:
                return _err(f"Could not submit to session '{params.session_id}'.", code="STDIN_CLOSED")
            return {
                "action": "submit",
                "session_id": params.session_id,
                "submitted": params.keys,
                "ok": True,
            }

        case "close-stdin":
            if not params.session_id:
                return _err("session_id is required for close-stdin")
            ok = supervisor.close_stdin(params.session_id)
            return {
                "action": "close-stdin",
                "session_id": params.session_id,
                "ok": ok,
            }

        case "list":
            sessions = supervisor.list_sessions(filter_state=params.filter)
            return {
                "action": "list",
                "filter": params.filter,
                "sessions": sessions,
                "count": len(sessions),
            }

        case "get-log":
            if not params.session_id:
                return _err("session_id is required for get-log")
            content = supervisor.get_log(
                params.session_id,
                stream=params.stream,
                offset=params.offset,
                limit=params.limit,
            )
            if content is None:
                return _err(f"Session '{params.session_id}' not found or expired.", code="SESSION_EXPIRED")
            return {
                "action": "get-log",
                "session_id": params.session_id,
                "stream": params.stream,
                "offset": params.offset,
                "content": content,
                "bytes_returned": len(content.encode("utf-8")),
            }

        case _:
            return _err(f"Unknown action: {params.action}")


def _err(message: str, code: str = "INVALID_REQUEST") -> dict:
    return {"ok": False, "error_code": code, "error_message": message}
