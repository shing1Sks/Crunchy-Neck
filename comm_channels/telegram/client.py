"""Thin urllib.request wrapper for the Telegram Bot API.

Uses only the Python standard library — no extra dependencies required.
All public functions raise TelegramAPIError on failure; callers should
catch it and map it to a PingResultError / SendMediaResultError.
"""
from __future__ import annotations

import json
import mimetypes
import uuid
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
    reply_markup: dict[str, Any] | None = None,
) -> dict[str, Any] | bool:
    """Edit an existing message's text.

    Pass reply_markup={"inline_keyboard": []} to remove inline buttons.
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
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
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


def delete_message(token: str, chat_id: str, message_id: int) -> bool:
    """Delete a message by ID.

    Returns True on success.
    Returns False silently if the message is already gone — idempotent.
    Raises TelegramAPIError for all other failures.
    """
    try:
        result = _call(token, "deleteMessage", {"chat_id": chat_id, "message_id": message_id})
        return bool(result)
    except TelegramAPIError as exc:
        if exc.error_code == 400 and "not found" in exc.description.lower():
            return False
        raise


def upload_media(
    token: str,
    method: str,
    chat_id: str,
    field_name: str,
    file_bytes: bytes,
    filename: str,
    *,
    caption: str | None = None,
    parse_mode: str = "MarkdownV2",
    http_timeout: int = 60,
) -> dict[str, Any]:
    """Upload a file to Telegram using multipart/form-data.

    Args:
        token:      Bot token.
        method:     API method, e.g. 'sendPhoto', 'sendDocument'.
        chat_id:    Destination chat ID.
        field_name: Multipart field name for the file ('photo', 'document', etc.).
        file_bytes: Raw bytes of the file to upload.
        filename:   Original filename (used for Content-Disposition and MIME type).
        caption:    Optional caption (MarkdownV2-escaped by the caller).
        parse_mode: Parse mode for the caption.
        http_timeout: HTTP timeout in seconds (longer than JSON calls due to upload).

    Returns:
        The Telegram Message dict from result.

    Raises:
        TelegramAPIError on any failure.
    """
    boundary = uuid.uuid4().hex
    content_type_header = f"multipart/form-data; boundary={boundary}"

    mime_type, _ = mimetypes.guess_type(filename)
    if mime_type is None:
        mime_type = "application/octet-stream"

    # ── Build multipart body ──────────────────────────────────────────────────
    parts: list[bytes] = []

    def _field(name: str, value: str) -> bytes:
        return (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode("utf-8")

    parts.append(_field("chat_id", chat_id))

    if caption is not None:
        parts.append(_field("caption", caption))
        parts.append(_field("parse_mode", parse_mode))

    # File part
    parts.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode("utf-8")
        + file_bytes
        + b"\r\n"
    )

    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(parts)

    url = _BASE.format(token=token, method=method)
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": content_type_header},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=http_timeout) as resp:
            response_body: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            response_body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            response_body = {}
        raise TelegramAPIError(
            method,
            response_body.get("description", str(exc)),
            response_body.get("error_code", exc.code),
        ) from exc
    except Exception as exc:
        raise TelegramAPIError(method, str(exc)) from exc

    if not response_body.get("ok"):
        raise TelegramAPIError(
            method,
            response_body.get("description", "Unknown error"),
            response_body.get("error_code", 0),
        )
    result = response_body["result"]
    assert isinstance(result, dict)
    return result
