"""Node: Format output — structure the final JSON response. Code only, no LLM."""

from __future__ import annotations

import re
import logging
from typing import Any

from agent.config import get_settings
from agent.schemas import AgentResponse
from agent.state import AgentState
from agent.authoritative_sources import get_sources_for_tools
from agent.observability import aggregate_token_usage, make_trace_entry

logger = logging.getLogger(__name__)

TOOL_TO_INTENT: list[tuple[frozenset[str], str]] = [
    # New unified guardrails_check
    (frozenset({"guardrails_check", "get_market_data", "get_portfolio_snapshot"}), "risk_check"),
    (frozenset({"guardrails_check", "get_market_data"}), "risk_check"),
    (frozenset({"guardrails_check"}), "risk_check"),
    (frozenset({"get_portfolio_snapshot", "guardrails_check"}), "portfolio_health"),
    # Standard mappings
    (frozenset({"get_trade_history", "get_portfolio_snapshot"}), "performance_review"),
    (frozenset({"compliance_check"}), "compliance"),
    (frozenset({"get_market_data"}), "price_quote"),
    (frozenset({"get_portfolio_snapshot"}), "portfolio_overview"),
    (frozenset({"get_trade_history"}), "performance_review"),
    (frozenset({"lookup_symbol"}), "lookup_symbol"),
    (frozenset({"create_activity"}), "create_activity"),
    (frozenset({"add_to_watchlist"}), "add_to_watchlist"),
    (frozenset({"log_trade_journal"}), "journal_analysis"),
    (frozenset({"get_journal_analysis"}), "journal_analysis"),
    (frozenset({"validate_chart"}), "chart_validation"),
    # Legacy tool names for backward compatibility
    (frozenset({"trade_guardrails_check", "get_market_data", "get_portfolio_snapshot"}), "risk_check"),
    (frozenset({"trade_guardrails_check", "get_market_data"}), "risk_check"),
    (frozenset({"trade_guardrails_check"}), "risk_check"),
    (frozenset({"get_portfolio_snapshot", "portfolio_guardrails_check"}), "portfolio_health"),
    (frozenset({"tax_estimate"}), "tax_implications"),
]


def infer_intent_from_tools(tools_called: list[str]) -> str:
    """Infer intent from which tools the agent called. Zero-cost code-only mapping."""
    if not tools_called:
        return "general"
    called = set(tools_called)
    for tool_set, intent in TOOL_TO_INTENT:
        if tool_set == called:
            return intent
    if len(called) >= 4:
        return "multi_step"
    for tool_set, intent in TOOL_TO_INTENT:
        if tool_set <= called and len(called) - len(tool_set) <= 1:
            return intent
    if len(called) >= 3:
        return "multi_step"
    return "general"

DISCLAIMER = (
    "This is portfolio analysis, not financial advice. Past performance does not guarantee "
    "future results. Always do your own research and consider your risk tolerance before investing."
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
        "get_market_data": ["rsi", "sma", "ema", "macd", "bollinger", "atr", "price", "volume", "close", "trading", "currently"],
        "detect_regime": ["regime", "trend", "volatility", "breadth", "correlation", "rotation", "vix"],
        "get_portfolio_snapshot": ["portfolio", "holding", "cash", "invested", "account", "position"],
        "scan_strategies": ["score", "signal", "breakout", "reversion", "momentum", "entry", "stop", "target"],
        "guardrails_check": ["risk", "violation", "sector", "concentration", "position size", "cash buffer", "stop loss"],
        # Legacy names
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
            tool_results.get("guardrails_check")
            or tool_results.get("trade_guardrails_check")
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
    elif intent == "portfolio_health":
        return {
            "snapshot": tool_results.get("get_portfolio_snapshot", {}),
            "guardrails": (
                tool_results.get("guardrails_check")
                or tool_results.get("portfolio_guardrails_check", {})
            ),
        }
    elif intent == "performance_review":
        history = tool_results.get("get_trade_history", {})
        return {
            "aggregates": history.get("aggregates", {}),
            "trades": history.get("trades", [])[:20],
        }
    elif intent == "tax_implications":
        return {
            "tax_estimate": tool_results.get("tax_estimate", {}),
            "compliance": tool_results.get("compliance_check", {}),
        }
    elif intent == "compliance":
        return tool_results.get("compliance_check", {})
    elif intent == "multi_step":
        return {k: v for k, v in tool_results.items()}
    return {}


def format_output_node(state: AgentState) -> dict[str, Any]:
    """Build the structured JSON response."""
    synthesis = state.get("synthesis", "")
    tool_results = state.get("tool_results", {})
    tools_called = state.get("tools_called", [])
    verification = state.get("verification_result") or {}
    token_usage = state.get("token_usage") or {}
    node_latencies = state.get("node_latencies") or {}
    error_log = state.get("error_log") or []
    trace_log = list(state.get("trace_log") or [])

    intent = infer_intent_from_tools(tools_called)

    confidence = verification.get("confidence", 50)
    issues = verification.get("issues", [])

    warnings = []
    if not verification.get("passed", True):
        warnings.append("Response had verification issues — some data points may not be fully verified.")
        warnings.extend(issues)

    regime = state.get("regime")
    if regime and isinstance(regime, dict):
        ts = regime.get("timestamp")
        if ts:
            warnings.append(f"Regime data from: {ts}")

    citations = _extract_citations(synthesis, tool_results)
    data = _build_intent_data(intent, tool_results)

    settings = get_settings()
    token_totals = aggregate_token_usage(token_usage, model=settings.agent_model)

    trace_log.append(make_trace_entry(
        "format_output",
        output_summary=f"confidence={confidence}, warnings={len(warnings)}",
    ))

    observability = {
        "token_usage": {**token_usage, "total": token_totals},
        "node_latencies": node_latencies,
        "error_log": error_log,
        "trace_log": trace_log,
    }

    auth_sources = get_sources_for_tools(tools_called)

    response = {
        "summary": synthesis,
        "confidence": confidence,
        "intent": intent,
        "data": data,
        "citations": citations,
        "warnings": warnings if warnings else [],
        "tools_used": tools_called,
        "authoritative_sources": [{"label": s["label"], "url": s["url"]} for s in auth_sources],
        "disclaimer": DISCLAIMER,
        "observability": observability,
    }

    # Validate through Pydantic schema
    try:
        validated = AgentResponse(**response)
        response = validated.model_dump()
    except Exception as exc:
        logger.error("Output validation failed: %s", exc)
        fallback_warnings = list(warnings) if warnings else []
        fallback_warnings.append(f"Output validation error: {exc}")
        fallback = AgentResponse(
            summary=synthesis or "Response could not be fully validated.",
            confidence=max(0, min(100, confidence)) if isinstance(confidence, (int, float)) else 0,
            intent=intent or "error",
            data={},
            citations=[],
            warnings=fallback_warnings,
            tools_used=tools_called,
            authoritative_sources=[],
            disclaimer=DISCLAIMER,
            observability=observability,
        )
        response = fallback.model_dump()

    return {"response": response}
