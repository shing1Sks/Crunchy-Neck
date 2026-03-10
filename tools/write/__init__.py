from .write_tool import write_command
from .write_types import WriteParams

TOOL_DEFINITION = {
    "name": "write",
    "description": (
        "Create a new file or fully overwrite an existing one with the given content.\n\n"
        "Rules:\n"
        "- path may be absolute or relative to the workspace root.\n"
        "- Parent directories are created automatically by default (create_parents=True).\n"
        "- Existing files are overwritten by default (overwrite=True). "
        "Set overwrite=False to fail instead.\n"
        "- Writes are atomic by default (temp file + rename) to prevent partial writes.\n"
        "- max_bytes default is 10 MB — content larger than this is rejected.\n"
        "- Check bytes_written in the result to confirm how much was saved."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path. Absolute or relative to workspace root.",
            },
            "content": {
                "type": "string",
                "description": "Full text content to write to the file.",
            },
            "encoding": {
                "type": "string",
                "description": "Character encoding for writing. Default 'utf-8'.",
                "default": "utf-8",
            },
            "create_parents": {
                "type": "boolean",
                "description": "Create missing parent directories automatically. Default true.",
                "default": True,
            },
            "overwrite": {
                "type": "boolean",
                "description": (
                    "Allow overwriting an existing file. "
                    "Set to false to fail if the file already exists. Default true."
                ),
                "default": True,
            },
            "atomic": {
                "type": "boolean",
                "description": (
                    "Write via a temp file then rename for atomicity. "
                    "Prevents partial writes on crash. Default true."
                ),
                "default": True,
            },
            "max_bytes": {
                "type": "integer",
                "description": "Maximum content size in bytes. Default 10485760 (10 MB).",
                "default": 10485760,
            },
        },
        "required": ["path", "content"],
    },
}

__all__ = ["write_command", "WriteParams", "TOOL_DEFINITION"]
