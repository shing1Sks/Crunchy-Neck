"""process tool — registration and JSON schema for LLM function calling."""
from __future__ import annotations

from .process_tool import process_command
from .proc_types import ProcessParams

TOOL_DEFINITION = {
    "name": "process",
    "description": (
        "Manage long-running processes started by exec(). "
        "Use poll to check status, kill to stop, send-keys/submit to send input, "
        "list to see all sessions, get-log for full output. "
        "If a process produces no output and appears stuck, it is likely waiting for stdin — "
        "kill it and re-run with exec's `stdin` parameter to pass the input at launch."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["poll", "kill", "send-keys", "submit", "close-stdin", "list", "get-log"],
                "description": (
                    "Action to perform. "
                    "poll=check status/output. kill=terminate. "
                    "send-keys=write text to stdin (no auto newline unless press_enter=true). "
                    "submit=write text + newline (for interactive yes/no prompts). "
                    "close-stdin=send EOF to stdin (unblocks programs that read until EOF like --body-file -). "
                    "list=list sessions. get-log=read full stdout/stderr log."
                ),
            },
            "session_id": {
                "type": "string",
                "description": "The session_id returned by exec(). Required for all actions except 'list'.",
            },
            "keys": {
                "type": "string",
                "description": (
                    "Text to send to the process stdin. Required for send-keys and submit. "
                    "For multi-line content (e.g. an email body), call send-keys once per line "
                    "then call close-stdin to send EOF. "
                    "Prefer passing the full content via exec's `stdin` parameter at launch instead."
                ),
            },
            "press_enter": {
                "type": "boolean",
                "description": "Append newline after keys (default true). Only for send-keys.",
                "default": True,
            },
            "lines": {
                "type": "integer",
                "description": "Number of tail lines to return in poll response. Default 50.",
                "default": 50,
            },
            "filter": {
                "type": "string",
                "enum": ["running", "done", "killed", "all"],
                "description": "Filter sessions by state for 'list' action. Default 'all'.",
                "default": "all",
            },
            "stream": {
                "type": "string",
                "enum": ["stdout", "stderr"],
                "description": "Which stream to read for get-log. Default 'stdout'.",
                "default": "stdout",
            },
            "offset": {
                "type": "integer",
                "description": "Byte offset for get-log pagination. Default 0.",
                "default": 0,
            },
            "limit": {
                "type": "integer",
                "description": "Max bytes to return for get-log. Default 32768.",
                "default": 32768,
            },
        },
        "required": ["action"],
    },
}

__all__ = ["process_command", "ProcessParams", "TOOL_DEFINITION"]
