"""ReAct agent node — LLM with bound tools that adaptively chooses actions."""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from agent.config import get_settings
from agent.state import AgentState
from agent.tools.langchain_tools import get_tools

logger = logging.getLogger(__name__)

MAX_REACT_STEPS = 10

REACT_SYSTEM_PROMPT = """You are a trading intelligence agent with access to these tools: get_market_data, get_portfolio_snapshot, detect_regime, scan_strategies, portfolio_guardrails_check, trade_guardrails_check, get_trade_history, lookup_symbol, create_activity, portfolio_analysis, transaction_categorize, tax_estimate, compliance_check.

Your goal: answer the trader's question by calling the right tools in the right order, then provide a clear final answer.

TOOL GUIDANCE:
- portfolio_guardrails_check: Use for "What's my portfolio risk?", "Am I within my limits?", "Portfolio health check". No arguments needed.
- trade_guardrails_check: Use for "Can I buy $10k of TSLA?", "Should I sell GOOG?", "Is this trade within my limits?". Requires symbol and side (buy/sell).
- portfolio_analysis: Use for per-account analysis, allocation breakdown, or detailed performance. Omit account_id for the full portfolio.
- transaction_categorize: Use for categorizing transactions and detecting patterns (recurring dividends, DCA, fee clusters). Pass transactions or leave blank to fetch from Ghostfolio.
- tax_estimate: Use for estimating US federal income tax from income and deductions. Informational only.
- compliance_check: Use for checking regulatory/tax compliance (wash_sale, capital_gains, tax_loss_harvesting). NOT for portfolio risk limits.

RECORDING TRANSACTIONS: You have the create_activity tool. When the user asks to "record a transaction", "log a trade", "add a buy/sell", or "save a transaction", you MUST use create_activity. Do NOT say you do not have access to portfolio management tools or that you cannot record transactions — you can, using create_activity. If the user has not provided symbol, quantity, unit_price, date, and currency, reply with a single short message asking for those details (e.g. "I can record that. What symbol, how many shares, at what price, and on what date? Currency (e.g. USD)?") then when they reply, call create_activity with the details. For BUY/SELL use activity_type "BUY" or "SELL". You may call get_portfolio_snapshot first to get account_id if the user has multiple accounts.

RULES:
- Call tools as needed. You may call one or more tools per step and may take multiple steps.
- When you have gathered enough data, stop calling tools and provide your final answer as plain text.
- Do NOT make up numbers. If you need data, call a tool.
- Be efficient: don't call tools you don't need.
- If a tool returns an error, acknowledge it and work with what you have.

AVAILABLE CONTEXT (may be empty if stale/missing):
{context_block}

INTENT HINT (for your reference, not binding): {intent}
EXTRACTED PARAMS: {extracted_params}
"""

FINAL_STEP_ADDENDUM = """
You have reached the maximum number of tool-calling steps. Do NOT call any more tools.
Provide your final answer now using whatever data you have collected so far.
"""


def _build_context_block(state: AgentState) -> str:
    """Build a context summary from cached regime/portfolio."""
    parts = []
    regime = state.get("regime")
    if regime:
        parts.append(f"Cached regime: {json.dumps(regime, default=str)[:1000]}")
    portfolio = state.get("portfolio")
    if portfolio:
        summary = portfolio.get("summary", portfolio)
        parts.append(f"Cached portfolio summary: {json.dumps(summary, default=str)[:1000]}")
    return "\n".join(parts) if parts else "(none)"


def _get_last_human_message(messages: list) -> str:
    """Find the last HumanMessage content in the message list."""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.content if hasattr(msg, "content") else str(msg)
    return ""


def react_agent_node(state: AgentState) -> dict[str, Any]:
    """ReAct agent: invoke the LLM with bound tools. Returns AIMessage (with or without tool_calls)."""
    settings = get_settings()
    messages = list(state.get("messages", []))
    intent = state.get("intent", "general")
    extracted_params = state.get("extracted_params", {})
    react_step = state.get("react_step", 0)

    context_block = _build_context_block(state)

    system_text = REACT_SYSTEM_PROMPT.format(
        context_block=context_block,
        intent=intent,
        extracted_params=json.dumps(extracted_params, default=str),
    )

    if react_step >= MAX_REACT_STEPS:
        system_text += FINAL_STEP_ADDENDUM

    system_msg = SystemMessage(content=system_text)

    llm_messages = [system_msg] + messages

    try:
        llm = ChatAnthropic(
            model="claude-sonnet-4-20250514",
            api_key=settings.anthropic_api_key,
            max_tokens=2048,
            temperature=0,
        )

        if react_step < MAX_REACT_STEPS:
            tools = get_tools()
            llm_with_tools = llm.bind_tools(tools)
        else:
            llm_with_tools = llm

        response: AIMessage = llm_with_tools.invoke(llm_messages)
        logger.info(
            "ReAct step %d: tool_calls=%d, content_len=%d",
            react_step,
            len(response.tool_calls) if hasattr(response, "tool_calls") and response.tool_calls else 0,
            len(response.content) if response.content else 0,
        )

        return {"messages": [response]}

    except Exception as e:
        logger.error("ReAct agent LLM call failed: %s", e)
        error_msg = AIMessage(content=f"I encountered an error during analysis: {e}")
        return {"messages": [error_msg]}


def route_after_react(state: AgentState) -> str:
    """Route: if the last message has tool_calls and we haven't hit max steps, go to execute_tools; else synthesize."""
    messages = state.get("messages", [])
    react_step = state.get("react_step", 0)

    if not messages:
        return "synthesize"

    last_msg = messages[-1]

    has_tool_calls = (
        isinstance(last_msg, AIMessage)
        and hasattr(last_msg, "tool_calls")
        and last_msg.tool_calls
    )

    if has_tool_calls and react_step < MAX_REACT_STEPS:
        return "execute_tools"

    return "synthesize"
