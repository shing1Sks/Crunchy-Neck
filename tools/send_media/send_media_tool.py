"""send_user_media — main dispatcher.

Resolves the file path, then routes to the appropriate medium handler.
"""
from __future__ import annotations

from pathlib import Path

from comm_channels.audit import log_event
from tools.file_safety import resolve_path

from .send_media_types import (
    SendMediaParams,
    SendMediaResult,
    SendMediaResultError,
    SendMediaResultSent,
)


def send_media_command(
    params: SendMediaParams,
    *,
    workspace_root: str,
    agent_session_id: str,
) -> SendMediaResult:
    # ── Path resolution & safety ───────────────────────────────────────────────
    resolved, block_reason = resolve_path(params.path, workspace_root)

    if block_reason is not None:
        _audit(
            event="media.file_error",
            agent_session_id=agent_session_id,
            workspace_root=workspace_root,
            params=params,
            status="error",
            error_code="file_blocked",
            detail=block_reason,
        )
        return SendMediaResultError(
            error_code="file_blocked",
            detail=f"Path blocked: {block_reason}",
        )

    if not resolved.exists():
        _audit(
            event="media.file_error",
            agent_session_id=agent_session_id,
            workspace_root=workspace_root,
            params=params,
            status="error",
            error_code="file_not_found",
            detail=str(resolved),
        )
        return SendMediaResultError(
            error_code="file_not_found",
            detail=f"File not found: {params.path!r}",
        )

    # ── Dispatch ───────────────────────────────────────────────────────────────
    if params.medium == "terminal":
        result = _dispatch_terminal(params)
    elif params.medium == "telegram":
        result = _dispatch_telegram(params, resolved, workspace_root)
    else:
        result = SendMediaResultError(
            error_code="invalid_params",
            detail=f"Unknown medium: {params.medium!r}",
        )

    # ── Audit outcome ──────────────────────────────────────────────────────────
    _audit(
        event="media.done",
        agent_session_id=agent_session_id,
        workspace_root=workspace_root,
        params=params,
        status=result.status,
        error_code=getattr(result, "error_code", None),
        detail=getattr(result, "detail", None),
    )
    return result


# ─── Medium dispatchers ───────────────────────────────────────────────────────

def _dispatch_terminal(params: SendMediaParams) -> SendMediaResult:
    from comm_channels.terminal.channel import terminal_send_media
    return terminal_send_media(params)


def _dispatch_telegram(
    params: SendMediaParams,
    resolved: "Path",
    workspace_root: str,
) -> SendMediaResult:
    from comm_channels.telegram.config import ConfigError, load_config
    from comm_channels.telegram.sender import send_media

    try:
        cfg = load_config(workspace_root)
    except ConfigError as exc:
        return SendMediaResultError(error_code="not_configured", detail=str(exc))

    return send_media(params, cfg, resolved)


# ─── Audit helper ─────────────────────────────────────────────────────────────

def _audit(
    *,
    event: str,
    agent_session_id: str,
    workspace_root: str,
    params: SendMediaParams,
    status: str,
    error_code: str | None = None,
    detail: str | None = None,
) -> None:
    log_event(
        event=event,
        agent_session_id=agent_session_id,
        workspace_root=workspace_root,
        medium=params.medium,
        media_type=params.media_type,
        path=params.path,
        status=status,
        error_code=error_code,
        detail=detail,
    )
