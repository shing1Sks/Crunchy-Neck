"""
tool_schemas.py — OpenAI function-calling schema list for all agent tools.

Re-uses TOOL_DEFINITION dicts from each tool's __init__.py (canonical source).
Adds OpenAI's built-in web_search_preview tool.
"""
from __future__ import annotations

from tools import (
    EXEC_TOOL,
    PROCESS_TOOL,
    READ_TOOL,
    WRITE_TOOL,
    EDIT_TOOL,
    REMEMBER_TOOL,
    PING_TOOL,
    SEND_MEDIA_TOOL,
    SNAPSHOT_TOOL,
    TTS_TOOL,
    IMAGE_GEN_TOOL,
)

_CUSTOM_TOOLS = [
    EXEC_TOOL,
    PROCESS_TOOL,
    READ_TOOL,
    WRITE_TOOL,
    EDIT_TOOL,
    REMEMBER_TOOL,
    PING_TOOL,
    SEND_MEDIA_TOOL,
    SNAPSHOT_TOOL,
    TTS_TOOL,
    IMAGE_GEN_TOOL,
]


def get_openai_tools() -> list[dict]:
    """
    Return all tool schemas in OpenAI function-calling format:
        [{"type": "function", "function": <TOOL_DEFINITION>}, ...]
    plus the built-in web_search_preview tool.
    """
    return [{"type": "function", "function": t} for t in _CUSTOM_TOOLS]
