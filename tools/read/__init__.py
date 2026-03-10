from .read_tool import read_command
from .read_types import ReadParams

TOOL_DEFINITION = {
    "name": "read",
    "description": (
        "Read a file's text content. Returns the content with metadata.\n\n"
        "Use start_line + num_lines for pagination on large files. "
        "Binary files return an error by default; set binary='base64' to get "
        "base64-encoded bytes, or binary='skip' to return empty content.\n\n"
        "Rules:\n"
        "- path may be absolute or relative to the workspace root.\n"
        "- max_bytes default is 1 MB — increase if you need more.\n"
        "- Always check the truncated field; True means you only got part of the file.\n"
        "- Use start_line=0, num_lines=N then start_line=N, num_lines=N to page through."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path. Absolute or relative to workspace root.",
            },
            "encoding": {
                "type": "string",
                "description": "Character encoding for decoding the file. Default 'utf-8'.",
                "default": "utf-8",
            },
            "max_bytes": {
                "type": "integer",
                "description": "Maximum bytes to read. Default 1048576 (1 MB).",
                "default": 1048576,
            },
            "start_line": {
                "type": "integer",
                "description": "Zero-based line index to start reading from. Default 0.",
                "default": 0,
            },
            "num_lines": {
                "type": "integer",
                "description": (
                    "Number of lines to return starting at start_line. "
                    "Omit to return all remaining lines."
                ),
            },
            "binary": {
                "type": "string",
                "enum": ["error", "base64", "skip"],
                "description": (
                    "How to handle binary files. "
                    "'error' (default) returns an error, "
                    "'base64' returns base64-encoded content, "
                    "'skip' returns empty content."
                ),
                "default": "error",
            },
        },
        "required": ["path"],
    },
}

__all__ = ["read_command", "ReadParams", "TOOL_DEFINITION"]
