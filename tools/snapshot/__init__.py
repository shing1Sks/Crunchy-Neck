"""tools/snapshot — desktop screenshot tool."""
from .snapshot_tool import snapshot_command
from .snapshot_types import SnapshotParams

TOOL_DEFINITION = {
    "name": "snapshot",
    "description": (
        "Capture a desktop screenshot and save it to .agent/snapshots/.\n\n"
        "Returns the workspace-relative file path plus a base64-encoded copy of the image "
        "so you can inspect the screenshot directly.\n\n"
        "Rules:\n"
        "- 'monitor=0' (default) captures all monitors combined into one image.\n"
        "- 'monitor=1' captures the primary monitor only; 2+ for additional monitors.\n"
        "- 'region' crops the capture to [x, y, width, height] pixels.\n"
        "- Set 'include_base64=false' to skip embedding the image data "
        "(useful when you only need the saved file path).\n"
        "- Requires Pillow: pip install Pillow"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "monitor": {
                "type": "integer",
                "default": 0,
                "description": "0 = all monitors combined (default); 1+ = specific monitor.",
            },
            "region": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Optional [x, y, width, height] pixel crop.",
            },
            "format": {
                "type": "string",
                "enum": ["png", "jpeg"],
                "default": "png",
                "description": "Output image format. Default 'png'.",
            },
            "include_base64": {
                "type": "boolean",
                "default": True,
                "description": (
                    "Include a base64-encoded copy of the image in the result "
                    "for direct visual inspection. Default true."
                ),
            },
        },
        "required": [],
    },
}

__all__ = ["snapshot_command", "SnapshotParams", "TOOL_DEFINITION"]
