"""Type definitions for the image_gen tool."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union


@dataclass
class ImageGenParams:
    prompt: str
    """Text description of the image to generate."""

    size: int = 512
    """Image resolution in pixels. Passed as string to Gemini image_size. Default: 512."""

    aspect_ratio: str = "1:1"
    """Aspect ratio string. Default: '1:1'."""


# ─── Result types ─────────────────────────────────────────────────────────────

@dataclass(kw_only=True)
class ImageGenResultDone:
    status: Literal["done"] = "done"
    path: str
    """Workspace-relative path to the saved PNG."""
    width: int
    height: int
    prompt: str


@dataclass(kw_only=True)
class ImageGenResultError:
    status: Literal["error"] = "error"
    error_code: Literal[
        "not_configured",
        "api_error",
        "save_failed",
        "no_image_in_response",
        "dependency_missing",
    ]
    detail: str


ImageGenResult = Union[ImageGenResultDone, ImageGenResultError]
