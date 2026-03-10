"""Load Telegram Bot API credentials from env / .env file.

Required environment variables:
  TELEGRAM_BOT_TOKEN — bot token from @BotFather
  TELEGRAM_CHAT_ID   — chat_id of the conversation (same for all message types)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(Exception):
    """Raised when required Telegram env vars are missing."""


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    chat_id: str


def _load_dotenv(workspace_root: str) -> None:
    """Parse a .env file and inject keys into os.environ (existing keys are NOT overwritten)."""
    env_path = Path(workspace_root) / ".env"
    if not env_path.exists():
        return
    try:
        text = env_path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def load_config(workspace_root: str = "") -> TelegramConfig:
    """Load and validate Telegram credentials.  Raises ConfigError if any are missing."""
    if workspace_root:
        _load_dotenv(workspace_root)

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
