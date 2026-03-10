from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Union


# ─── Input ────────────────────────────────────────────────────────────────────

@dataclass
class ExecParams:
    command: str
    intent: str
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    yieldMs: int = 10_000
    timeout: int | None = None
    shell: Literal["bash", "sh", "cmd", "powershell", "auto"] = "auto"
    stdin: str | None = None
    background: bool = False
    stripAnsi: bool = True


# ─── Shared base fields ────────────────────────────────────────────────────────
# kw_only=True (Python 3.10+) prevents field-ordering errors: without it,
# overriding `status` with a default in a subclass while parent has non-default
# fields after it causes TypeError at class definition time.

@dataclass(kw_only=True)
class ExecBase:
    status: str
    session_id: str
    command: str
    started_at: float       # unix timestamp (seconds)
    duration_ms: int
    cwd: str
    pid: int | None


# ─── Result branches ──────────────────────────────────────────────────────────

@dataclass(kw_only=True)
class ExecResultDone(ExecBase):
    status: Literal["done"] = "done"
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    truncation_note: str | None = None


@dataclass(kw_only=True)
class ExecResultRunning(ExecBase):
    status: Literal["running"] = "running"
    tail: str = ""
    tail_lines: int = 0
    lines_so_far: int = 0
    hint: str = ""


@dataclass(kw_only=True)
class ExecResultFailed(ExecBase):
    status: Literal["failed"] = "failed"
    exit_code: int = 1
    stdout: str = ""
    stderr: str = ""
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    diagnosis: str | None = None


@dataclass(kw_only=True)
class ExecResultKilled(ExecBase):
    status: Literal["killed"] = "killed"
    killed_by: Literal["timeout", "user", "session-limit", "signal"] = "user"
    timeout_ms: int | None = None
    stdout: str = ""
    stderr: str = ""
    stdout_truncated: bool = False
    stderr_truncated: bool = False


ErrorCode = Literal[
    "BLOCKED_COMMAND",
    "INTENT_MISSING",
    "INTENT_GENERIC",
    "INVALID_CWD",
    "SHELL_NOT_FOUND",
    "RATE_LIMITED",
    "TIMEOUT_LESS_THAN_YIELD",
    "ENV_SANITIZED",
    "INTERNAL",
]


@dataclass(kw_only=True)
class ExecResultError(ExecBase):
    status: Literal["error"] = "error"
    error_code: ErrorCode = "INTERNAL"
    error_message: str = ""
    blocked_pattern: str | None = None


ExecResult = Union[
    ExecResultDone,
    ExecResultRunning,
    ExecResultFailed,
    ExecResultKilled,
    ExecResultError,
]


# ─── Internal process entry (held by supervisor) ──────────────────────────────

@dataclass
class ProcessEntry:
    session_id: str
    command: str
    intent: str
    cwd: str
    shell: str
    pid: int | None
    started_at: float
    state: Literal["pending", "running", "done", "killed", "error"]
    exit_code: int | None = None
    killed_by: str | None = None
    # Buffers are attached externally by supervisor; not stored here.
