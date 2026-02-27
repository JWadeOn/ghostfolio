"""Node: Tool execution for ReAct loop — reads tool_calls from the last AIMessage."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from agent.ghostfolio_client import GhostfolioClient
from agent.state import AgentState
from agent.observability import (
    track_latency, make_error_entry, make_trace_entry, ErrorCategory,
)
from agent.tools.market_data import get_market_data
from agent.tools.portfolio import get_portfolio_snapshot
from agent.tools.regime import detect_regime
from agent.tools.scanner import scan_strategies
from agent.tools.risk import portfolio_guardrails_check, trade_guardrails_check, check_risk
from agent.tools.history import get_trade_history
from agent.tools.symbols import lookup_symbol
from agent.tools.activities import create_activity
from agent.tools.portfolio_analysis import portfolio_analysis
from agent.tools.transaction_categorize import transaction_categorize
from agent.tools.tax_estimate import tax_estimate
from agent.tools.compliance_check import compliance_check

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
    "transaction_categorize": transaction_categorize,
    "tax_estimate": tax_estimate,
    "compliance_check": compliance_check,
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
    "transaction_categorize",
    "compliance_check",
})


def execute_tools_node(state: AgentState) -> dict[str, Any]:
    """Execute tool_calls from the last AIMessage and return ToolMessages + updated state."""
    messages = state.get("messages", [])
    tool_results = dict(state.get("tool_results", {}))
    tools_called = list(state.get("tools_called", []))
    react_step = state.get("react_step", 0)
    node_latencies = dict(state.get("node_latencies") or {})
    error_log = list(state.get("error_log") or [])
    trace_log = list(state.get("trace_log") or [])

    regime = state.get("regime")
    regime_timestamp = state.get("regime_timestamp")
    portfolio = state.get("portfolio")
    portfolio_timestamp = state.get("portfolio_timestamp")
    ghostfolio_token = state.get("ghostfolio_access_token")

    step_key = f"execute_tools_{react_step}"

    if not messages:
        return {"react_step": react_step + 1}

    last_msg = messages[-1]
    if not isinstance(last_msg, AIMessage) or not getattr(last_msg, "tool_calls", None):
        return {"react_step": react_step + 1}

    ghostfolio_client = None
    if ghostfolio_token and GHOSTFOLIO_TOOLS:
        try:
            ghostfolio_client = GhostfolioClient(access_token=ghostfolio_token)
        except Exception as e:
            logger.warning("Failed to create Ghostfolio client from request token: %s", e)

    new_messages = []
    tool_timings: dict[str, float] = {}

    with track_latency() as step_timing:
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
                    error_log.append(make_error_entry(
                        step_key, ValueError(f"Unknown tool: {tool_name}"),
                        ErrorCategory.TOOL, context={"tool": tool_name},
                    ))
                    new_messages.append(
                        ToolMessage(content=json.dumps(result, default=str), tool_call_id=tool_call_id)
                    )
                    continue

                if tool_name == "scan_strategies" and "regime" not in tool_args and regime:
                    tool_args["regime"] = regime

                if tool_name in GHOSTFOLIO_TOOLS and ghostfolio_client is not None:
                    tool_args["client"] = ghostfolio_client

                try:
                    logger.info("Executing tool: %s with args: %s", tool_name, tool_args)
                    t0 = time.perf_counter()
                    result = tool_fn(**tool_args)
                    tool_timings[tool_name] = round(time.perf_counter() - t0, 4)

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
                    error_log.append(make_error_entry(
                        step_key, e, ErrorCategory.TOOL, context={"tool": tool_name},
                    ))
                    new_messages.append(
                        ToolMessage(content=json.dumps(error_result), tool_call_id=tool_call_id)
                    )

        finally:
            if ghostfolio_client is not None:
                try:
                    ghostfolio_client.close()
                except Exception:
                    pass

    node_latencies[step_key] = step_timing.get("elapsed_seconds", 0)
    for tn, dur in tool_timings.items():
        node_latencies[f"tool_{tn}_{react_step}"] = dur

    trace_log.append(make_trace_entry(
        step_key,
        input_summary=f"tool_calls={[tc['name'] for tc in last_msg.tool_calls]}",
        output_summary=f"executed={list(tool_timings.keys())}",
        metadata={"tool_timings": tool_timings},
    ))

    return {
        "messages": new_messages,
        "tool_results": tool_results,
        "tools_called": tools_called,
        "react_step": react_step + 1,
        "regime": regime,
        "regime_timestamp": regime_timestamp,
        "portfolio": portfolio,
        "portfolio_timestamp": portfolio_timestamp,
        "node_latencies": node_latencies,
        "error_log": error_log,
        "trace_log": trace_log,
    }
