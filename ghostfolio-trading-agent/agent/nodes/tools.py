"""Node 3: Tool execution router — deterministic code, no LLM."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from agent.state import AgentState
from agent.tools.market_data import get_market_data
from agent.tools.portfolio import get_portfolio_snapshot
from agent.tools.regime import detect_regime
from agent.tools.scanner import scan_strategies
from agent.tools.risk import check_risk
from agent.tools.history import get_trade_history
from agent.tools.symbols import lookup_symbol

logger = logging.getLogger(__name__)

# Tool function registry
TOOL_REGISTRY = {
    "get_market_data": get_market_data,
    "get_portfolio_snapshot": get_portfolio_snapshot,
    "detect_regime": detect_regime,
    "scan_strategies": scan_strategies,
    "check_risk": check_risk,
    "get_trade_history": get_trade_history,
    "lookup_symbol": lookup_symbol,
}


def execute_tools_node(state: AgentState) -> dict[str, Any]:
    """Execute the tools specified by the context node."""
    tools_needed = state.get("tools_needed", [])
    tool_results = dict(state.get("tool_results", {}))
    tools_called = list(state.get("tools_called", []))

    # Track regime and portfolio updates
    regime = state.get("regime")
    regime_timestamp = state.get("regime_timestamp")
    portfolio = state.get("portfolio")
    portfolio_timestamp = state.get("portfolio_timestamp")

    for tool_spec in tools_needed:
        tool_name = tool_spec["tool"]
        params = tool_spec.get("params", {})

        tool_fn = TOOL_REGISTRY.get(tool_name)
        if not tool_fn:
            logger.error(f"Unknown tool: {tool_name}")
            tool_results[tool_name] = {"error": f"Unknown tool: {tool_name}"}
            continue

        try:
            logger.info(f"Executing tool: {tool_name} with params: {params}")
            result = tool_fn(**params)
            tool_results[tool_name] = result
            tools_called.append(tool_name)

            # Cache regime and portfolio results
            now = datetime.now(timezone.utc).isoformat()
            if tool_name == "detect_regime":
                regime = result
                regime_timestamp = now
            elif tool_name == "get_portfolio_snapshot":
                portfolio = result
                portfolio_timestamp = now

            # Pass regime to scanner if available
            if tool_name == "detect_regime" and "scan_strategies" in [t["tool"] for t in tools_needed]:
                # Update scan params with regime
                for t in tools_needed:
                    if t["tool"] == "scan_strategies":
                        t["params"]["regime"] = result

        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            tool_results[tool_name] = {"error": str(e)}
            tools_called.append(tool_name)

    return {
        "tool_results": tool_results,
        "tools_called": tools_called,
        "regime": regime,
        "regime_timestamp": regime_timestamp,
        "portfolio": portfolio,
        "portfolio_timestamp": portfolio_timestamp,
    }
