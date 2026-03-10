from .edit_tool import edit_command
from .edit_types import EditParams

TOOL_DEFINITION = {
    "name": "edit",
    "description": (
        "Surgically replace an exact string in a file without rewriting the whole file.\n\n"
        "The old string must match exactly — whitespace, indentation, and newlines included. "
        "By default the old string must appear exactly once; use allow_multiple=True to replace "
        "all occurrences. Use dry_run=True to preview the diff without writing.\n\n"
        "Rules:\n"
        "- path may be absolute or relative to the workspace root.\n"
        "- old must be an exact substring of the current file content.\n"
        "- new may be an empty string to delete old.\n"
        "- diff_preview is always returned so you can verify the change.\n"
        "- If OLD_NOT_FOUND is returned, check that indentation and line endings match exactly."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path. Absolute or relative to workspace root.",
            },
            "old": {
                "type": "string",
                "description": "Exact string to find and replace. Must appear in the file.",
            },
            "new": {
                "type": "string",
                "description": "Replacement string. May be empty to delete old.",
            },
            "encoding": {
                "type": "string",
                "description": "File encoding. Default 'utf-8'.",
                "default": "utf-8",
            },
            "allow_multiple": {
                "type": "boolean",
                "description": (
                    "If true, replace all occurrences of old. "
                    "If false (default), fail when old appears more than once."
                ),
                "default": False,
            },
            "dry_run": {
                "type": "boolean",
                "description": (
                    "If true, compute and return the diff but do not write the file. "
                    "Default false."
                ),
                "default": False,
            },
            "atomic": {
                "type": "boolean",
                "description": "Write via temp file + rename for atomicity. Default true.",
                "default": True,
            },
        },
        "required": ["path", "old", "new"],
    },
}

__all__ = ["edit_command", "EditParams", "TOOL_DEFINITION"]
