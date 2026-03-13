"""ping_user — main dispatcher.

Routes to the appropriate medium (telegram / terminal) and type handler,
validates params, and writes audit events.
"""
from __future__ import annotations

from comm_channels.audit import log_event
from comm_channels.ping_types import PingParams, PingResult, PingResultError


def ping_command(
    params: PingParams,
    *,
    workspace_root: str,
    agent_session_id: str,
) -> PingResult:
    # ── Param validation ──────────────────────────────────────────────────────
    if params.type == "query:options" and not params.options:
        log_event(
            event="ping.invalid_params",
            agent_session_id=agent_session_id,
            workspace_root=workspace_root,
            medium=params.medium,
            type=params.type,
            detail="options list is required for type='query:options'",
        )
        return PingResultError(
            error_code="invalid_params",
            detail="type='query:options' requires a non-empty options list",
        )

    # ── Dispatch ──────────────────────────────────────────────────────────────
    if params.medium == "telegram":
        result = _dispatch_telegram(params, workspace_root, agent_session_id)
    elif params.medium == "terminal":
        result = _dispatch_terminal(params)
    else:
        result = PingResultError(
            error_code="invalid_params",
            detail=f"Unknown medium: {params.medium!r}",
        )

    # ── Audit outcome ─────────────────────────────────────────────────────────
    log_event(
        event="ping.done",
        agent_session_id=agent_session_id,
        workspace_root=workspace_root,
        medium=params.medium,
        type=params.type,
        status=result.status,
        error_code=getattr(result, "error_code", None),
        detail=getattr(result, "detail", None),
    )
    return result


# ─── Medium dispatchers ───────────────────────────────────────────────────────

def _delete_and_clear_anchor(workspace_root: str, cfg) -> None:
    """Delete the current update message and clear last_update_message_id from state.

    Called before sending query:msg / query:options so the query appears on a clean
    timeline with no stale progress bubble above it.
    """
    try:
        from comm_channels._state import load_state, save_state
        from comm_channels.telegram.client import delete_message, TelegramAPIError
        state = load_state(workspace_root)
        msg_id = state.get("last_update_message_id")
        if msg_id:
            try:
                delete_message(cfg.bot_token, cfg.chat_id, msg_id)
            except TelegramAPIError:
                pass
            state.pop("last_update_message_id", None)
            save_state(workspace_root, state)
    except Exception:  # noqa: BLE001
        pass


def _dispatch_terminal(params: PingParams) -> PingResult:
    from comm_channels.terminal.channel import terminal_send
    return terminal_send(params)


def _dispatch_telegram(
    params: PingParams,
    workspace_root: str,
    agent_session_id: str,
) -> PingResult:
    from comm_channels.telegram.config import ConfigError, load_config
    from comm_channels.telegram import sender

    try:
        cfg = load_config(workspace_root)
    except ConfigError as exc:
        return PingResultError(error_code="not_configured", detail=str(exc))

    if params.type == "update":
        return sender.send_update(params, cfg, workspace_root)
    if params.type == "chat":
        # Anchor deletion is handled by _run_agent_turn before calling this
        return sender.send_chat(params, cfg)
    if params.type == "query:msg":
        # Delete progress bubble before sending query so it appears on a clean line
        _delete_and_clear_anchor(workspace_root, cfg)
        return sender.send_query_msg(params, cfg, workspace_root)
    if params.type == "query:options":
        # Delete progress bubble before sending options so it appears on a clean line
        _delete_and_clear_anchor(workspace_root, cfg)
        return sender.send_query_options(params, cfg)

    return PingResultError(
        error_code="invalid_params",
        detail=f"Unknown type: {params.type!r}",
    )
