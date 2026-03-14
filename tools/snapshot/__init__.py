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
        "- 'filename' sets the saved file name (e.g. 'empty_state.png'). "
        "If omitted, a timestamp name is used.\n"
        "- 'x1, y1, x2, y2' crops the capture to a region (top-left to bottom-right). "
        "All four must be provided together.\n"
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
            "filename": {
                "type": "string",
                "description": (
                    "Custom filename for the saved file, e.g. 'empty_state.png'. "
                    "Saved to .agent/snapshots/{filename}. If omitted, a timestamp name is used."
                ),
            },
            "x1": {"type": "integer", "description": "Left edge of capture region (pixels)."},
            "y1": {"type": "integer", "description": "Top edge of capture region (pixels)."},
            "x2": {"type": "integer", "description": "Right edge of capture region (pixels)."},
            "y2": {"type": "integer", "description": "Bottom edge of capture region (pixels)."},
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
