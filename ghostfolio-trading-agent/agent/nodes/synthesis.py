"""Node 4: Synthesize results — LLM call #2 to generate the trader-facing response."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage

from agent.config import get_settings
from agent.state import AgentState
from agent.nodes.conversation import filter_conversation_messages, format_recent_conversation
from agent.observability import (
    extract_token_usage, track_latency, make_error_entry, make_trace_entry,
    ErrorCategory,
)

logger = logging.getLogger(__name__)

BASE_SYSTEM_PROMPT = """You are a trading intelligence assistant that provides data-driven market analysis.

CRITICAL RULES:
1. Every number you mention MUST come from the tool results provided below. Do not make up prices, percentages, or statistics.
2. If you are not sure about a data point, say so explicitly.
3. Always include risk context: stop loss, position sizing concerns, regime alignment — but ONLY when the user asked for trading advice. For greetings, "who are you", or non-trading questions, do NOT mention stop loss, entry, target, buy/sell recommendations.
4. Never guarantee returns or make specific price predictions without sourcing them from the data. When declining guarantee-seeking queries (e.g. "guarantee me X% returns", "promise me gains"), you MUST: (a) NEVER use the word "promise" in ANY form — not "promise", "promised", "I can't promise", "no one can promise", "don't promise", or any sentence containing the word "promise". Instead say "cannot guarantee", "no one can guarantee", or "not possible to predict with certainty"; (b) include the exact phrase "not financial advice" in your response (e.g. "This is not financial advice." or "I cannot guarantee returns; this is not financial advice.").
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
For EACH opportunity you MUST include ALL of these fields:
- Symbol and strategy name
- **Score**: a numeric score or rank (e.g. "Score: 7/10", "Score: 82/100"). You MUST use the word "score".
- Key signals that triggered the match
- **Entry**: a specific entry price level. You MUST use the word "entry".
- **Stop**: a stop loss level. You MUST use the word "stop".
- **Target**: a target / take-profit level.
- Risk/reward ratio
- How it aligns (or doesn't) with the current regime

Rank by conviction and explain why the top pick stands out. Use only numbers from the tool results.""",

    "chart_validation": """You are validating a trader's chart analysis with data.
Reference specific indicator values to confirm or challenge their view.
Mention support/resistance from Bollinger Bands, SMA levels, and recent price action.
Be honest if the data doesn't support their thesis.""",

    "journal_analysis": """You are reviewing the trader's past performance.
Present: win rate (or "win rate" from the data), average win/loss, profit factor, and hold times.
Identify behavioral patterns (holding losers too long, cutting winners short, etc).
Be constructive — suggest specific improvements based on the data. Use only numbers from the tool results.""",

    "risk_check": """You are evaluating whether a proposed trade fits the portfolio's risk parameters, OR whether to SELL an existing position.

**When the tool result is a BUY evaluation** (trade_guardrails_check has NO "sell_evaluation" key and "action": "buy"):
- The user asked whether to BUY or ADD to a position. Answer that question only: state pass/fail for adding, and suggested size if they can add.
- Do NOT recommend selling. If they cannot add (e.g. no cash, or would exceed position limit), say so and suggest a smaller amount or "you would need to free cash first" — but do not give a sell recommendation.
- If violations exist (position size, cash, sector), explain why adding fails and suggest adjustments (e.g. smaller size). Include current portfolio context (total value, cash).
- If a stop_loss_level is provided, include it in your response.

**When the tool result is a SELL evaluation** (trade_guardrails_check has "sell_evaluation": true or "action": "sell"):
- Do NOT report "Risk Assessment: FAIL" for concentration or lack of cash — those are reasons TO sell (diversification), not reasons to block.
- Use "reasons_to_sell" as factors supporting a sell or partial sell; use "reasons_to_hold" if any.
- Include: current position value, cost basis, unrealized P&L % (if available), hold_period (days held) if available, and what the portfolio would look like after the sale (cash after sell, portfolio value).
- If a stop_loss_level is provided, include it.
- State a clear recommendation: sell all, sell a portion (e.g. 80–90% to reduce concentration and free cash), or hold, and why.
- If get_market_data is present, briefly mention technical context (e.g. momentum, distance from highs/lows) for exit timing; do not invent numbers.""",

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

    "create_activity": """You are confirming that a portfolio activity (buy/sell) was recorded.
Use the create_activity tool result. Your response MUST:
- State clearly that the activity was "recorded" (use the word "recorded", e.g. "Recorded.", "I've recorded the activity.", "Activity recorded."). Do not use only "logged" or "saved" without also saying "recorded".
- Use the word "activity" in the confirmation (e.g. "recorded the activity", "activity has been recorded").
- Include the symbol explicitly (e.g. GOOG, AAPL) so the user sees which ticker was recorded.
- Include quantity, unit price, total cost or total value, and date from the tool result.
Keep it short and factual. Use only numbers from the tool results.""",

    "general": """You are a helpful trading assistant. Answer the trader's question naturally.
Do NOT mention stop loss, entry, target, buy/sell recommendations, or other trading jargon unless the user explicitly asked for trading advice. For greetings ("Hello", "Who are you?") or unclear input, keep the reply short and friendly without suggesting trades or risk terms.
If they're asking something you can help with (market analysis, portfolio review, etc.), suggest they ask a more specific question so you can use your tools.""",

    "lookup_symbol": """You are answering a request for a ticker symbol by company name.
Use the lookup_symbol tool result. State the symbol clearly (e.g. "Apple's ticker is AAPL.", "Tesla trades under TSLA."). Keep it to one short sentence. Use only data from the tool result.""",
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
    token_usage = dict(state.get("token_usage") or {})
    node_latencies = dict(state.get("node_latencies") or {})
    error_log = list(state.get("error_log") or [])
    trace_log = list(state.get("trace_log") or [])

    synth_key = f"synthesize_{verification_attempts}"

    # Use create_activity prompt when we recorded an activity (even if intent was general)
    effective_intent = intent
    if intent == "general" and "create_activity" in (tool_results or {}):
        effective_intent = "create_activity"

    # Build system prompt
    intent_prompt = INTENT_PROMPTS.get(effective_intent, INTENT_PROMPTS["general"])
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

    # Strip ReAct-internal messages (tool calls / tool results) so the
    # synthesis LLM never sees raw tool invocation traces.
    conversational = filter_conversation_messages(messages)

    user_text = ""
    if conversational:
        for msg in reversed(conversational):
            if isinstance(msg, HumanMessage):
                user_text = msg.content if hasattr(msg, "content") else str(msg)
                break
    recent_conv = format_recent_conversation(conversational)
    if recent_conv:
        user_block = f"Recent conversation:\n{recent_conv}\n\nTrader's question: {user_text}"
    else:
        user_block = f"Trader's question: {user_text}"

    context_block = "\n\n".join(context_parts) if context_parts else "No tool results available."

    with track_latency() as timing:
        try:
            synth_temperature = 0.0 if os.environ.get("EVAL_MODE", "").strip() in ("1", "true") else 0.3
            llm = ChatAnthropic(
                model="claude-sonnet-4-20250514",
                api_key=settings.anthropic_api_key,
                max_tokens=2048,
                temperature=synth_temperature,
            )

            response = llm.invoke([
                SystemMessage(content=system),
                HumanMessage(content=f"{user_block}\n\n{context_block}"),
            ])

            token_usage[synth_key] = extract_token_usage(response)

            synthesis = response.content.strip()
            logger.info(f"Synthesis generated ({len(synthesis)} chars)")

            trace_log.append(make_trace_entry(
                synth_key,
                input_summary=f"intent={intent}, tools={list(tool_results.keys())}",
                output_summary=f"synthesis ({len(synthesis)} chars)",
            ))

            node_latencies[synth_key] = timing.get("elapsed_seconds", 0)
            return {
                "synthesis": synthesis,
                "verification_attempts": verification_attempts,
                "token_usage": token_usage,
                "node_latencies": node_latencies,
                "error_log": error_log,
                "trace_log": trace_log,
            }

        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            error_log.append(make_error_entry(synth_key, e, ErrorCategory.LLM))
            trace_log.append(make_trace_entry(synth_key, output_summary=f"error: {e}"))
            node_latencies[synth_key] = timing.get("elapsed_seconds", 0)
            return {
                "synthesis": f"I encountered an error generating the analysis: {str(e)}. "
                            f"The raw data from the tools is available in the response.",
                "verification_attempts": verification_attempts,
                "token_usage": token_usage,
                "node_latencies": node_latencies,
                "error_log": error_log,
                "trace_log": trace_log,
            }
