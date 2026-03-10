from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Union


# ─── Input ────────────────────────────────────────────────────────────────────

@dataclass
class PingParams:
    msg: str
    type: Literal["update", "chat", "query:msg", "query:options"]
    medium: Literal["telegram", "terminal"] = "telegram"
    options: list[str] | None = None   # required when type="query:options"
    title: str | None = None           # bold header; used only for type="update"
    timeout: int = 120                 # seconds to wait for a query reply
    edit_last_update: bool = True      # edit the previous update msg in-place


# ─── Result branches ──────────────────────────────────────────────────────────

@dataclass(kw_only=True)
class PingResultSent:
    """Returned for one-way message types (update, chat)."""
    status: Literal["sent"] = "sent"
    message_id: int | None = None


@dataclass(kw_only=True)
class PingResultResponse:
    """Returned for blocking query types once the user replies."""
    status: Literal["response"] = "response"
    response: str
    message_id: int | None = None


@dataclass(kw_only=True)
class PingResultError:
    status: Literal["error"] = "error"
    error_code: Literal[
        "not_configured",
        "timeout",
        "send_failed",
        "invalid_params",
        "medium_error",
    ] = "medium_error"
    detail: str = ""


PingResult = Union[PingResultSent, PingResultResponse, PingResultError]
