"""
test_tts.py — test suite for the tts tool.

Run from the workspace root:
    python -m tools.tts.test_tts
"""
from __future__ import annotations

import os
import sys

if __name__ == "__main__" and __package__ is None:
    _workspace = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    )
    if _workspace not in sys.path:
        sys.path.insert(0, _workspace)
    __package__ = "tools.tts"

import base64
import json
import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from .tts_tool import tts_command
from .tts_types import TtsParams, TtsResultDone, TtsResultError

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


def _fake_audio_b64() -> str:
    return base64.b64encode(b"ID3\x00fake-mp3-content").decode("ascii")


def _make_url_mock(audio_b64: str):
    """Return a context-manager mock for urllib.request.urlopen."""
    response_body = json.dumps({"audioContent": audio_b64}).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.read.return_value = response_body
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_success() -> None:
    section("Successful TTS call")
    with tempfile.TemporaryDirectory(prefix="tts_test_") as ws:
        audio_b64 = _fake_audio_b64()
        mock_resp = _make_url_mock(audio_b64)

        with (
            patch.dict(os.environ, {"INWORLD_API_KEY": "test-key-b64"}),
            patch("urllib.request.urlopen", return_value=mock_resp),
        ):
            params = TtsParams(text="Hello world")
            r = tts_command(params, workspace_root=ws, agent_session_id="test")

        check("status=done", r.status == "done", str(r))
        check("path contains .agent/tts", ".agent" in r.path and "tts-" in r.path, r.path)
        check("path ends .mp3", r.path.endswith(".mp3"), r.path)
        check("file saved", Path(ws, r.path).exists(), r.path)
        check("voice_id=Ashley", r.voice_id == "Ashley")
        check("model_id default", r.model_id == "inworld-tts-1.5-max")

        # Verify file content
        saved = Path(ws, r.path).read_bytes()
        check("audio bytes written", saved == base64.b64decode(audio_b64))


def test_custom_voice_and_model() -> None:
    section("Custom voice_id and model_id")
    with tempfile.TemporaryDirectory(prefix="tts_test_") as ws:
        mock_resp = _make_url_mock(_fake_audio_b64())

        with (
            patch.dict(os.environ, {"INWORLD_API_KEY": "k"}),
            patch("urllib.request.urlopen", return_value=mock_resp),
        ):
            r = tts_command(
                TtsParams(text="Hi", voice_id="Emma", model_id="inworld-tts-1.5"),
                workspace_root=ws, agent_session_id="test",
            )

        check("status=done", r.status == "done", str(r))
        check("voice_id=Emma", r.voice_id == "Emma")
        check("model_id=inworld-tts-1.5", r.model_id == "inworld-tts-1.5")


def test_request_body_fields() -> None:
    section("Request body contains text, voiceId, modelId")
    with tempfile.TemporaryDirectory(prefix="tts_test_") as ws:
        mock_resp = _make_url_mock(_fake_audio_b64())
        captured_req: list = []

        def _fake_urlopen(req, timeout=None):
            captured_req.append(req)
            return mock_resp

        with (
            patch.dict(os.environ, {"INWORLD_API_KEY": "k"}),
            patch("urllib.request.urlopen", side_effect=_fake_urlopen),
        ):
            tts_command(
                TtsParams(text="Test text", voice_id="Sam"),
                workspace_root=ws, agent_session_id="test",
            )

        req = captured_req[0]
        body = json.loads(req.data.decode("utf-8"))
        check("text in body", body.get("text") == "Test text", str(body))
        check("voiceId in body", body.get("voiceId") == "Sam", str(body))
        check("modelId in body", "modelId" in body, str(body))

        auth_header = req.get_header("Authorization")
        check("Authorization header present", auth_header is not None, str(auth_header))
        check("Authorization starts Basic", str(auth_header).startswith("Basic"), str(auth_header))


def test_not_configured() -> None:
    section("Missing INWORLD_API_KEY -> not_configured")
    with tempfile.TemporaryDirectory(prefix="tts_test_") as ws:
        env_without_key = {k: v for k, v in os.environ.items() if k != "INWORLD_API_KEY"}
        with patch.dict(os.environ, env_without_key, clear=True):
            r = tts_command(TtsParams(text="hi"), workspace_root=ws, agent_session_id="test")

        check("status=error", r.status == "error", str(r))
        check("error_code=not_configured", r.error_code == "not_configured", str(r))


def test_api_error_http() -> None:
    section("HTTP error from API -> api_error")
    import urllib.error
    with tempfile.TemporaryDirectory(prefix="tts_test_") as ws:
        err_body = json.dumps({"message": "Unauthorized"}).encode("utf-8")
        http_err = urllib.error.HTTPError(
            url="", code=401, msg="Unauthorized",
            hdrs=None, fp=BytesIO(err_body),
        )

        with (
            patch.dict(os.environ, {"INWORLD_API_KEY": "bad-key"}),
            patch("urllib.request.urlopen", side_effect=http_err),
        ):
            r = tts_command(TtsParams(text="hi"), workspace_root=ws, agent_session_id="test")

        check("status=error", r.status == "error", str(r))
        check("error_code=api_error", r.error_code == "api_error", str(r))
        check("detail contains Unauthorized", "Unauthorized" in r.detail, r.detail)


def test_api_error_network() -> None:
    section("Network error -> api_error")
    with tempfile.TemporaryDirectory(prefix="tts_test_") as ws:
        with (
            patch.dict(os.environ, {"INWORLD_API_KEY": "k"}),
            patch("urllib.request.urlopen", side_effect=ConnectionError("connection refused")),
        ):
            r = tts_command(TtsParams(text="hi"), workspace_root=ws, agent_session_id="test")

        check("status=error", r.status == "error", str(r))
        check("error_code=api_error", r.error_code == "api_error", str(r))


def test_audit_written() -> None:
    section("Audit — tts.done event written")
    with tempfile.TemporaryDirectory(prefix="tts_test_") as ws:
        mock_resp = _make_url_mock(_fake_audio_b64())

        with (
            patch.dict(os.environ, {"INWORLD_API_KEY": "k"}),
            patch("urllib.request.urlopen", return_value=mock_resp),
        ):
            tts_command(TtsParams(text="Audit test"), workspace_root=ws, agent_session_id="test")

        audit_dir = Path(ws) / ".agent" / "audit"
        logs = list(audit_dir.glob("tts-*.jsonl"))
        check("audit file created", len(logs) > 0)
        if logs:
            events = [json.loads(ln)["event"] for ln in logs[0].read_text().splitlines() if ln.strip()]
            check("tts.done logged", "tts.done" in events, str(events))


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all() -> None:
    print("\n" + "=" * 60)
    print("  tts — test suite")
    print("=" * 60)

    test_success()
    test_custom_voice_and_model()
    test_request_body_fields()
    test_not_configured()
    test_api_error_http()
    test_api_error_network()
    test_audit_written()

    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print(f"\n{'=' * 60}")
    print(f"  Results: {passed}/{total} passed")
    print("=" * 60)
    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    run_all()
