"""Node 6: Format output — structure the final JSON response. Code only, no LLM."""

from __future__ import annotations

import re
import logging
from typing import Any

from agent.state import AgentState

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "This is market analysis, not financial advice. Past performance does not guarantee "
    "future results. Always do your own research and consider your risk tolerance before trading."
)


def _extract_citations(synthesis: str, tool_results: dict) -> list[dict]:
    """Extract verifiable claims from synthesis and match to tool sources."""
    citations = []

    # Extract dollar amounts and match to tools
    dollar_pattern = r'\$([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)'
    pct_pattern = r'([0-9]+(?:\.[0-9]+)?)\s*%'

    for match in re.finditer(dollar_pattern, synthesis):
        claim_start = max(0, match.start() - 30)
        claim_end = min(len(synthesis), match.end() + 10)
        claim = synthesis[claim_start:claim_end].strip()

        # Determine source tool
        source = _guess_source_tool(claim, tool_results)
        citations.append({
            "claim": claim,
            "source": source,
            "verified": source is not None,
        })

    for match in re.finditer(pct_pattern, synthesis):
        claim_start = max(0, match.start() - 30)
        claim_end = min(len(synthesis), match.end() + 10)
        claim = synthesis[claim_start:claim_end].strip()

        source = _guess_source_tool(claim, tool_results)
        citations.append({
            "claim": claim,
            "source": source,
            "verified": source is not None,
        })

    return citations[:20]  # Limit citations


def _guess_source_tool(claim: str, tool_results: dict) -> str | None:
    """Guess which tool a claim came from based on keywords."""
    claim_lower = claim.lower()

    keyword_map = {
        "get_market_data": ["rsi", "sma", "ema", "macd", "bollinger", "atr", "price", "volume", "close"],
        "detect_regime": ["regime", "trend", "volatility", "breadth", "correlation", "rotation", "vix"],
        "get_portfolio_snapshot": ["portfolio", "holding", "cash", "invested", "account", "position"],
        "scan_strategies": ["score", "signal", "breakout", "reversion", "momentum", "entry", "stop", "target"],
        "portfolio_guardrails_check": ["risk", "violation", "sector", "concentration", "position size", "cash buffer"],
        "trade_guardrails_check": ["risk", "violation", "sector", "concentration", "position size", "stop loss"],
        "get_trade_history": ["win rate", "profit factor", "p&l", "trade", "loss"],
    }

    for tool, keywords in keyword_map.items():
        if tool in tool_results:
            for kw in keywords:
                if kw in claim_lower:
                    return tool

    return None


def _build_intent_data(intent: str, tool_results: dict) -> dict:
    """Build intent-specific structured data from tool results."""
    if intent == "regime_check":
        return tool_results.get("detect_regime", {})
    elif intent == "opportunity_scan":
        scan = tool_results.get("scan_strategies", {})
        return {
            "opportunities": scan.get("opportunities", [])[:10],
            "scanned": scan.get("scanned", 0),
            "matches": scan.get("matches", 0),
        }
    elif intent == "risk_check":
        return (
            tool_results.get("trade_guardrails_check")
            or tool_results.get("portfolio_guardrails_check")
            or tool_results.get("check_risk", {})
        )
    elif intent == "journal_analysis":
        history = tool_results.get("get_trade_history", {})
        return {
            "aggregates": history.get("aggregates", {}),
            "recent_trades": history.get("trades", [])[:10],
        }
    elif intent in ("chart_validation", "price_quote"):
        md = tool_results.get("get_market_data", {})
        # Return latest data points for each symbol
        result = {}
        for sym, data in md.items():
            if isinstance(data, list) and data:
                result[sym] = data[-1]  # latest record
        return result
    elif intent == "portfolio_overview":
        return tool_results.get("get_portfolio_snapshot", {})
    return {}


def format_output_node(state: AgentState) -> dict[str, Any]:
    """Build the structured JSON response."""
    synthesis = state.get("synthesis", "")
    intent = state.get("intent", "general")
    verification = state.get("verification_result", {})
    tool_results = state.get("tool_results", {})
    tools_called = state.get("tools_called", [])

    confidence = verification.get("confidence", 50)
    issues = verification.get("issues", [])

    # Build warnings
    warnings = []
    if not verification.get("passed", True):
        warnings.append("Response had verification issues — some data points may not be fully verified.")
        warnings.extend(issues)

    # Check data freshness
    regime = state.get("regime")
    if regime and isinstance(regime, dict):
        ts = regime.get("timestamp")
        if ts:
            warnings.append(f"Regime data from: {ts}")

    # Build citations
    citations = _extract_citations(synthesis, tool_results)

    # Build intent-specific data
    data = _build_intent_data(intent, tool_results)

    response = {
        "summary": synthesis,
        "confidence": confidence,
        "intent": intent,
        "data": data,
        "citations": citations,
        "warnings": warnings if warnings else [],
        "tools_used": tools_called,
        "disclaimer": DISCLAIMER,
    }

    return {"response": response}
