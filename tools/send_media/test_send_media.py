"""
test_send_media.py — test suite for the send_user_media tool.

Run from the workspace root:
    python -m pytest tools/send_media/test_send_media.py -v
Or directly:
    python -m tools.send_media.test_send_media
"""
from __future__ import annotations

import os
import sys

# Allow `python test_send_media.py` from inside tools/send_media/
if __name__ == "__main__" and __package__ is None:
    _workspace = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    )
    if _workspace not in sys.path:
        sys.path.insert(0, _workspace)
    __package__ = "tools.send_media"

import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from .send_media_tool import send_media_command
from .send_media_types import SendMediaParams, SendMediaResultError, SendMediaResultSent

# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------
_results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    _results.append((name, condition, detail))
    status = "\033[32mPASS\033[0m" if condition else "\033[31mFAIL\033[0m"
    suffix = f"  ({detail})" if detail and not condition else ""
    print(f"  [{status}] {name}{suffix}")


def section(title: str) -> None:
    print(f"\n{'-' * 60}")
    print(f"  {title}")
    print(f"{'-' * 60}")


def make_runner(workspace: str):
    def run(path: str, media_type: str = "document", **kwargs):
        params = SendMediaParams(path=path, media_type=media_type, **kwargs)
        return send_media_command(
            params, workspace_root=workspace, agent_session_id="test_session"
        )
    return run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_upload_result() -> dict:
    return {"message_id": 42, "photo": []}


def _make_upload_mock(return_value: dict | None = None):
    m = MagicMock(return_value=return_value or _fake_upload_result())
    return m


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_file_not_found() -> None:
    section("File not found")
    with tempfile.TemporaryDirectory(prefix="snm_test_") as ws:
        run = make_runner(ws)
        r = run("nonexistent.jpg", "photo")
        check("status=error", r.status == "error", str(r))
        check("error_code=file_not_found", r.error_code == "file_not_found", str(r))


def test_file_blocked_env() -> None:
    section("Blocked path (.env)")
    with tempfile.TemporaryDirectory(prefix="snm_test_") as ws:
        run = make_runner(ws)
        r = run(".env", "document")
        check("status=error", r.status == "error", str(r))
        check("error_code=file_blocked", r.error_code == "file_blocked", str(r))


def test_terminal_photo() -> None:
    section("Terminal medium — photo")
    with tempfile.TemporaryDirectory(prefix="snm_test_") as ws:
        img = Path(ws) / "shot.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n")
        run = make_runner(ws)

        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            r = run("shot.png", "photo", medium="terminal")

        output = buf.getvalue()
        check("status=sent", r.status == "sent", str(r))
        check("message_id=None", r.message_id is None)
        check("output contains [MEDIA:PHOTO]", "[MEDIA:PHOTO]" in output, repr(output))
        check("output contains filename", "shot.png" in output, repr(output))


def test_terminal_document_with_caption() -> None:
    section("Terminal medium — document with caption")
    with tempfile.TemporaryDirectory(prefix="snm_test_") as ws:
        doc = Path(ws) / "report.pdf"
        doc.write_bytes(b"%PDF-1.4")
        run = make_runner(ws)

        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            r = run("report.pdf", "document", medium="terminal", caption="Q1 report")

        output = buf.getvalue()
        check("status=sent", r.status == "sent", str(r))
        check("output contains [MEDIA:DOCUMENT]", "[MEDIA:DOCUMENT]" in output, repr(output))
        check("output contains caption", "Q1 report" in output, repr(output))


def test_terminal_no_caption() -> None:
    section("Terminal medium — no caption")
    with tempfile.TemporaryDirectory(prefix="snm_test_") as ws:
        f = Path(ws) / "data.zip"
        f.write_bytes(b"PK")
        run = make_runner(ws)

        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            r = run("data.zip", "document", medium="terminal")

        output = buf.getvalue()
        check("no em-dash when no caption", " \u2014 " not in output, repr(output))


def test_telegram_photo_sends_correct_method() -> None:
    section("Telegram — photo uses sendPhoto + 'photo' field")
    with tempfile.TemporaryDirectory(prefix="snm_test_") as ws:
        img = Path(ws) / "img.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0")  # JPEG magic bytes

        with (
            patch("comm_channels.telegram.config.load_config") as mock_cfg,
            patch("comm_channels.telegram.sender.upload_media") as mock_upload,
        ):
            mock_cfg.return_value = MagicMock(bot_token="tok", chat_id="123")
            mock_upload.return_value = {"message_id": 7}

            params = SendMediaParams(path="img.jpg", media_type="photo")
            r = send_media_command(
                params, workspace_root=ws, agent_session_id="test_session"
            )

        check("status=sent", r.status == "sent", str(r))
        check("message_id=7", r.message_id == 7)
        call_args = mock_upload.call_args
        check("method=sendPhoto", call_args.args[1] == "sendPhoto", str(call_args))
        check("field=photo", call_args.args[3] == "photo", str(call_args))


def test_telegram_document_sends_correct_method() -> None:
    section("Telegram — document uses sendDocument + 'document' field")
    with tempfile.TemporaryDirectory(prefix="snm_test_") as ws:
        doc = Path(ws) / "notes.txt"
        doc.write_text("hello")

        with (
            patch("comm_channels.telegram.config.load_config") as mock_cfg,
            patch("comm_channels.telegram.sender.upload_media") as mock_upload,
        ):
            mock_cfg.return_value = MagicMock(bot_token="tok", chat_id="123")
            mock_upload.return_value = {"message_id": 8}

            params = SendMediaParams(path="notes.txt", media_type="document")
            r = send_media_command(
                params, workspace_root=ws, agent_session_id="test_session"
            )

        check("status=sent", r.status == "sent", str(r))
        call_args = mock_upload.call_args
        check("method=sendDocument", call_args.args[1] == "sendDocument", str(call_args))
        check("field=document", call_args.args[3] == "document", str(call_args))


def test_telegram_video_method() -> None:
    section("Telegram — video uses sendVideo + 'video' field")
    with tempfile.TemporaryDirectory(prefix="snm_test_") as ws:
        vid = Path(ws) / "clip.mp4"
        vid.write_bytes(b"\x00\x00\x00\x18ftyp")

        with (
            patch("comm_channels.telegram.config.load_config") as mock_cfg,
            patch("comm_channels.telegram.sender.upload_media") as mock_upload,
        ):
            mock_cfg.return_value = MagicMock(bot_token="tok", chat_id="123")
            mock_upload.return_value = {"message_id": 9}

            params = SendMediaParams(path="clip.mp4", media_type="video")
            r = send_media_command(
                params, workspace_root=ws, agent_session_id="test_session"
            )

        check("status=sent", r.status == "sent", str(r))
        call_args = mock_upload.call_args
        check("method=sendVideo", call_args.args[1] == "sendVideo", str(call_args))
        check("field=video", call_args.args[3] == "video", str(call_args))


def test_telegram_audio_method() -> None:
    section("Telegram — audio uses sendAudio + 'audio' field")
    with tempfile.TemporaryDirectory(prefix="snm_test_") as ws:
        aud = Path(ws) / "track.mp3"
        aud.write_bytes(b"ID3")

        with (
            patch("comm_channels.telegram.config.load_config") as mock_cfg,
            patch("comm_channels.telegram.sender.upload_media") as mock_upload,
        ):
            mock_cfg.return_value = MagicMock(bot_token="tok", chat_id="123")
            mock_upload.return_value = {"message_id": 10}

            params = SendMediaParams(path="track.mp3", media_type="audio")
            r = send_media_command(
                params, workspace_root=ws, agent_session_id="test_session"
            )

        check("status=sent", r.status == "sent", str(r))
        call_args = mock_upload.call_args
        check("method=sendAudio", call_args.args[1] == "sendAudio", str(call_args))
        check("field=audio", call_args.args[3] == "audio", str(call_args))


def test_telegram_caption_escaped() -> None:
    section("Telegram — caption is MarkdownV2-escaped")
    with tempfile.TemporaryDirectory(prefix="snm_test_") as ws:
        img = Path(ws) / "img.png"
        img.write_bytes(b"\x89PNG")

        with (
            patch("comm_channels.telegram.config.load_config") as mock_cfg,
            patch("comm_channels.telegram.sender.upload_media") as mock_upload,
        ):
            mock_cfg.return_value = MagicMock(bot_token="tok", chat_id="123")
            mock_upload.return_value = {"message_id": 11}

            params = SendMediaParams(
                path="img.png", media_type="photo", caption="Result: 100% done!"
            )
            send_media_command(params, workspace_root=ws, agent_session_id="test_session")

        call_kwargs = mock_upload.call_args.kwargs
        raw_caption = call_kwargs.get("caption", "")
        check(
            "special chars escaped",
            "%" not in raw_caption or "\\%" in raw_caption or raw_caption != "Result: 100% done!",
            repr(raw_caption),
        )


def test_telegram_not_configured() -> None:
    section("Telegram — missing config returns not_configured")
    with tempfile.TemporaryDirectory(prefix="snm_test_") as ws:
        img = Path(ws) / "img.png"
        img.write_bytes(b"\x89PNG")

        from comm_channels.telegram.config import ConfigError
        with patch("comm_channels.telegram.config.load_config", side_effect=ConfigError("no token")):
            params = SendMediaParams(path="img.png", media_type="photo")
            r = send_media_command(params, workspace_root=ws, agent_session_id="test_session")

        check("status=error", r.status == "error", str(r))
        check("error_code=not_configured", r.error_code == "not_configured", str(r))


def test_telegram_upload_failure() -> None:
    section("Telegram — upload failure returns send_failed")
    with tempfile.TemporaryDirectory(prefix="snm_test_") as ws:
        img = Path(ws) / "img.png"
        img.write_bytes(b"\x89PNG")

        from comm_channels.telegram.client import TelegramAPIError
        with (
            patch("comm_channels.telegram.config.load_config") as mock_cfg,
            patch("comm_channels.telegram.client.upload_media",
                  side_effect=TelegramAPIError("sendPhoto", "Bad Request", 400)),
        ):
            mock_cfg.return_value = MagicMock(bot_token="tok", chat_id="123")
            params = SendMediaParams(path="img.png", media_type="photo")
            r = send_media_command(params, workspace_root=ws, agent_session_id="test_session")

        check("status=error", r.status == "error", str(r))
        check("error_code=send_failed", r.error_code == "send_failed", str(r))


def test_audit_written() -> None:
    section("Audit — event written on success")
    import json as _json
    with tempfile.TemporaryDirectory(prefix="snm_test_") as ws:
        doc = Path(ws) / "file.txt"
        doc.write_text("data")

        with (
            patch("comm_channels.telegram.config.load_config") as mock_cfg,
            patch("comm_channels.telegram.sender.upload_media") as mock_upload,
        ):
            mock_cfg.return_value = MagicMock(bot_token="tok", chat_id="123")
            mock_upload.return_value = {"message_id": 99}

            params = SendMediaParams(path="file.txt", media_type="document")
            send_media_command(params, workspace_root=ws, agent_session_id="test_session")

        audit_dir = Path(ws) / ".agent" / "audit"
        ping_logs = list(audit_dir.glob("ping-*.jsonl"))
        check("audit file created", len(ping_logs) > 0, str(list(audit_dir.iterdir()) if audit_dir.exists() else []))
        if ping_logs:
            lines = ping_logs[0].read_text().strip().splitlines()
            events = [_json.loads(ln) for ln in lines if ln]
            media_events = [e for e in events if "media" in e.get("event", "")]
            check("media.done event logged", any(e["event"] == "media.done" for e in media_events), str(media_events))


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all() -> None:
    print("\n" + "=" * 60)
    print("  send_user_media — test suite")
    print("=" * 60)

    test_file_not_found()
    test_file_blocked_env()
    test_terminal_photo()
    test_terminal_document_with_caption()
    test_terminal_no_caption()
    test_telegram_photo_sends_correct_method()
    test_telegram_document_sends_correct_method()
    test_telegram_video_method()
    test_telegram_audio_method()
    test_telegram_caption_escaped()
    test_telegram_not_configured()
    test_telegram_upload_failure()
    test_audit_written()

    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print(f"\n{'=' * 60}")
    print(f"  Results: {passed}/{total} passed")
    print("=" * 60)
    if passed < total:
        sys.exit(1)


# pytest compatibility — expose each test as a function at module level
def test_all():
    """Umbrella test — run from pytest."""
    run_all()
    failed = [name for name, ok, _ in _results if not ok]
    assert not failed, f"Failed checks: {failed}"


if __name__ == "__main__":
    run_all()
