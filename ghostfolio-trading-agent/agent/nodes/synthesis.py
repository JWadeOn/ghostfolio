"""Node 4: Synthesize results — LLM call #2 to generate the trader-facing response."""

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

BASE_SYSTEM_PROMPT = """You are a trading intelligence assistant that provides data-driven market analysis.

CRITICAL RULES:
1. Every number you mention MUST come from the tool results provided below. Do not make up prices, percentages, or statistics.
2. If you are not sure about a data point, say so explicitly.
3. Always include risk context: stop loss, position sizing concerns, regime alignment.
4. Never guarantee returns or make specific price predictions without sourcing them from the data.
5. Be concise and actionable. Traders want signal, not noise.
6. Use specific numbers from the data — don't say "the stock is up" when you can say "AAPL is up 2.3% this week at $187.42"."""

INTENT_PROMPTS = {
    "price_quote": """You are answering a request for the current price or quote of a symbol.
Use the get_market_data tool results. For each symbol requested:
- Lead with the current/latest close price. State the actual date of the data (see "Latest data date" below).
- Do NOT say "Today" or "Today's session" unless the latest data date is literally today. If the data is from a past date, say "Session of [date]" or "As of [date]" (e.g. "As of December 11, 2025").
- Optionally add: open, high, low, volume for that session, or a one-line context.
Keep the response short and direct. Use only numbers from the tool results.""",

    "regime_check": """You are analyzing the current market regime. Present the 5-dimension classification clearly:
- Trend (trending_up/down/ranging)
- Volatility (low/rising/high/falling)
- Correlation (high/moderate/low)
- Breadth (broad/moderate/narrow)
- Rotation (risk_on/risk_off/mixed)

Give the composite label and explain what it means for trading. Mention which strategies tend to work in this regime.""",

    "opportunity_scan": """You are presenting trading opportunities found by the strategy scanner.
For each opportunity:
- Symbol and strategy name
- Key signals that triggered the match
- Entry, stop loss, and target levels
- Risk/reward ratio
- How it aligns (or doesn't) with the current regime

Rank by conviction and explain why the top pick stands out.""",

    "chart_validation": """You are validating a trader's chart analysis with data.
Reference specific indicator values to confirm or challenge their view.
Mention support/resistance from Bollinger Bands, SMA levels, and recent price action.
Be honest if the data doesn't support their thesis.""",

    "journal_analysis": """You are reviewing the trader's past performance.
Present win rate, average win/loss, profit factor, and hold times.
Identify behavioral patterns (holding losers too long, cutting winners short, etc).
Be constructive — suggest specific improvements based on the data.""",

    "risk_check": """You are evaluating whether a proposed trade fits the portfolio's risk parameters.
Clearly state pass/fail for each risk rule checked.
If violations exist, explain why and suggest adjustments.
Include current portfolio context (total value, cash, sector weights).""",

    "signal_archaeology": """You are analyzing historical data to explain what drove a past price move.
Walk through the indicators leading up to the move.
Identify which signals were present before the move started.
Note what regime was in place at the time.""",

    "portfolio_overview": """You are presenting the trader's portfolio snapshot.
Use the get_portfolio_snapshot tool results. Include:
- Total portfolio value and cash balance
- List of positions (symbol, quantity, value, allocation %)
- Performance summary: net P&L and total invested (total invested = cost basis: sum of what was paid for current positions; if 0 or missing, say "cost basis not available" rather than inventing a number)
- Brief interpretation: concentration, diversification, or notable exposures
Use only numbers and facts from the data; do not invent figures.""",

    "general": """You are a helpful trading assistant. Answer the trader's question naturally.
If they're asking something you can help with (market analysis, portfolio review, etc.),
suggest they ask a more specific question so you can use your tools.""",
}


def synthesize_node(state: AgentState) -> dict[str, Any]:
    """Generate the trader-facing response using Claude with tool results as context."""
    settings = get_settings()
    intent = state.get("intent", "general")
    messages = state.get("messages", [])
    tool_results = state.get("tool_results", {})
    regime = state.get("regime")
    portfolio = state.get("portfolio")
    verification_result = state.get("verification_result")
    verification_attempts = state.get("verification_attempts", 0)

    # Build system prompt
    intent_prompt = INTENT_PROMPTS.get(intent, INTENT_PROMPTS["general"])
    system = f"{BASE_SYSTEM_PROMPT}\n\n{intent_prompt}"

    # Build context from tool results
    context_parts = []
    if tool_results:
        context_parts.append("## Tool Results")
        for tool_name, result in tool_results.items():
            # Truncate very large results for the prompt
            result_str = json.dumps(result, default=str)
            if len(result_str) > 5000:
                result_str = result_str[:5000] + "... (truncated)"
            context_parts.append(f"### {tool_name}\n```json\n{result_str}\n```")

    # For price_quote (and risk_check/chart_validation that use current price), inject latest data date
    if intent in ("price_quote", "risk_check", "chart_validation"):
        md = tool_results.get("get_market_data", {})
        if md and isinstance(md, dict):
            dates = []
            for sym, data in md.items():
                if isinstance(data, list) and data:
                    last = data[-1]
                    if isinstance(last, dict) and last.get("date"):
                        dates.append(f"{sym} -> {last['date']}")
            if dates:
                context_parts.append(
                    "## Latest data date (use this — do not say 'today' unless it is today)\n"
                    + ", ".join(dates)
                )

    if regime and "detect_regime" not in tool_results:
        context_parts.append(f"## Cached Regime\n```json\n{json.dumps(regime, default=str)}\n```")

    if portfolio and "get_portfolio_snapshot" not in tool_results:
        summary = portfolio.get("summary", portfolio)
        context_parts.append(f"## Cached Portfolio Summary\n```json\n{json.dumps(summary, default=str)}\n```")

    # If re-synthesis after verification failure
    if verification_result and not verification_result.get("passed", True):
        issues = verification_result.get("issues", [])
        system += f"\n\nIMPORTANT: Your previous response had issues that need correction:\n"
        for issue in issues:
            system += f"- {issue}\n"
        system += "\nPlease regenerate your response using only the data provided. Fix the issues listed above."

    # Get user message and optional recent conversation (for "it" / "that stock" resolution)
    user_text = ""
    if messages:
        last = messages[-1]
        user_text = last.content if hasattr(last, "content") else str(last)
    recent_conv = format_recent_conversation(messages)
    if recent_conv:
        user_block = f"Recent conversation:\n{recent_conv}\n\nTrader's question: {user_text}"
    else:
        user_block = f"Trader's question: {user_text}"

    context_block = "\n\n".join(context_parts) if context_parts else "No tool results available."

    try:
        llm = ChatAnthropic(
            model="claude-sonnet-4-20250514",
            api_key=settings.anthropic_api_key,
            max_tokens=2048,
            temperature=0.3,
        )

        response = llm.invoke([
            SystemMessage(content=system),
            HumanMessage(content=f"{user_block}\n\n{context_block}"),
        ])

        synthesis = response.content.strip()
        logger.info(f"Synthesis generated ({len(synthesis)} chars)")

        return {
            "synthesis": synthesis,
            "verification_attempts": verification_attempts,
        }

    except Exception as e:
        logger.error(f"Synthesis failed: {e}")
        return {
            "synthesis": f"I encountered an error generating the analysis: {str(e)}. "
                        f"The raw data from the tools is available in the response.",
            "verification_attempts": verification_attempts,
        }
