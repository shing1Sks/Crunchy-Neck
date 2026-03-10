"""Shell detection and cross-platform invocation builder."""
from __future__ import annotations

import os
import shutil
import sys
from typing import Literal

ShellChoice = Literal["bash", "sh", "cmd", "powershell", "auto"]


def resolve_shell(shell: ShellChoice) -> str:
    """Return the concrete shell name to use (never 'auto')."""
    if shell != "auto":
        return shell
    if sys.platform == "win32":
        return "cmd"
    # Unix: prefer bash, fall back to sh.
    return "bash" if shutil.which("bash") else "sh"


def build_argv(command: str, shell: str) -> list[str]:
    """Return the argv list to pass to subprocess for the given shell + command."""
    match shell:
        case "bash":
            return ["bash", "-c", command]
        case "sh":
            return ["sh", "-c", command]
        case "cmd":
            return ["cmd.exe", "/d", "/s", "/c", command]
        case "powershell":
            return ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command]
        case "pwsh":
            return ["pwsh", "-NoProfile", "-NonInteractive", "-Command", command]
        case _:
            # Fallback: treat shell as a binary name.
            return [shell, "-c", command]


def verify_shell_exists(shell: str) -> bool:
    """Return True if the shell binary is available on PATH."""
    if sys.platform == "win32" and shell == "cmd":
        return True  # cmd.exe is always present on Windows.
    return shutil.which(shell) is not None


def build_env(
    user_env: dict[str, str],
    session_id: str,
    exec_id: str,
    workspace_root: str,
) -> dict[str, str]:
    """Build the final environment dict for the subprocess.

    Merge order: os.environ < injected_session_vars < user_env
    (user_env has already been sanitized by safety.sanitize_env)
    """
    injected = {
        "AGENT_SESSION_ID": session_id,
        "AGENT_EXEC_ID": exec_id,
        "AGENT_WORKSPACE": workspace_root,
        "CI": "1",
        "NO_COLOR": "1",
        "TERM": "dumb",
    }

    env = {**os.environ, **injected, **user_env}

    # Normalize line endings don't matter for env, but ensure no None values.
    return {k: v for k, v in env.items() if v is not None}
