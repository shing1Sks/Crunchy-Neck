"""tts — synthesise speech via Inworld TTS API and save the MP3."""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from .audit import log_event
from .tts_types import TtsParams, TtsResult, TtsResultDone, TtsResultError

_TTS_ENDPOINT = "https://api.inworld.ai/tts/v1/voice"


def tts_command(
    params: TtsParams,
    *,
    workspace_root: str,
    agent_session_id: str,
) -> TtsResult:
    # ── Credentials ────────────────────────────────────────────────────────────
    load_dotenv(Path(workspace_root) / ".env", override=False)
    api_key = os.getenv("INWORLD_API_KEY", "").strip()
    if not api_key:
        detail = "INWORLD_API_KEY not set. Set it in the environment or in a .env file at the workspace root."
        log_event(event="tts.error", agent_session_id=agent_session_id,
                  workspace_root=workspace_root, error_code="not_configured", detail=detail)
        return TtsResultError(error_code="not_configured", detail=detail)

    # ── API call ───────────────────────────────────────────────────────────────
    payload = json.dumps({
        "text": params.text,
        "voiceId": params.voice_id,
        "modelId": params.model_id,
    }).encode("utf-8")

    req = urllib.request.Request(
        _TTS_ENDPOINT,
        data=payload,
        headers={
            "Authorization": f"Basic {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
            detail = body.get("message", str(exc))
        except Exception:
            detail = str(exc)
        log_event(event="tts.error", agent_session_id=agent_session_id,
                  workspace_root=workspace_root, error_code="api_error", detail=detail)
        return TtsResultError(error_code="api_error", detail=detail)
    except Exception as exc:
        log_event(event="tts.error", agent_session_id=agent_session_id,
                  workspace_root=workspace_root, error_code="api_error", detail=str(exc))
        return TtsResultError(error_code="api_error", detail=str(exc))

    # ── Decode and save ────────────────────────────────────────────────────────
    try:
        audio_bytes = base64.b64decode(result["audioContent"])
    except Exception as exc:
        log_event(event="tts.error", agent_session_id=agent_session_id,
                  workspace_root=workspace_root, error_code="api_error",
                  detail=f"Failed to decode audioContent: {exc}")
        return TtsResultError(error_code="api_error",
                              detail=f"Failed to decode audioContent: {exc}")

    out_dir = Path(workspace_root) / ".agent" / "tts"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"tts-{ts}.mp3"

    try:
        (out_dir / filename).write_bytes(audio_bytes)
    except OSError as exc:
        log_event(event="tts.error", agent_session_id=agent_session_id,
                  workspace_root=workspace_root, error_code="save_failed", detail=str(exc))
        return TtsResultError(error_code="save_failed", detail=str(exc))

    rel_path = str(Path(".agent") / "tts" / filename)
    log_event(event="tts.done", agent_session_id=agent_session_id,
              workspace_root=workspace_root, path=rel_path,
              voice_id=params.voice_id, model_id=params.model_id)

    return TtsResultDone(path=rel_path, voice_id=params.voice_id, model_id=params.model_id)
