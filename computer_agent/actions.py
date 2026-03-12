"""
actions.py — PyAutoGUI action executor for Scout (GA computer tool format).

Receives one action dict from the GA Responses API computer_call.actions[] array
and executes it. Returns a short description string for ping_user updates.

GA field names (new):
    type: str              — discriminator  (was "action")
    x, y: int              — coordinates    (was "coordinate": [x, y])
    keys: list[str]        — key combo      (was "key": "ctrl+c")
    scroll_x, scroll_y     — scroll deltas  (was "direction"/"amount")
    path: [{x,y}, ...]     — drag waypoints (was "startCoordinate"/"endCoordinate")

Settle delays:
    type / screenshot / wait — no extra sleep
    key with enter/tab       — 2.5s
    everything else          — 2.0s
"""
from __future__ import annotations

import asyncio

import pyautogui

pyautogui.FAILSAFE = True   # move mouse to top-left corner to abort
pyautogui.PAUSE = 0.2       # small inter-step pause on top of our settle delays

_DEFAULT_DELAY  = 2.0
_NAVIGATE_DELAY = 2.5       # enter / return / tab — likely page transition
_TYPE_DELAY     = 1.0       # typing doesn't trigger navigation

_NAVIGATE_KEYS = {"enter", "return", "tab"}


async def execute_action(action: dict) -> str:
    """
    Execute one GA CUA action dict and return a short description.

    The caller is responsible for taking a fresh screenshot after each
    computer_call batch (not after each individual action).
    """
    action_type = action.get("type", "")

    # ── screenshot ────────────────────────────────────────────────────────────
    if action_type == "screenshot":
        return "screenshot_requested"

    # ── click ─────────────────────────────────────────────────────────────────
    if action_type == "click":
        x, y = action["x"], action["y"]
        button = action.get("button", "left")
        pyautogui.click(x, y, button=button)
        await _settle(_DEFAULT_DELAY)
        return f"clicked ({x}, {y})"

    # ── double_click ──────────────────────────────────────────────────────────
    if action_type == "double_click":
        x, y = action["x"], action["y"]
        pyautogui.doubleClick(x, y)
        await _settle(_DEFAULT_DELAY)
        return f"double-clicked ({x}, {y})"

    # ── type ──────────────────────────────────────────────────────────────────
    if action_type == "type":
        text = action.get("text", "")
        if all(ord(c) < 128 for c in text):
            # Pure ASCII — pyautogui.write() is reliable
            pyautogui.write(text, interval=0.04)
        else:
            # Contains non-ASCII (em dashes, curly quotes, accents, etc.)
            # pyautogui.write() silently drops or corrupts these characters.
            # Use clipboard paste instead — preserves the exact string.
            import pyperclip
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
        await _settle(_TYPE_DELAY)
        preview = text[:40] + ("..." if len(text) > 40 else "")
        return f"typed: {preview!r}"

    # ── keypress ──────────────────────────────────────────────────────────────
    if action_type == "keypress":
        keys: list[str] = action.get("keys", [])
        if not keys:
            return "keypress: no keys"
        lower_keys = [k.lower() for k in keys]
        if len(lower_keys) > 1:
            pyautogui.hotkey(*lower_keys)
        else:
            pyautogui.press(lower_keys[0])
        is_nav = bool(set(lower_keys) & _NAVIGATE_KEYS)
        delay = _NAVIGATE_DELAY if is_nav else _DEFAULT_DELAY
        await _settle(delay)
        return f"pressed: {'+'.join(lower_keys)}"

    # ── scroll ────────────────────────────────────────────────────────────────
    if action_type == "scroll":
        x, y = action.get("x", 0), action.get("y", 0)
        scroll_y = int(action.get("scroll_y", 0))
        scroll_x = int(action.get("scroll_x", 0))
        pyautogui.moveTo(x, y)
        if scroll_y:
            # API: positive scroll_y = scroll down; pyautogui: positive = up
            pyautogui.scroll(-scroll_y)
        if scroll_x:
            pyautogui.hscroll(-scroll_x)
        await _settle(_DEFAULT_DELAY)
        return f"scrolled (dx={scroll_x}, dy={scroll_y}) at ({x}, {y})"

    # ── move ──────────────────────────────────────────────────────────────────
    if action_type == "move":
        x, y = action["x"], action["y"]
        pyautogui.moveTo(x, y, duration=0.2)
        await _settle(_DEFAULT_DELAY)
        return f"moved mouse to ({x}, {y})"

    # ── drag ──────────────────────────────────────────────────────────────────
    if action_type == "drag":
        path: list[dict] = action.get("path", [])
        if len(path) < 2:
            return "drag: path too short"
        start = path[0]
        pyautogui.mouseDown(start["x"], start["y"], button="left")
        for wp in path[1:]:
            pyautogui.moveTo(wp["x"], wp["y"], duration=0.1)
        pyautogui.mouseUp()
        await _settle(_DEFAULT_DELAY)
        end = path[-1]
        return f"dragged ({start['x']},{start['y']}) -> ({end['x']},{end['y']})"

    # ── wait ──────────────────────────────────────────────────────────────────
    if action_type == "wait":
        await asyncio.sleep(2.0)
        return "waited 2s"

    return f"unknown action ignored: {action_type!r}"


async def _settle(seconds: float) -> None:
    """Non-blocking sleep to let the screen render before the next screenshot."""
    if seconds > 0:
        await asyncio.sleep(seconds)
