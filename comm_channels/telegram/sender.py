"""Telegram send functions — one per message type.

Each function takes a PingParams + TelegramConfig and returns a PingResult.
All HTTP is funnelled through telegram.client which uses only urllib.request.
"""
from __future__ import annotations

import time
from typing import Any

from .client import (
    TelegramAPIError,
    answer_callback_query,
    edit_message_text,
    get_updates,
    send_message,
)
from .config import TelegramConfig
from .._state import load_state, save_state
from ..ping_types import (
    PingParams,
    PingResult,
    PingResultError,
    PingResultResponse,
    PingResultSent,
)
from ..templates import (
    render_telegram_chat,
    render_telegram_query_msg,
    render_telegram_query_options,
    render_telegram_update,
)


# ─── update ───────────────────────────────────────────────────────────────────

def send_update(
    params: PingParams,
    cfg: TelegramConfig,
    workspace_root: str,
) -> PingResult:
    text = render_telegram_update(params.title, params.msg)
    state = load_state(workspace_root)
    last_id: int | None = state.get("last_update_message_id")

    # Try editing the previous message first (reduces channel spam)
    if params.edit_last_update and last_id is not None:
        try:
            result = edit_message_text(cfg.bot_token, cfg.chat_id, last_id, text)
            # result is False → "not modified" → treat as success, id unchanged
            return PingResultSent(message_id=last_id)
        except TelegramAPIError:
            pass  # Fall through and send a fresh message

    # Send a new message
    try:
        msg = send_message(cfg.bot_token, cfg.chat_id, text)
        new_id: int = msg["message_id"]
        save_state(workspace_root, {"last_update_message_id": new_id})
        return PingResultSent(message_id=new_id)
    except TelegramAPIError as exc:
        return PingResultError(error_code="send_failed", detail=str(exc))


# ─── chat ─────────────────────────────────────────────────────────────────────

def send_chat(params: PingParams, cfg: TelegramConfig) -> PingResult:
    try:
        msg = send_message(cfg.bot_token, cfg.chat_id, render_telegram_chat(params.msg))
        return PingResultSent(message_id=msg["message_id"])
    except TelegramAPIError as exc:
        return PingResultError(error_code="send_failed", detail=str(exc))


# ─── query:msg ────────────────────────────────────────────────────────────────

def send_query_msg(params: PingParams, cfg: TelegramConfig) -> PingResult:
    force_reply: dict[str, Any] = {"force_reply": True, "selective": False}
    try:
        sent = send_message(
            cfg.bot_token,
            cfg.chat_id,
            render_telegram_query_msg(params.msg),
            reply_markup=force_reply,
        )
    except TelegramAPIError as exc:
        return PingResultError(error_code="send_failed", detail=str(exc))

    return _poll_for_text_reply(cfg, sent["message_id"], params.timeout)


# ─── query:options ────────────────────────────────────────────────────────────

def send_query_options(params: PingParams, cfg: TelegramConfig) -> PingResult:
    text = render_telegram_query_options(params.msg)
    keyboard = _build_inline_keyboard(params.options or [])
    try:
        sent = send_message(
            cfg.bot_token,
            cfg.chat_id,
            text,
            reply_markup=keyboard,
        )
    except TelegramAPIError as exc:
        return PingResultError(error_code="send_failed", detail=str(exc))

    return _poll_for_callback(cfg, sent["message_id"], params.timeout)


# ─── Polling helpers ──────────────────────────────────────────────────────────

def _poll_for_text_reply(
    cfg: TelegramConfig,
    original_msg_id: int,
    timeout: int,
) -> PingResult:
    """Block until a Message that replies to *original_msg_id* arrives."""
    deadline = time.monotonic() + timeout
    offset = 0

    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        poll_timeout = min(int(remaining), 5)
        if poll_timeout <= 0:
            break
        try:
            updates = get_updates(
                cfg.bot_token,
                offset=offset,
                timeout=poll_timeout,
                allowed_updates=["message"],
            )
        except TelegramAPIError:
            time.sleep(1)
            continue

        for update in updates:
            offset = update["update_id"] + 1
            msg = update.get("message") or {}
            reply_to = msg.get("reply_to_message") or {}
            if reply_to.get("message_id") == original_msg_id:
                return PingResultResponse(
                    response=msg.get("text", ""),
                    message_id=msg.get("message_id"),
                )

    return PingResultError(
        error_code="timeout",
        detail=f"No reply received within {timeout}s",
    )


def _poll_for_callback(
    cfg: TelegramConfig,
    original_msg_id: int,
    timeout: int,
) -> PingResult:
    """Block until a CallbackQuery for *original_msg_id* arrives."""
    deadline = time.monotonic() + timeout
    offset = 0

    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        poll_timeout = min(int(remaining), 5)
        if poll_timeout <= 0:
            break
        try:
            updates = get_updates(
                cfg.bot_token,
                offset=offset,
                timeout=poll_timeout,
                allowed_updates=["callback_query"],
            )
        except TelegramAPIError:
            time.sleep(1)
            continue

        for update in updates:
            offset = update["update_id"] + 1
            cb = update.get("callback_query") or {}
            cb_msg = cb.get("message") or {}
            if cb_msg.get("message_id") == original_msg_id:
                # Must answer within ~10 s or Telegram shows an error spinner
                try:
                    answer_callback_query(cfg.bot_token, cb["id"])
                except TelegramAPIError:
                    pass  # Non-fatal — the response is still valid
                return PingResultResponse(
                    response=cb.get("data", ""),
                    message_id=cb_msg.get("message_id"),
                )

    return PingResultError(
        error_code="timeout",
        detail=f"No selection received within {timeout}s",
    )


# ─── Keyboard builder ─────────────────────────────────────────────────────────

def _build_inline_keyboard(options: list[str]) -> dict[str, Any]:
    """Each option gets its own row (single-column layout for clarity)."""
    rows = [[{"text": opt, "callback_data": opt}] for opt in options]
    return {"inline_keyboard": rows}
