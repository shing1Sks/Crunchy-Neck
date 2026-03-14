"""Type definitions for the snapshot tool."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union


@dataclass
class SnapshotParams:
    monitor: int = 0
    """0 = all monitors combined (default); 1+ = specific monitor index."""

    x1: int | None = None
    y1: int | None = None
    x2: int | None = None
    y2: int | None = None
    """Optional region: top-left (x1, y1) → bottom-right (x2, y2).
    All four must be provided together; if any is None the full screen is captured."""

    filename: str | None = None
    """Custom filename for the saved file (e.g. 'empty_state.png').
    Saved under .agent/snapshots/{filename}. If None, a timestamp name is used."""

    format: Literal["png", "jpeg"] = "png"
    """Output image format."""

    include_base64: bool = True
    """Embed base64-encoded image in the result for direct LLM vision use."""


# ─── Result types ─────────────────────────────────────────────────────────────

@dataclass(kw_only=True)
class SnapshotResultDone:
    status: Literal["done"] = "done"
    path: str
    """Workspace-relative path to the saved screenshot."""
    width: int
    height: int
    format: str
    base64: str | None
    """Base64-encoded image data; None when include_base64=False."""


@dataclass(kw_only=True)
class SnapshotResultError:
    status: Literal["error"] = "error"
    error_code: Literal["capture_failed", "save_failed", "invalid_region", "dependency_missing"]
    detail: str


SnapshotResult = Union[SnapshotResultDone, SnapshotResultError]
