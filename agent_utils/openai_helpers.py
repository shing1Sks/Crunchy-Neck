"""
openai_helpers.py — OpenAI client factory and chat completion wrapper.

All OpenAI calls in this project go through chat_complete(), which enforces
reasoning_effort="low" on every call. This is the single source of truth for
that setting — never set it in callers.
"""
from __future__ import annotations

MODEL = "gpt-5.2"
REASONING_EFFORT = "low"


def make_client(api_key: str):
    """Return a configured OpenAI client."""
    import openai
    return openai.OpenAI(api_key=api_key)


def chat_complete(
    client,
    *,
    messages: list[dict],
    tools: list[dict] | None = None,
    model: str = MODEL,
):
    """
    Call chat.completions.create with reasoning_effort='low' always enforced.

    tools is omitted entirely (not passed as []) when empty — avoids API quirks
    on some model versions that reject an empty tools list.
    """
    kwargs: dict = {
        "model": model,
        "messages": messages,
        "reasoning_effort": REASONING_EFFORT,
    }
    if tools:
        kwargs["tools"] = tools
    return client.chat.completions.create(**kwargs)
