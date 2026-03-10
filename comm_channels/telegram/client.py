"""Thin urllib.request wrapper for the Telegram Bot API.

Uses only the Python standard library — no extra dependencies required.
All public functions raise TelegramAPIError on failure; callers should
catch it and map it to a PingResultError.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

_BASE = "https://api.telegram.org/bot{token}/{method}"


class TelegramAPIError(Exception):
    def __init__(self, method: str, description: str, error_code: int = 0) -> None:
        self.method = method
        self.description = description
        self.error_code = error_code
        super().__init__(f"Telegram {method} failed ({error_code}): {description}")


# ─── Core HTTP call ───────────────────────────────────────────────────────────

def _call(
    token: str,
    method: str,
    payload: dict[str, Any],
    *,
    http_timeout: int = 30,
) -> Any:
    """POST *payload* as JSON to the Telegram Bot API.  Returns result on success."""
    url = _BASE.format(token=token, method=method)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=http_timeout) as resp:
            body: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            body = {}
        raise TelegramAPIError(
            method,
            body.get("description", str(exc)),
            body.get("error_code", exc.code),
        ) from exc
    except Exception as exc:
        raise TelegramAPIError(method, str(exc)) from exc

    if not body.get("ok"):
        raise TelegramAPIError(
            method,
            body.get("description", "Unknown error"),
            body.get("error_code", 0),
        )
    return body["result"]


# ─── Named API wrappers ───────────────────────────────────────────────────────

def send_message(
    token: str,
    chat_id: str,
    text: str,
    *,
    parse_mode: str = "MarkdownV2",
    reply_markup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    result = _call(token, "sendMessage", payload)
    assert isinstance(result, dict)
    return result


def edit_message_text(
    token: str,
    chat_id: str,
    message_id: int,
    text: str,
    *,
    parse_mode: str = "MarkdownV2",
) -> dict[str, Any] | bool:
    """Edit an existing message's text.

    Returns the updated Message dict on success.
    Returns False if Telegram says "message is not modified" (treat as success).
    Raises TelegramAPIError for all other failures.
    """
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    try:
        result = _call(token, "editMessageText", payload)
        assert isinstance(result, dict)
        return result
    except TelegramAPIError as exc:
        if "message is not modified" in exc.description.lower():
            return False
        raise


def get_updates(
    token: str,
    *,
    offset: int = 0,
    timeout: int = 5,
    allowed_updates: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Long-poll for new updates.  *timeout* is the server-side wait in seconds."""
    payload: dict[str, Any] = {"offset": offset, "timeout": timeout}
    if allowed_updates is not None:
        payload["allowed_updates"] = allowed_updates
    # Add a small client-side buffer on top of the Telegram server timeout
    result = _call(token, "getUpdates", payload, http_timeout=timeout + 10)
    assert isinstance(result, list)
    return result


def answer_callback_query(token: str, callback_query_id: str) -> bool:
    """Acknowledge a callback query to dismiss the loading spinner on the button."""
    result = _call(token, "answerCallbackQuery", {"callback_query_id": callback_query_id})
    return bool(result)
