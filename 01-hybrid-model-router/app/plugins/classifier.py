"""Decides whether a chat request is standard (vLLM) or complex (Bedrock)."""

from enum import Enum
from typing import Any

COMPLEX_TOKEN_THRESHOLD = 2000
CHARS_PER_TOKEN = 4
REASONING_TAG = "reasoning"


class Tier(Enum):
    STANDARD = "standard"
    COMPLEX = "complex"


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    return ""


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Rough token count: about four characters per token, no tokenizer needed."""
    characters = sum(len(_message_text(message.get("content"))) for message in messages)
    return characters // CHARS_PER_TOKEN


def last_user_text(messages: list[dict[str, Any]]) -> str:
    """Text of the most recent user message: the task the request is asking for."""
    for message in reversed(messages):
        if message.get("role") == "user":
            return _message_text(message.get("content"))
    return ""


def classify(messages: list[dict[str, Any]], tags: list[str]) -> Tier:
    if REASONING_TAG in tags:
        return Tier.COMPLEX
    if estimate_tokens(messages) > COMPLEX_TOKEN_THRESHOLD:
        return Tier.COMPLEX
    return Tier.STANDARD
