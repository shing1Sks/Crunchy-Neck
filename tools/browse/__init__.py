from .browse_tool import browse_command
from .browse_types import BrowseParams

TOOL_DEFINITION = {
    "name": "browse",
    "description": (
        "Delegate a browser or desktop GUI task to Scout, the computer-use subagent.\n\n"
        "Scout controls Chrome (browser mode) or the full Windows desktop (desktop mode) "
        "and returns what it found or did.\n\n"
        "Use for: web scraping, form filling, GUI automation, navigating apps, "
        "extracting on-screen data, clicking through multi-step flows.\n\n"
        "Do NOT use for: tasks that exec/read/write can handle directly."
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
