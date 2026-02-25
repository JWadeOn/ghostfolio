"""Node 2: Context freshness check — deterministic code, no LLM."""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from agent.state import AgentState

logger = logging.getLogger(__name__)

# Cache freshness thresholds
REGIME_TTL = timedelta(minutes=30)
PORTFOLIO_TTL = timedelta(minutes=5)

# Intent → required tools mapping
INTENT_TOOLS = {
    "price_quote": [
        {"tool": "get_market_data", "always_fresh": True},
    ],
    "regime_check": [
        {"tool": "detect_regime", "always_fresh": True},
    ],
    "opportunity_scan": [
        {"tool": "detect_regime", "always_fresh": False},
        {"tool": "get_portfolio_snapshot", "always_fresh": False},
        {"tool": "scan_strategies", "always_fresh": True},
    ],
    "chart_validation": [
        {"tool": "get_market_data", "always_fresh": True},
    ],
    "journal_analysis": [
        {"tool": "get_trade_history", "always_fresh": True},
    ],
    "risk_check": [
        {"tool": "get_portfolio_snapshot", "always_fresh": False},
        {"tool": "get_market_data", "always_fresh": True},
        {"tool": "check_risk", "always_fresh": True},
    ],
    "signal_archaeology": [
        {"tool": "get_market_data", "always_fresh": True},
    ],
    "portfolio_overview": [
        {"tool": "get_portfolio_snapshot", "always_fresh": False},
    ],
    "general": [],
}


def _is_fresh(timestamp_str: str | None, ttl: timedelta) -> bool:
    """Check if a cached value is still fresh."""
    if not timestamp_str:
        return False
    try:
        ts = datetime.fromisoformat(timestamp_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - ts < ttl
    except (ValueError, TypeError):
        return False


def check_context_node(state: AgentState) -> dict[str, Any]:
    """Determine which tools need to run based on intent and cached context."""
    intent = state.get("intent", "general")
    params = state.get("extracted_params", {})
    required = INTENT_TOOLS.get(intent, [])

    tools_needed = []

    for tool_spec in required:
        tool_name = tool_spec["tool"]
        always_fresh = tool_spec["always_fresh"]

        # Check if we already have fresh cached data
        if tool_name == "detect_regime" and not always_fresh:
            if _is_fresh(state.get("regime_timestamp"), REGIME_TTL) and state.get("regime"):
                logger.info("Regime data is fresh, skipping fetch")
                continue

        if tool_name == "get_portfolio_snapshot" and not always_fresh:
            if _is_fresh(state.get("portfolio_timestamp"), PORTFOLIO_TTL) and state.get("portfolio"):
                logger.info("Portfolio data is fresh, skipping fetch")
                continue

        # Build tool params from extracted_params
        tool_params = {}
        symbols = params.get("symbols", [])
        timeframe = params.get("timeframe")

        if tool_name == "get_market_data":
            if not symbols:
                if intent != "risk_check":
                    continue  # get_market_data requires symbols; skip if none extracted
                tool_params["from_portfolio"] = True  # execute_tools will fill symbols from portfolio
            else:
                tool_params["symbols"] = symbols
            if timeframe:
                tool_params["period"] = timeframe
        elif tool_name == "get_trade_history":
            tool_params["time_range"] = timeframe or "90d"
            if symbols:
                tool_params["symbol"] = symbols[0]
        elif tool_name == "check_risk":
            if symbols:
                tool_params["symbol"] = symbols[0]
                tool_params["direction"] = params.get("direction", "LONG")
                if params.get("dollar_amount"):
                    tool_params["dollar_amount"] = params["dollar_amount"]
            # when no symbols, leave params empty → check_risk runs portfolio-level assessment
        elif tool_name == "scan_strategies":
            if symbols:
                tool_params["symbols"] = symbols
            if params.get("strategy"):
                tool_params["strategy_names"] = [params["strategy"]]

        tools_needed.append({"tool": tool_name, "params": tool_params})

    return {"tools_needed": tools_needed}


def route_after_context(state: AgentState) -> str:
    """Route: if tools are needed go to execute_tools, otherwise synthesize."""
    tools_needed = state.get("tools_needed", [])
    if tools_needed:
        return "needs_tools"
    return "has_context"
