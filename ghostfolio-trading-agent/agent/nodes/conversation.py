"""Helpers for using conversation history in agent nodes."""

from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

# Max number of previous messages to include for context (excluding current user message)
MAX_RECENT_MESSAGES = 6


def format_recent_conversation(messages: list) -> str:
    """Format the most recent conversation turns for context (excluding the latest message).

    Used so the model can resolve pronouns like 'it' or 'that stock' from prior turns.
    """
    if not messages or len(messages) <= 1:
        return ""

    previous = messages[:-1]
    to_show = previous[-MAX_RECENT_MESSAGES:]
    parts = []
    for msg in to_show:
        if isinstance(msg, HumanMessage):
            content = getattr(msg, "content", str(msg))
            parts.append(f"User: {content}")
        elif isinstance(msg, AIMessage):
            content = getattr(msg, "content", str(msg))
            if isinstance(content, str) and len(content) > 500:
                content = content[:500] + "..."
            parts.append(f"Assistant: {content}")
        elif isinstance(msg, BaseMessage):
            content = getattr(msg, "content", str(msg))
            parts.append(f"{type(msg).__name__}: {content}")
        else:
            parts.append(str(msg))
    return "\n".join(parts)
