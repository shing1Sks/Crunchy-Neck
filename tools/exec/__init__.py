"""exec tool — registration and JSON schema for LLM function calling."""
from __future__ import annotations

from .exec_tool import exec_command
from .exec_types import ExecParams

# ─── JSON Schema (OpenAI/Anthropic function-calling format) ───────────────────

TOOL_DEFINITION = {
    "name": "exec",
    "description": (
        "Run a shell command. Returns full output if done within yieldMs (default 10s), "
        "or session_id + tail if still running. "
        "Use process({action:'poll', session_id}) to check running commands.\n\n"
        "Rules:\n"
        "- intent: REQUIRED. Why you're running this. Specific. Min 10 chars.\n"
        "- yieldMs=0 to block forever (only for known-short commands).\n"
        "- background=true to return session_id immediately (servers, daemons).\n"
        "- Always check exit_code — non-zero means the command failed.\n"
        "- Use env dict for secrets, never embed them in the command string."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to run.",
            },
            "intent": {
                "type": "string",
                "description": (
                    "REQUIRED. Why you are running this command. "
                    "Be specific (min 10 characters). "
                    "Example: 'Installing project dependencies before running tests'."
                ),
            },
            "cwd": {
                "type": "string",
                "description": (
                    "Working directory. Absolute or relative to workspace root. "
                    "Defaults to workspace root."
                ),
            },
            "env": {
                "type": "object",
                "description": "Extra env vars merged on top of the process environment. Use this for secrets.",
                "additionalProperties": {"type": "string"},
            },
            "yieldMs": {
                "type": "integer",
                "description": (
                    "How long to wait (ms) before returning a session_id for async polling. "
                    "Default 10000. Set to 0 to block until the command finishes."
                ),
                "default": 10000,
            },
            "timeout": {
                "type": "integer",
                "description": (
                    "Hard kill deadline in ms (SIGTERM then SIGKILL). "
                    "Must be greater than yieldMs if both are set. Omit for no timeout."
                ),
            },
            "shell": {
                "type": "string",
                "enum": ["bash", "sh", "cmd", "powershell", "auto"],
                "description": "Shell to use. 'auto' detects from platform (default).",
                "default": "auto",
            },
            "stdin": {
                "type": "string",
                "description": "Text to feed to the process stdin at start. Pipe stays open for send-keys.",
            },
            "background": {
                "type": "boolean",
                "description": "Return session_id immediately without waiting. Use for servers and daemons.",
                "default": False,
            },
            "stripAnsi": {
                "type": "boolean",
                "description": "Strip ANSI escape codes from output. Default true.",
                "default": True,
            },
        },
        "required": ["command", "intent"],
    },
}


__all__ = ["exec_command", "ExecParams", "TOOL_DEFINITION"]
