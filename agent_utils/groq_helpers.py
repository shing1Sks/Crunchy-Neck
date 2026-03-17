"""
groq_helpers.py — Groq client factory and chat completion wrapper for open-crunchy.

All Groq calls go through groq_chat_complete(). Unlike the OpenAI wrapper,
reasoning_effort is NOT passed — Kimi K2 on Groq does not support it.

Groq exposes an OpenAI-compatible API at GROQ_BASE_URL; the standard
openai package works unchanged with a different base_url + api_key.
"""
from __future__ import annotations

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL    = "moonshotai/kimi-k2-instruct-0905"


def make_groq_client(api_key: str):
    """Return a Groq-backed OpenAI-compatible client."""
    import openai
    return openai.OpenAI(base_url=GROQ_BASE_URL, api_key=api_key)


def groq_chat_complete(
    client,
    *,
    messages: list[dict],
    tools: list[dict] | None = None,
    model: str = GROQ_MODEL,
):
    """
    Call Groq's chat completions endpoint.

    Intentionally omits reasoning_effort — Kimi K2 does not support it on Groq.
    tools is omitted entirely when empty (avoids API quirks with empty lists).
    """
    kwargs: dict = {
        "model": model,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools
    return client.chat.completions.create(**kwargs)
