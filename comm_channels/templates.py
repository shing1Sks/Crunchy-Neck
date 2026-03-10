"""Message format templates for each type × medium combination.

All user-supplied dynamic text MUST be passed through escape_mdv2() before
insertion into any MarkdownV2 template.  The structural Markdown characters
added by the template itself (e.g. *bold*, _italic_) must NOT be escaped.
"""
from __future__ import annotations

import re

# Characters that must be escaped in Telegram MarkdownV2 when they appear
# in user-supplied content (not in the template's own markup).
_MDV2_RE = re.compile(r'([_*\[\]()~`>#+\-=|{}.!\\])')


def escape_mdv2(text: str) -> str:
    """Escape arbitrary text for safe inclusion in a MarkdownV2 message."""
    return _MDV2_RE.sub(r'\\\1', text)


# ─── Telegram renderers (return MarkdownV2 strings) ───────────────────────────

def render_telegram_update(title: str | None, msg: str) -> str:
    body = escape_mdv2(msg)
    if title:
        return f"*{escape_mdv2(title)}*\n\n{body}"
    return body


def render_telegram_chat(msg: str) -> str:
    return escape_mdv2(msg)


def render_telegram_query_msg(msg: str) -> str:
    return escape_mdv2(msg)


def render_telegram_query_options(msg: str) -> str:
    return escape_mdv2(msg) + "\n\n_Choose one of the options below:_"


# ─── Terminal renderers (return plain text strings) ───────────────────────────

_SEP = "\u2500" * 50   # ─────────────────────────────────


def render_terminal_update(title: str | None, msg: str) -> str:
    if title:
        return f"\n{_SEP}\n[UPDATE] {title}\n{_SEP}\n{msg}\n{_SEP}"
    return f"\n{_SEP}\n[UPDATE]\n{_SEP}\n{msg}\n{_SEP}"


def render_terminal_chat(msg: str) -> str:
    return f"[AGENT] {msg}"


def render_terminal_query_msg(msg: str) -> str:
    return f"[QUERY] {msg}"


def render_terminal_options(options: list[str]) -> str:
    return "\n".join(f"  {i + 1}. {opt}" for i, opt in enumerate(options))
