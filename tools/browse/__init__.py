from .browse_tool import browse_command
from .browse_types import BrowseParams

TOOL_DEFINITION = {
    "name": "browse",
    "description": (
        "Launch Scout, the computer-use subagent, to control Chrome or the Windows desktop.\n\n"
        "PRIMARY use: desktop GUI automation (mode='desktop') — controlling any Windows app, "
        "file dialogs, non-browser GUIs (Notepad, File Explorer, etc.).\n\n"
        "WEB FALLBACK use: when agent-browser CLI has already been attempted and failed "
        "(CAPTCHA, auth wall, broken page, non-zero exit). "
        "Do NOT use as first choice for web tasks — try agent-browser via exec() first.\n\n"
        "Do NOT use for: tasks exec/read/write can handle, or any web task you haven't "
        "tried agent-browser for first."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": (
                    "Complete natural-language instruction for Scout. "
                    "Be specific — include exact URLs, app names, button labels, "
                    "and what data to return."
                ),
            },
            "mode": {
                "type": "string",
                "enum": ["browser", "desktop"],
                "description": (
                    "'browser' = Chrome with persistent profile (default). "
                    "'desktop' = full Windows control."
                ),
                "default": "browser",
            },
            "launch_browser": {
                "type": "boolean",
                "description": (
                    "Launch a new Chrome window before starting. Default true. "
                    "Set false if Chrome is already open on the right page."
                ),
                "default": True,
            },
            "max_turns": {
                "type": "integer",
                "description": (
                    "Hard cap on Scout's action loop. Default 60. "
                    "Increase to 100+ for long multi-step flows."
                ),
                "default": 60,
            },
        },
        "required": ["task"],
    },
}

__all__ = ["browse_command", "BrowseParams", "TOOL_DEFINITION"]
