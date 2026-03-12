"""Type definitions for the browse tool (Scout computer-use subagent wrapper)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union


@dataclass
class BrowseParams:
    task: str
    """Natural-language instruction for Scout to carry out."""

    mode: Literal["browser", "desktop"] = "browser"
    """'browser' = Chrome with persistent profile; 'desktop' = full Windows control."""

    launch_browser: bool = True
    """Launch a new Chrome window before starting. Ignored in desktop mode."""

    max_turns: int = 60
    """Hard cap on Scout's action loop before returning failed."""


@dataclass(kw_only=True)
class BrowseResultDone:
    status: Literal["done"] = "done"
    deliverable: str
    """Human-readable summary of what Scout accomplished."""


@dataclass(kw_only=True)
class BrowseResultFailed:
    status: Literal["failed"] = "failed"
    reason: str
    """Why Scout could not complete the task."""


BrowseResult = Union[BrowseResultDone, BrowseResultFailed]
