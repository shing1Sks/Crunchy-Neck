"""tools/send_media — send_user_media tool entry point."""
from .send_media_tool import send_media_command
from .send_media_types import SendMediaParams

TOOL_DEFINITION = {
    "name": "send_user_media",
    "description": (
        "Send a media file (photo, document, video, or audio) to the user.\n\n"
        "Reads the file from the local workspace and uploads it to the configured medium.\n\n"
        "Rules:\n"
        "- 'path' must be relative to the workspace root.\n"
        "- 'media_type' must match the actual file content "
        "(e.g. use 'photo' for images, 'document' for PDFs/code/archives).\n"
        "- 'caption' supports plain text; it will be MarkdownV2-escaped automatically.\n"
        "- Terminal medium prints the file path and caption instead of uploading.\n"
        "- Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID "
        "in the environment or in a .env file at the workspace root."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Workspace-relative path to the file to send.",
            },
            "media_type": {
                "type": "string",
                "enum": ["photo", "document", "video", "audio"],
                "description": (
                    "Media category. "
                    "'photo' for images (JPEG/PNG/etc.), "
                    "'document' for any file sent as-is (PDF, ZIP, code, etc.), "
                    "'video' for video files, "
                    "'audio' for audio/music files."
                ),
            },
            "caption": {
                "type": "string",
                "description": "Optional caption displayed below the media.",
            },
            "medium": {
                "type": "string",
                "enum": ["telegram", "terminal"],
                "default": "telegram",
                "description": (
                    "Delivery medium. "
                    "'telegram' (default) uploads via the Telegram Bot API. "
                    "'terminal' prints the path and caption to stdout."
                ),
            },
        },
        "required": ["path", "media_type"],
    },
}

__all__ = ["send_media_command", "SendMediaParams", "TOOL_DEFINITION"]
