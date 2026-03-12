"""Type definitions for the computer agent (Scout)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union


ComputerMode = Literal["browser", "desktop"]


# ─── Agent result (returned to parent after task completes) ───────────────────

@dataclass(kw_only=True)
class AgentResultDone:
    status: Literal["done"] = "done"
    deliverable: str
    """Human-readable summary of what was accomplished."""


@dataclass(kw_only=True)
class AgentResultFailed:
    status: Literal["failed"] = "failed"
    reason: str
    """Why the task could not be completed."""


AgentResult = Union[AgentResultDone, AgentResultFailed]


# ─── Per-run config (passed into ComputerAgent.run()) ─────────────────────────

@dataclass
class RunConfig:
    task: str
    """The natural-language instruction to carry out."""

    mode: ComputerMode = "browser"
    """'browser' = Chrome with persistent profile; 'desktop' = full Windows control."""

    profile: str = "default"
    """Chrome user-data profile name. Ignored in desktop mode."""

    launch_browser: bool = True
    """Whether to launch Chrome before starting. Ignored in desktop mode."""

    medium: str = "telegram"
    """Communication channel for ping_user calls ('telegram' or 'terminal')."""

    max_turns: int = 60
    """Hard cap on agent loop iterations before returning failed."""
