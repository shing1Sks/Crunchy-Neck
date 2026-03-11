"""Type definitions for the snapshot tool."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union


@dataclass
class SnapshotParams:
    monitor: int = 0
    """0 = all monitors combined (default); 1+ = specific monitor index."""

    region: list[int] | None = None
    """Optional [x, y, width, height] pixel crop applied after capture."""

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
