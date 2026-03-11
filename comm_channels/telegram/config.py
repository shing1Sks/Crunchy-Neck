"""Load Telegram Bot API credentials from env / .env file.

Required environment variables:
  TELEGRAM_BOT_TOKEN — bot token from @BotFather
  TELEGRAM_CHAT_ID   — chat_id of the conversation (same for all message types)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(Exception):
    """Raised when required Telegram env vars are missing."""


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    chat_id: str


def load_config(workspace_root: str = "") -> TelegramConfig:
    """Load and validate Telegram credentials.  Raises ConfigError if any are missing."""
    if workspace_root:
        load_dotenv(Path(workspace_root) / ".env", override=False)
 
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    missing = [
        name
        for name, val in [
            ("TELEGRAM_BOT_TOKEN", token),
            ("TELEGRAM_CHAT_ID", chat_id),
        ]
        if not val
    ]
    if missing:
        raise ConfigError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Set them in the environment or in a .env file at the workspace root."
        )
    return TelegramConfig(bot_token=token, chat_id=chat_id)
