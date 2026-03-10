"""exec() — main entry point.

Flow:
  validate params → safety checks → resolve shell/cwd/env
  → register with supervisor → spawn subprocess
  → wait up to yieldMs → return appropriate ExecResult
"""
from __future__ import annotations

import os
import subprocess
import time
import threading
import uuid
from pathlib import Path

from .audit import log_event
from .output import strip_ansi, truncate
from .safety import check_blocklist, sanitize_env, validate_intent
from .shell import build_argv, build_env, resolve_shell, verify_shell_exists
from .supervisor import get_supervisor
from .exec_types import (
    ExecBase,
    ExecParams,
    ExecResult,
    ExecResultDone,
    ExecResultError,
    ExecResultFailed,
    ExecResultKilled,
    ExecResultRunning,
)

# Exit code → human-readable diagnosis.
_EXIT_DIAGNOSIS: dict[int, str] = {
    1:   "Generic error — check stderr",
    2:   "Shell built-in misuse (bash syntax error)",
    126: "Permission denied — file is not executable",
    127: "Command not found — check PATH or install the binary",
    128: "Invalid exit argument",
    130: "Terminated by Ctrl+C (SIGINT)",
    137: "Killed by OS (OOM or explicit SIGKILL) — possible memory issue",
    139: "Segmentation fault — likely a bug in the program",
    143: "Killed by SIGTERM (graceful shutdown)",
}


def _make_session_id() -> str:
    return "exec_" + uuid.uuid4().hex[:8]


def _base(
    session_id: str,
    command: str,
    started_at: float,
    cwd: str,
    pid: int | None,
) -> dict:
    return dict(
        session_id=session_id,
        command=command,
        started_at=started_at,
        duration_ms=int((time.time() - started_at) * 1000),
        cwd=cwd,
        pid=pid,
    )


def exec_command(
    params: ExecParams,
    *,
    workspace_root: str,
    agent_session_id: str,
) -> ExecResult:
    session_id = _make_session_id()
    started_at = time.time()

    # ── 1. Intent validation ───────────────────────────────────────────────
    intent_error = validate_intent(params.intent, params.command)
    if intent_error:
        log_event(
            event="exec.blocked",
            session_id=session_id,
            agent_session_id=agent_session_id,
            command=params.command,
            intent=params.intent,
            cwd=workspace_root,
            shell=params.shell,
            workspace_root=workspace_root,
            blocked_reason=intent_error,
        )
        return ExecResultError(
            **_base(session_id, params.command, started_at, workspace_root, None),
            error_code=intent_error,  # type: ignore[arg-type]
            error_message=f"Intent rejected ({intent_error}): provide a specific description of why you're running this command.",
        )

    # ── 2. Blocklist check ─────────────────────────────────────────────────
    blocked_pattern = check_blocklist(params.command)
    if blocked_pattern:
        log_event(
            event="exec.blocked",
            session_id=session_id,
            agent_session_id=agent_session_id,
            command=params.command,
            intent=params.intent,
            cwd=workspace_root,
            shell=params.shell,
            workspace_root=workspace_root,
            blocked_reason=f"BLOCKED_COMMAND: {blocked_pattern}",
        )
        return ExecResultError(
            **_base(session_id, params.command, started_at, workspace_root, None),
            error_code="BLOCKED_COMMAND",
            error_message="Command matches safety blocklist and cannot be executed.",
            blocked_pattern=blocked_pattern,
        )

    # ── 3. Resolve shell ───────────────────────────────────────────────────
    shell_name = resolve_shell(params.shell)
    if not verify_shell_exists(shell_name):
        return ExecResultError(
            **_base(session_id, params.command, started_at, workspace_root, None),
            error_code="SHELL_NOT_FOUND",
            error_message=f"Shell '{shell_name}' not found on PATH.",
        )
    argv = build_argv(params.command, shell_name)

    # ── 4. Resolve CWD ────────────────────────────────────────────────────
    if params.cwd:
        cwd = str(Path(workspace_root) / params.cwd) if not os.path.isabs(params.cwd) else params.cwd
    else:
        cwd = workspace_root

    if not os.path.isdir(cwd):
        return ExecResultError(
            **_base(session_id, params.command, started_at, cwd, None),
            error_code="INVALID_CWD",
            error_message=f"Working directory does not exist: {cwd}",
        )

    # ── 5. Sanitize env ────────────────────────────────────────────────────
    safe_user_env, redacted_keys = sanitize_env(params.env)
    final_env = build_env(safe_user_env, agent_session_id, session_id, workspace_root)

    # ── 6. Prepare session directory ──────────────────────────────────────
    session_dir = Path(workspace_root) / ".agent" / "sessions" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    # ── 7. Register with supervisor ────────────────────────────────────────
    supervisor = get_supervisor()
    supervisor.register(
        session_id=session_id,
        command=params.command,
        intent=params.intent,
        cwd=cwd,
        shell=shell_name,
        session_dir=session_dir,
    )

    # ── 8. Audit: exec.start ───────────────────────────────────────────────
    log_event(
        event="exec.start",
        session_id=session_id,
        agent_session_id=agent_session_id,
        command=params.command,
        intent=params.intent,
        cwd=cwd,
        shell=shell_name,
        workspace_root=workspace_root,
        env_keys_provided=list(params.env.keys()),
        sensitive_keys_redacted=redacted_keys,
        background=params.background,
    )

    # ── 9. Spawn ───────────────────────────────────────────────────────────
    # On Windows with cmd, subprocess.list2cmdline wraps the command in an
    # extra layer of quoting that causes unquoted semicolons to be treated
    # as command separators by cmd.exe. Use shell=True + the raw command
    # string instead, which lets Python build the cmd.exe /c invocation
    # correctly without double-quoting.
    import sys as _sys
    _is_windows_cmd = _sys.platform == "win32" and shell_name == "cmd"
    try:
        proc = subprocess.Popen(
            params.command if _is_windows_cmd else argv,
            shell=_is_windows_cmd,
            cwd=cwd,
            env=final_env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except Exception as exc:
        log_event(
            event="exec.failed",
            session_id=session_id,
            agent_session_id=agent_session_id,
            command=params.command,
            intent=params.intent,
            cwd=cwd,
            shell=shell_name,
            workspace_root=workspace_root,
            duration_ms=int((time.time() - started_at) * 1000),
        )
        return ExecResultError(
            **_base(session_id, params.command, started_at, cwd, None),
            error_code="INTERNAL",
            error_message=f"Failed to spawn process: {exc}",
        )

    supervisor.attach(session_id, proc)

    # Feed initial stdin if provided, then keep pipe open.
    if params.stdin:
        try:
            proc.stdin.write(params.stdin.encode("utf-8"))
            proc.stdin.flush()
        except Exception:
            pass

    # ── 10. background=True: return immediately ────────────────────────────
    if params.background:
        return ExecResultRunning(
            **_base(session_id, params.command, started_at, cwd, proc.pid),
            tail="",
            tail_lines=0,
            lines_so_far=0,
            hint=(
                f"Process started in background (pid {proc.pid}). "
                f"Call process({{action:'poll', session_id:'{session_id}'}}) to check progress."
            ),
        )

    # ── 11. Wait up to yieldMs ─────────────────────────────────────────────
    yield_s = params.yieldMs / 1000 if params.yieldMs > 0 else None

    # Set up timeout kill if requested.
    timeout_timer: threading.Timer | None = None
    if params.timeout:
        def _timeout_kill():
            supervisor.kill(session_id, reason="timeout")
        timeout_timer = threading.Timer(params.timeout / 1000, _timeout_kill)
        timeout_timer.daemon = True
        timeout_timer.start()

    try:
        exit_code = proc.wait(timeout=yield_s)
    except subprocess.TimeoutExpired:
        # Still running — return running result.
        entry_poll = supervisor.poll(session_id)
        tail = entry_poll["tail"] if entry_poll else ""
        tail_lines = entry_poll["tail_lines"] if entry_poll else 0
        lines_so_far = entry_poll["lines_so_far"] if entry_poll else 0

        return ExecResultRunning(
            **_base(session_id, params.command, started_at, cwd, proc.pid),
            tail=_maybe_strip(tail, params.stripAnsi),
            tail_lines=tail_lines,
            lines_so_far=lines_so_far,
            hint=(
                f"Still running after {params.yieldMs}ms. "
                f"Call process({{action:'poll', session_id:'{session_id}'}}) to check progress, "
                f"or process({{action:'kill', session_id:'{session_id}'}}) to terminate."
            ),
        )
    finally:
        if timeout_timer:
            timeout_timer.cancel()

    # ── 12. Process finished — collect output ──────────────────────────────
    # Wait for reader threads to drain.
    time.sleep(0.05)

    poll = supervisor.poll(session_id)
    if poll and poll["state"] == "killed":
        stdout_raw, stderr_raw = supervisor.collect_output(session_id)
        stdout, stdout_trunc, stdout_note = _process_output(
            stdout_raw, params.stripAnsi, session_id, "stdout",
            str(session_dir / "stdout.log")
        )
        log_event(
            event="exec.killed",
            session_id=session_id,
            agent_session_id=agent_session_id,
            command=params.command,
            intent=params.intent,
            cwd=cwd,
            shell=shell_name,
            workspace_root=workspace_root,
            duration_ms=int((time.time() - started_at) * 1000),
            killed_by=poll.get("killed_by"),
        )
        return ExecResultKilled(
            **_base(session_id, params.command, started_at, cwd, proc.pid),
            killed_by=poll.get("killed_by", "user"),  # type: ignore[arg-type]
            timeout_ms=params.timeout,
            stdout=stdout,
            stdout_truncated=stdout_trunc,
        )

    stdout_raw, stderr_raw = supervisor.collect_output(session_id)
    stdout, stdout_trunc, stdout_note = _process_output(
        stdout_raw, params.stripAnsi, session_id, "stdout",
        str(session_dir / "stdout.log")
    )
    stderr, stderr_trunc, stderr_note = _process_output(
        stderr_raw, params.stripAnsi, session_id, "stderr",
        str(session_dir / "stderr.log")
    )
    duration_ms = int((time.time() - started_at) * 1000)

    if exit_code == 0:
        log_event(
            event="exec.done",
            session_id=session_id,
            agent_session_id=agent_session_id,
            command=params.command,
            intent=params.intent,
            cwd=cwd,
            shell=shell_name,
            workspace_root=workspace_root,
            exit_code=exit_code,
            duration_ms=duration_ms,
        )
        return ExecResultDone(
            **_base(session_id, params.command, started_at, cwd, proc.pid),
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            stdout_truncated=stdout_trunc,
            stderr_truncated=stderr_trunc,
            truncation_note=stdout_note or stderr_note,
        )
    else:
        diagnosis = _EXIT_DIAGNOSIS.get(exit_code)
        log_event(
            event="exec.failed",
            session_id=session_id,
            agent_session_id=agent_session_id,
            command=params.command,
            intent=params.intent,
            cwd=cwd,
            shell=shell_name,
            workspace_root=workspace_root,
            exit_code=exit_code,
            duration_ms=duration_ms,
        )
        return ExecResultFailed(
            **_base(session_id, params.command, started_at, cwd, proc.pid),
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            stdout_truncated=stdout_trunc,
            stderr_truncated=stderr_trunc,
            diagnosis=diagnosis,
        )


def _maybe_strip(text: str, do_strip: bool) -> str:
    return strip_ansi(text) if do_strip else text


def _process_output(
    raw: str,
    do_strip: bool,
    session_id: str,
    stream: str,
    log_path: str,
) -> tuple[str, bool, str | None]:
    text = _maybe_strip(raw, do_strip)
    return truncate(text, session_id, stream, log_path)
