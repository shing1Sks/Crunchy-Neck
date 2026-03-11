"""tools/ping — ping_user tool entry point."""
from comm_channels.ping_types import PingParams
from .ping_tool import ping_command

TOOL_DEFINITION = {
    "name": "ping_user",
    "description": (
        "Send a message or query to the user via Telegram or terminal.\n\n"
        "Types:\n"
        "- 'update': one-way status broadcast to a channel. "
        "Edits the previous update message in-place (avoids spam) when edit_last_update=true.\n"
        "- 'chat': informational message to the user's DM. No reply expected.\n"
        "- 'query:msg': ask the user a free-text question via DM. "
        "Blocks until the user replies or timeout elapses.\n"
        "- 'query:options': present labeled inline buttons via DM. "
        "Blocks until the user taps a button or timeout elapses.\n\n"
        "Rules:\n"
        "- 'query:options' requires a non-empty options list.\n"
        "- All message types go to the same TELEGRAM_CHAT_ID.\n"
        "- Query types block the agent until a response arrives or timeout elapses.\n"
        "- On timeout: status='error', error_code='timeout'.\n"
        "- Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID "
        "in the environment or in a .env file at the workspace root."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "msg": {
                "type": "string",
                "description": "The message body to send.",
            },
            "type": {
                "type": "string",
                "enum": ["update", "chat", "query:msg", "query:options"],
                "description": (
                    "Message type. "
                    "'update' = status broadcast (one-way, edits in-place), "
                    "'chat' = informational message (one-way), "
                    "'query:msg' = free-text question (blocking), "
                    "'query:options' = button-choice question (blocking)."
                ),
            },
            "medium": {
                "type": "string",
                "enum": ["telegram", "terminal"],
                "default": "telegram",
                "description": (
                    "Delivery medium. "
                    "'telegram' (default) uses the Telegram Bot API. "
                    "'terminal' uses print/input — useful for local testing without a bot token."
                ),
            },
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Required for type='query:options'. "
                    "Labels for the inline keyboard buttons (one per row)."
                ),
            },
            "title": {
                "type": "string",
                "description": (
                    "Optional title displayed in bold above the message body. "
                    "Only used for type='update'."
                ),
            },
            "timeout": {
                "type": "integer",
                "default": 120,
                "description": "Seconds to wait for a reply on query types. Default 120.",
            },
            "edit_last_update": {
                "type": "boolean",
                "default": True,
                "description": (
                    "For type='update': edit the previous update message in-place "
                    "instead of sending a new one. Reduces channel spam. Default true."
                ),
            },
        },
        "required": ["msg", "type"],
    },
}

__all__ = ["ping_command", "PingParams", "TOOL_DEFINITION"]
