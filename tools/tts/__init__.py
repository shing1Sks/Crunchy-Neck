"""tools/tts — text-to-speech via Inworld TTS API."""
from .tts_tool import tts_command
from .tts_types import TtsParams

TOOL_DEFINITION = {
    "name": "tts",
    "description": (
        "Synthesise speech from text using the Inworld TTS API and save the result as an MP3.\n\n"
        "Returns the workspace-relative path to the saved audio file.\n\n"
        "Rules:\n"
        "- Requires INWORLD_API_KEY in the environment or in a .env file at the workspace root.\n"
        "- The API key is already base64-encoded as provided by Inworld.\n"
        "- Audio is saved to .agent/tts/ with a timestamp filename.\n"
        "- Use send_user_media() with media_type='audio' to send the file to the user."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The text to synthesise into speech.",
            },
            "voice_id": {
                "type": "string",
                "default": "Ashley",
                "description": "Inworld voice name. Default: 'Ashley'.",
            },
            "model_id": {
                "type": "string",
                "default": "inworld-tts-1.5-max",
                "description": "Inworld TTS model ID. Default: 'inworld-tts-1.5-max'.",
            },
        },
        "required": ["text"],
    },
}

__all__ = ["tts_command", "TtsParams", "TOOL_DEFINITION"]
