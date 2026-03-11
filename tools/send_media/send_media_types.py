"""Type definitions for the send_user_media tool."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Union

SendMediaErrorCode = Literal[
    "not_configured",
    "file_not_found",
    "file_blocked",
    "send_failed",
    "invalid_params",
]


@dataclass
class SendMediaParams:
    path: str
    """Workspace-relative path to the file to send."""

    media_type: Literal["photo", "document", "video", "audio"]
    """Telegram media category — determines the API method used."""

    caption: str | None = None
    """Optional caption displayed below the media (supports MarkdownV2)."""

    medium: Literal["telegram", "terminal"] = "telegram"
    """Delivery medium. 'terminal' prints the path + caption instead of uploading."""


# ─── Result types ─────────────────────────────────────────────────────────────

@dataclass(kw_only=True)
class SendMediaResultSent:
    status: Literal["sent"] = "sent"
    message_id: int | None = None
    """Telegram message_id of the sent media message (None for terminal medium)."""


@dataclass(kw_only=True)
class SendMediaResultError:
    status: Literal["error"] = "error"
    error_code: SendMediaErrorCode = "invalid_params"
    detail: str = ""


SendMediaResult = Union[SendMediaResultSent, SendMediaResultError]
