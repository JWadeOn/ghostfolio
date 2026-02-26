"""Node: Tool execution for ReAct loop — reads tool_calls from the last AIMessage."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from agent.ghostfolio_client import GhostfolioClient
from agent.state import AgentState
from agent.tools.market_data import get_market_data
from agent.tools.portfolio import get_portfolio_snapshot
from agent.tools.regime import detect_regime
from agent.tools.scanner import scan_strategies
from agent.tools.risk import portfolio_guardrails_check, trade_guardrails_check, check_risk
from agent.tools.history import get_trade_history
from agent.tools.symbols import lookup_symbol
from agent.tools.activities import create_activity
from agent.tools.portfolio_analysis import portfolio_analysis

logger = logging.getLogger(__name__)

TOOL_REGISTRY = {
    "get_market_data": get_market_data,
    "get_portfolio_snapshot": get_portfolio_snapshot,
    "detect_regime": detect_regime,
    "scan_strategies": scan_strategies,
    "portfolio_guardrails_check": portfolio_guardrails_check,
    "trade_guardrails_check": trade_guardrails_check,
    "get_trade_history": get_trade_history,
    "lookup_symbol": lookup_symbol,
    "create_activity": create_activity,
    "check_risk": check_risk,  # legacy — remove when all callers migrate
    "portfolio_analysis": portfolio_analysis,
}

GHOSTFOLIO_TOOLS = frozenset({
    "get_portfolio_snapshot",
    "get_trade_history",
    "portfolio_guardrails_check",
    "trade_guardrails_check",
    "check_risk",
    "lookup_symbol",
    "create_activity",
    "portfolio_analysis",
})


def execute_tools_node(state: AgentState) -> dict[str, Any]:
    """Execute tool_calls from the last AIMessage and return ToolMessages + updated state."""
    messages = state.get("messages", [])
    tool_results = dict(state.get("tool_results", {}))
    tools_called = list(state.get("tools_called", []))
    react_step = state.get("react_step", 0)

    regime = state.get("regime")
    regime_timestamp = state.get("regime_timestamp")
    portfolio = state.get("portfolio")
    portfolio_timestamp = state.get("portfolio_timestamp")
    ghostfolio_token = state.get("ghostfolio_access_token")

    if not messages:
        return {"react_step": react_step + 1}

    last_msg = messages[-1]
    if not isinstance(last_msg, AIMessage) or not getattr(last_msg, "tool_calls", None):
        return {"react_step": react_step + 1}

    # One client per request token for Ghostfolio tools (avoids re-exchanging token per tool)
    ghostfolio_client = None
    if ghostfolio_token and GHOSTFOLIO_TOOLS:
        try:
            ghostfolio_client = GhostfolioClient(access_token=ghostfolio_token)
        except Exception as e:
            logger.warning("Failed to create Ghostfolio client from request token: %s", e)

    new_messages = []

    try:
        for tc in last_msg.tool_calls:
            tool_name = tc["name"]
            tool_args = dict(tc.get("args", {}))
            tool_call_id = tc["id"]

            tool_fn = TOOL_REGISTRY.get(tool_name)
            if not tool_fn:
                logger.error("Unknown tool: %s", tool_name)
                result = {"error": f"Unknown tool: {tool_name}"}
                tool_results[tool_name] = result
                new_messages.append(
                    ToolMessage(content=json.dumps(result, default=str), tool_call_id=tool_call_id)
                )
                continue

            # Inject regime from state into scan_strategies when the LLM didn't provide it
            if tool_name == "scan_strategies" and "regime" not in tool_args and regime:
                tool_args["regime"] = regime

            # Use request-scoped Ghostfolio client for tools that need it
            if tool_name in GHOSTFOLIO_TOOLS and ghostfolio_client is not None:
                tool_args["client"] = ghostfolio_client

            try:
                logger.info("Executing tool: %s with args: %s", tool_name, tool_args)
                result = tool_fn(**tool_args)

                # Accumulate tool results (keyed by tool name; latest call wins if called twice)
                tool_results[tool_name] = result
                tools_called.append(tool_name)

                now = datetime.now(timezone.utc).isoformat()
                if tool_name == "detect_regime":
                    regime = result
                    regime_timestamp = now
                elif tool_name == "get_portfolio_snapshot":
                    portfolio = result
                    portfolio_timestamp = now

                result_str = json.dumps(result, default=str)
                if len(result_str) > 8000:
                    result_str = result_str[:8000] + "... (truncated)"

                new_messages.append(
                    ToolMessage(content=result_str, tool_call_id=tool_call_id)
                )

            except Exception as e:
                logger.error("Tool %s failed: %s", tool_name, e)
                error_result = {"error": str(e)}
                tool_results[tool_name] = error_result
                tools_called.append(tool_name)
                new_messages.append(
                    ToolMessage(content=json.dumps(error_result), tool_call_id=tool_call_id)
                )

    finally:
        if ghostfolio_client is not None:
            try:
                ghostfolio_client.close()
            except Exception:
                pass

    return {
        "messages": new_messages,
        "tool_results": tool_results,
        "tools_called": tools_called,
        "react_step": react_step + 1,
        "regime": regime,
        "regime_timestamp": regime_timestamp,
        "portfolio": portfolio,
        "portfolio_timestamp": portfolio_timestamp,
    }
