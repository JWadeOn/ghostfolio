"""Node 1: Intent classification — LLM call to classify the trader's message."""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage

from agent.config import get_settings
from agent.state import AgentState
from agent.nodes.conversation import format_recent_conversation

logger = logging.getLogger(__name__)

INTENT_SYSTEM_PROMPT = """You are the intent classifier for a trading intelligence agent.
Given the trader's message, classify it into one of these categories:

- price_quote: asking for current price, "trading at", "what's X at", quote, or last price for a symbol (e.g. "What's GOOG trading at?", "AAPL price?", "current price of MSFT")
- regime_check: asking about current market conditions, regime, environment, macro outlook
- opportunity_scan: asking to find setups, scan watchlist, find trades, screen stocks
- chart_validation: asking about specific support/resistance levels, patterns, chart analysis for a symbol
- journal_analysis: asking about their past trading performance, behavioral patterns, trade review
- risk_check: asking whether a specific trade fits their portfolio, position sizing
- signal_archaeology: asking about what predicted a past big move, historical analysis
- portfolio_overview: asking to see their portfolio, holdings, positions, allocations, or "how is my portfolio doing"
- general: greeting, general question, unclear, or request that doesn't fit above categories

Also extract parameters from the message:
- symbols: any ticker symbols mentioned (e.g., AAPL, TSLA)
- timeframe: any time period mentioned (e.g., "90 days", "last month")
- strategy: any strategy names mentioned
- price_levels: any specific price levels mentioned
- dollar_amount: any dollar amounts mentioned
- direction: long or short if mentioned

If "Recent conversation" is provided: the current message may use pronouns or references ("it", "that stock", "should I buy?", "what about that one?"). Resolve these from the recent conversation (e.g. user previously asked "What is Tesla trading at?" so "it" / "should I buy it?" refers to Tesla → include "TSLA" in params.symbols).

Respond in JSON format only:
{
  "intent": "<one of the categories above>",
  "params": {
    "symbols": [],
    "timeframe": null,
    "strategy": null,
    "price_levels": [],
    "dollar_amount": null,
    "direction": null
  }
}"""


def _build_intent_payload(messages: list, user_text: str) -> str:
    """Build the user payload, including recent conversation when available."""
    recent = format_recent_conversation(messages)
    if recent:
        return f"Recent conversation:\n{recent}\n\nCurrent message: {user_text}"
    return user_text


def classify_intent_node(state: AgentState) -> dict[str, Any]:
    """Classify the user's intent and extract parameters using Claude."""
    settings = get_settings()
    messages = state.get("messages", [])

    if not messages:
        return {
            "intent": "general",
            "extracted_params": {},
        }

    # Get the latest user message
    last_message = messages[-1]
    user_text = last_message.content if hasattr(last_message, "content") else str(last_message)

    try:
        llm = ChatAnthropic(
            model="claude-sonnet-4-20250514",
            api_key=settings.anthropic_api_key,
            max_tokens=512,
            temperature=0,
        )

        response = llm.invoke([
            SystemMessage(content=INTENT_SYSTEM_PROMPT),
            HumanMessage(content=_build_intent_payload(messages, user_text)),
        ])

        # Parse JSON from response
        response_text = response.content.strip()
        # Handle potential markdown code blocks
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        parsed = json.loads(response_text)
        intent = parsed.get("intent", "general")
        params = parsed.get("params", {})

        logger.info(f"Classified intent: {intent} with params: {params}")

        return {
            "intent": intent,
            "extracted_params": params,
        }

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse intent JSON: {e}")
        return {
            "intent": "general",
            "extracted_params": {},
        }
    except Exception as e:
        logger.error(f"Intent classification failed: {e}")
        return {
            "intent": "general",
            "extracted_params": {},
        }
