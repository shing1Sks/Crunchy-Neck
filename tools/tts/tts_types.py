"""Type definitions for the tts tool."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union


@dataclass
class TtsParams:
    text: str
    """The text to synthesise into speech."""

    voice_id: str = "Ashley"
    """Inworld voice name. Default: 'Ashley'."""

    model_id: str = "inworld-tts-1.5-mini"
    """Inworld TTS model ID. Default: 'inworld-tts-1.5-mini'."""


# ─── Result types ─────────────────────────────────────────────────────────────

@dataclass(kw_only=True)
class TtsResultDone:
    status: Literal["done"] = "done"
    path: str
    """Workspace-relative path to the saved .mp3 file."""
    voice_id: str
    model_id: str


@dataclass(kw_only=True)
class TtsResultError:
    status: Literal["error"] = "error"
    error_code: Literal["not_configured", "api_error", "save_failed"]
    detail: str


TtsResult = Union[TtsResultDone, TtsResultError]
