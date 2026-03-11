"""Terminal medium for ping_user and send_user_media.

Delivers all message types via stdout (print) and stdin (input).
No network calls; works without any configuration.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from ..ping_types import (
    PingParams,
    PingResult,
    PingResultError,
    PingResultResponse,
    PingResultSent,
)
from ..templates import (
    render_terminal_chat,
    render_terminal_options,
    render_terminal_query_msg,
    render_terminal_update,
)

if TYPE_CHECKING:
    from tools.send_media.send_media_types import SendMediaParams, SendMediaResult


def terminal_send(params: PingParams) -> PingResult:
    if params.type == "update":
        print(render_terminal_update(params.title, params.msg))
        return PingResultSent(message_id=None)

    if params.type == "chat":
        print(render_terminal_chat(params.msg))
        return PingResultSent(message_id=None)

    if params.type == "query:msg":
        prompt = render_terminal_query_msg(params.msg)
        try:
            response = input(f"{prompt}\n> ")
            return PingResultResponse(response=response.strip(), message_id=None)
        except (EOFError, KeyboardInterrupt):
            return PingResultError(
                error_code="medium_error",
                detail="stdin closed or interrupted",
            )

    if params.type == "query:options":
        options = params.options or []
        numbered = render_terminal_options(options)
        prompt = f"[QUERY] {params.msg}\n{numbered}\nEnter choice number: "
        try:
            raw = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            return PingResultError(
                error_code="medium_error",
                detail="stdin closed or interrupted",
            )
        try:
            idx = int(raw) - 1
        except ValueError:
            return PingResultError(
                error_code="medium_error",
                detail=f"Non-numeric input: {raw!r}",
            )
        if 0 <= idx < len(options):
            return PingResultResponse(response=options[idx], message_id=None)
        return PingResultError(
            error_code="medium_error",
            detail=f"Choice {raw!r} out of range (1\u2013{len(options)})",
        )

    return PingResultError(
        error_code="invalid_params",
        detail=f"Unknown type: {params.type!r}",
    )


def terminal_send_media(params: "SendMediaParams") -> "SendMediaResult":
    """Print media path and caption to stdout (terminal cannot display media files)."""
    from tools.send_media.send_media_types import SendMediaResultSent

    label = params.media_type.upper()
    caption_part = f" \u2014 {params.caption}" if params.caption else ""
    print(f"[MEDIA:{label}] {params.path}{caption_part}")
    return SendMediaResultSent(message_id=None)
