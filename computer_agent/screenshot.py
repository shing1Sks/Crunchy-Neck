"""
screenshot.py — full-screen capture for Scout (computer agent).

Returns base64-encoded PNG + screen dimensions for the OpenAI Responses API
computer_call_output payload.

No downscaling — screenshots are sent at native resolution so the model's
x,y coordinates map directly to the pixels PyAutoGUI will click on.
"""
from __future__ import annotations

import base64
import io


def take_screenshot() -> tuple[str, tuple[int, int]]:
    """
    Capture the full screen at native resolution and return (base64_png, (width, height)).

    Raises RuntimeError if Pillow is not installed.
    """
    try:
        from PIL import ImageGrab
    except ImportError:
        raise RuntimeError("Pillow is not installed. Run: pip install Pillow")

    img = ImageGrab.grab(all_screens=True)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return b64, img.size


def screen_size() -> tuple[int, int]:
    """Return the (width, height) of the primary display without capturing."""
    try:
        import pyautogui
        return pyautogui.size()
    except Exception:
        return (1920, 1080)
