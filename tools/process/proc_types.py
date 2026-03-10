from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

ProcessActionName = Literal[
    "poll",
    "kill",
    "send-keys",
    "submit",
    "close-stdin",
    "list",
    "get-log",
]


@dataclass
class ProcessParams:
    action: ProcessActionName
    session_id: str | None = None
    # send-keys / submit
    keys: str | None = None
    press_enter: bool = True
    # kill
    signal: Literal["SIGTERM", "SIGKILL"] = "SIGTERM"
    # poll
    lines: int = 50
    # list
    filter: Literal["running", "done", "killed", "all"] = "all"
    # get-log
    stream: Literal["stdout", "stderr"] = "stdout"
    offset: int = 0
    limit: int = 32 * 1024
