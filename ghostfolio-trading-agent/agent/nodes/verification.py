"""Verification node — fact-check, confidence score, guardrails. Code only, no LLM."""

from __future__ import annotations

import json
import re
import logging
import time
from datetime import datetime, timezone
from typing import Any

from agent.state import AgentState
from agent.nodes.formatter import infer_intent_from_tools
from agent.observability import make_trace_entry
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)


def _extract_numbers(text: str) -> list[tuple[str, float]]:
    """Extract numbers and their context from synthesis text."""
    results = []
    # Match numbers like 72.3, $187.42, 2.3%, -5.2
    patterns = [
        (r'\$([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)', 'dollar'),
        (r'([0-9]+(?:\.[0-9]+)?)\s*%', 'percent'),
        (r'(?:RSI|rsi).*?([0-9]+(?:\.[0-9]+)?)', 'indicator'),
        (r'(?:SMA|sma|EMA|ema|ATR|atr).*?([0-9]+(?:\.[0-9]+)?)', 'indicator'),
    ]

    for pattern, ptype in patterns:
        for match in re.finditer(pattern, text):
            val_str = match.group(1).replace(',', '')
            try:
                val = float(val_str)
                # Get surrounding context (20 chars each side)
                start = max(0, match.start() - 20)
                end = min(len(text), match.end() + 20)
                context = text[start:end]
                results.append((context, val))
            except ValueError:
                continue

    return results


def _find_in_tool_results(value: float, tool_results: dict, tolerance: float = 0.005) -> bool:
    """Check if a number can be found in any tool result (with tolerance).

    Searches both (1) recursively in dict/list structures and (2) in the stringified
    form of the entire tool result so numbers inside nested structures like
    {'AAPL': {'price': 682.39, ...}} are found. Uses relative tolerance (default 0.5%).
    """
    def search_dict(d: Any, depth: int = 0) -> bool:
        if depth > 10:
            return False
        if isinstance(d, (int, float)):
            if value == 0 and d == 0:
                return True
            if d != 0 and abs(d - value) / abs(d) <= tolerance:
                return True
            if value != 0 and abs(value - d) / abs(value) <= tolerance:
                return True
        elif isinstance(d, dict):
            for v in d.values():
                if search_dict(v, depth + 1):
                    return True
        elif isinstance(d, list):
            for item in d:
                if search_dict(item, depth + 1):
                    return True
        return False

    if search_dict(tool_results):
        return True

    # Stringify entire structure and look for numbers within tolerance (handles nested keys)
    try:
        s = json.dumps(tool_results, default=str)
    except (TypeError, ValueError):
        s = str(tool_results)
    # Match numbers in string: integers and decimals
    for match in re.finditer(r'-?\d+\.?\d*', s):
        try:
            num = float(match.group())
            if value == 0 and num == 0:
                return True
            if num != 0 and abs(num - value) / abs(num) <= tolerance:
                return True
            if value != 0 and abs(value - num) / abs(value) <= tolerance:
                return True
        except ValueError:
            continue
    return False


def _check_facts(
    synthesis: str,
    tool_results: dict,
    intent: str = "general",
    last_user_message: str = "",
    extracted_params: dict | None = None,
) -> list[str]:
    """Fact-check numbers in synthesis against tool results. Relaxed for intents where numbers are derived or user-provided."""
    issues = []
    # Nothing to fact-check if no tools were called (e.g. no-tool tax queries)
    if not tool_results:
        return issues
    # Skip fact-check for intents where derived arithmetic is inherent
    # signal_archaeology: cites historical highs/lows, derived indicator values from deep in time series
    if intent in (
        "create_activity", "portfolio_overview", "signal_archaeology",
        "portfolio_health", "performance_review", "tax_implications",
        "compliance", "multi_step",
    ):
        return issues

    params = extracted_params or {}
    user_text = (last_user_message or "").strip()
    numbers = _extract_numbers(synthesis)

    for context, value in numbers:
        # Skip very common numbers that might not be from tools (like "1", "2", etc.)
        if value in (0, 1, 2, 3, 4, 5, 10, 14, 20, 50, 100, 200):
            continue

        # risk_check: skip all percentages (often derived from price comparisons, position sizing)
        if intent == "risk_check" and "%" in context:
            continue

        # risk_check: skip dollar amounts near recommendation / derived-value language
        if intent == "risk_check":
            lower_ctx = context.lower()
            if any(kw in lower_ctx for kw in (
                "unrealized", "realize", "recommendation", "gain", "loss",
                "profit", "cost basis", "net p", "sell", "free cash",
            )):
                continue

        # opportunity_scan: skip derived numbers (reward per share, EMA(21), |value| < 25 in scan-like context)
        if intent == "opportunity_scan":
            if abs(value) < 25:
                continue
            if any(x in context for x in ("reward", "EMA(", "per share", "potential gain")):
                continue

        # chart_validation: skip percentages (derived from comparing price to user's levels)
        # and skip numbers that appear in the user message or in extracted price_levels
        if intent == "chart_validation":
            if "%" in context:
                continue
            if abs(value) < 20:
                continue
            if user_text and (
                str(int(value)) in user_text or str(value) in user_text
            ):
                continue
            price_levels = params.get("price_levels") or []
            if isinstance(price_levels, list):
                if any(float(x) == value for x in price_levels if isinstance(x, (int, float))):
                    continue
                if any(float(x) == value for pl in price_levels if isinstance(pl, dict) for x in (pl.get("price"), pl.get("level")) if pl and isinstance(pl.get("price"), (int, float)) or isinstance(pl.get("level"), (int, float))):
                    continue
            if any(str(value) in str(p) for p in price_levels):
                continue

        # For regime_check, price_quote: skip percentages and small-magnitude / 52-week style (existing logic)
        if intent in ("regime_check", "price_quote"):
            if "%" in context or (abs(value) < 20 and value != 0):
                continue
            if abs(value) > 50 and abs(value) < 200:
                window = synthesis[max(0, synthesis.find(context) - 30) : synthesis.find(context) + len(context) + 30]
                if "%" in window:
                    continue

        if not _find_in_tool_results(value, tool_results):
            issues.append(
                f"Number {value} (in '...{context.strip()}...') not found in tool results"
            )

    return issues


def _check_price_quote_freshness(
    intent: str,
    tool_results: dict,
    synthesis: str = "",
) -> list[str]:
    """
    Domain check: ensure stated prices are from the current trading day.
    Applies to price_quote and risk_check (buy/sell recommendations).
    Accepts data within 3 calendar days (weekends/holidays) and skips
    the issue if the synthesis already contains an 'as of' date disclaimer.
    """
    issues = []
    if intent not in ("price_quote", "risk_check"):
        return issues

    synth_lower = (synthesis or "").lower()
    if "as of" in synth_lower or "session of" in synth_lower:
        return issues

    md = tool_results.get("get_market_data")
    if not md or not isinstance(md, dict):
        return issues

    today_utc = datetime.now(timezone.utc).date()

    for symbol, data in md.items():
        if not isinstance(data, list) or not data:
            continue
        last_record = data[-1]
        if not isinstance(last_record, dict):
            continue
        date_str = last_record.get("date")
        if not date_str:
            continue
        try:
            data_date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
            days_old = (today_utc - data_date).days
            if days_old > 3:
                issues.append(
                    f"Price data for {symbol} is from {date_str}, not current trading day — "
                    "may be delayed or previous close; consider stating 'as of [date]'."
                )
        except (ValueError, TypeError):
            continue

    return issues


def _portfolio_is_empty(tool_results: dict) -> bool:
    """Check if a portfolio snapshot returned zero holdings."""
    snapshot = tool_results.get("get_portfolio_snapshot")
    if not snapshot or not isinstance(snapshot, dict):
        return False
    holdings = snapshot.get("holdings")
    if isinstance(holdings, list) and len(holdings) == 0:
        return True
    summary = snapshot.get("summary")
    if isinstance(summary, dict) and summary.get("holding_count", -1) == 0:
        return True
    return False


def _market_data_has_prices(tool_results: dict) -> bool:
    """Check if market data returned at least one concrete price."""
    md = tool_results.get("get_market_data")
    if not md or not isinstance(md, dict):
        return False
    for symbol, data in md.items():
        if isinstance(data, list) and data:
            last = data[-1]
            if isinstance(last, dict) and last.get("close") is not None:
                return True
    return False


def _compute_confidence(state: AgentState) -> int:
    """Compute confidence score 0-100 based on multiple factors.

    Rewards concrete, data-backed answers and penalises vacuous responses
    where tools succeeded but returned empty/unusable data.
    """
    score = 50  # Base

    tool_results = state.get("tool_results", {})
    intent = state.get("intent", "general")
    regime = state.get("regime")

    # Successful tools boost confidence; errors reduce it
    successful_tools = 0
    for tool_name, result in tool_results.items():
        if isinstance(result, dict) and "error" in result:
            score -= 5
        else:
            score += 10
            successful_tools += 1

    # Data-retrieval intents with successful tools deserve higher confidence —
    # we're reading real data, not making predictions
    data_intents = (
        "portfolio_overview", "performance_review", "price_quote",
        "tax_implications", "compliance", "lookup_symbol", "create_activity",
    )
    if intent in data_intents and successful_tools > 0:
        score += 15

    # --- Data-quality adjustments ---

    # Empty portfolio: the tools "succeeded" but there's nothing to analyse.
    # Penalise portfolio-dependent intents that got no holdings.
    portfolio_intents = (
        "portfolio_overview", "performance_review", "risk_check",
        "portfolio_health", "tax_implications", "compliance",
    )
    if _portfolio_is_empty(tool_results):
        if intent in portfolio_intents:
            score -= 20  # can't meaningfully answer
        else:
            score -= 10  # less relevant but still thin data

    # Market data: reward concrete prices for price-dependent intents
    price_intents = (
        "price_quote", "risk_check", "opportunity_scan",
        "chart_validation", "signal_archaeology",
    )
    if intent in price_intents:
        if _market_data_has_prices(tool_results):
            score += 10  # concrete answer backed by real prices
        elif "get_market_data" in tool_results:
            score -= 10  # tool ran but returned no usable prices

    # --- End data-quality adjustments ---

    if regime and "composite" in regime:
        confidence = regime.get("confidence", 0)
        score += confidence // 10  # +0 to +10

    scan_result = tool_results.get("scan_strategies")
    if scan_result and isinstance(scan_result, dict):
        matches = scan_result.get("matches", 0)
        if matches > 0:
            score += min(10, matches * 3)

    for guardrail_key in ("guardrails_check", "portfolio_guardrails_check", "trade_guardrails_check"):
        guardrail_result = tool_results.get(guardrail_key)
        if guardrail_result and isinstance(guardrail_result, dict):
            if guardrail_result.get("passed"):
                score += 10
            else:
                score -= 5

    # Legacy support: check_risk (until fully removed)
    risk_result = tool_results.get("check_risk")
    if risk_result and isinstance(risk_result, dict):
        if risk_result.get("passed"):
            score += 10
        else:
            score -= 5

    compliance_result = tool_results.get("compliance_check")
    if compliance_result and isinstance(compliance_result, dict):
        if compliance_result.get("passed"):
            score += 5
        elif compliance_result.get("violations"):
            score -= 5

    return max(0, min(100, score))


def _check_guardrails(synthesis: str, intent: str, tool_results: dict) -> list[str]:
    """Check risk guardrails in the synthesis."""
    issues = []

    synth_lower = synthesis.lower()
    trade_keywords = ["buy", "enter", "long", "short"]
    has_trade_suggestion = any(kw in synth_lower for kw in trade_keywords)

    trade_result = tool_results.get("guardrails_check", {})
    if not trade_result:
        trade_result = tool_results.get("trade_guardrails_check", {})
    if not trade_result:
        trade_result = tool_results.get("check_risk", {})
    if not isinstance(trade_result, dict):
        trade_result = {}
    is_sell_evaluation = trade_result.get("sell_evaluation") or trade_result.get("action") == "sell"

    if has_trade_suggestion and not is_sell_evaluation and intent in ("opportunity_scan", "risk_check", "chart_validation"):
        strong_trade = any(
            phrase in synth_lower
            for phrase in (
                "you should buy", "you should sell", "consider buying", "consider selling",
                "recommend buying", "recommend selling", "add to position",
                "i recommend", "i suggest", "we recommend",
            )
        )

        # Only require stop/target for strong trade recommendations
        if intent in ("chart_validation", "risk_check") and not strong_trade:
            pass
        elif intent == "opportunity_scan":
            if "stop" not in synth_lower and "stop loss" not in synth_lower:
                issues.append("Trade suggestion missing stop loss level")
            has_target = (
                "target" in synth_lower
                or "take profit" in synth_lower
                or "risk/reward" in synth_lower
                or "r:r" in synth_lower
                or "risk-reward" in synth_lower
            )
            if not has_target:
                issues.append("Trade suggestion missing target/take profit level")
        else:
            if "stop" not in synth_lower and "stop loss" not in synth_lower:
                issues.append("Trade suggestion missing stop loss level")
            if "target" not in synth_lower and "take profit" not in synth_lower:
                issues.append("Trade suggestion missing target/take profit level")

    guarantee_words = ["guaranteed", "will definitely", "100% certain", "can't lose", "sure thing"]
    for word in guarantee_words:
        if word in synth_lower:
            issues.append(f"Contains guarantee language: '{word}'")

    return issues


def _check_tax_estimate_sanity(synthesis: str, tool_results: dict) -> list[str]:
    """Domain check: tax_estimate results must be non-negative and plausible."""
    issues = []
    tax_result = tool_results.get("tax_estimate")
    if not tax_result or not isinstance(tax_result, dict):
        return issues

    liability = tax_result.get("estimated_liability")
    if liability is not None and liability < 0:
        issues.append(
            f"tax_estimate returned negative liability ({liability}); result is suspect"
        )

    effective_rate = tax_result.get("effective_rate")
    if effective_rate is not None and (effective_rate < 0 or effective_rate > 100):
        issues.append(
            f"tax_estimate effective_rate ({effective_rate}) outside 0–100 range"
        )

    return issues


def _check_compliance_consistency(synthesis: str, tool_results: dict) -> list[str]:
    """Domain check: synthesis must not contradict compliance_check results."""
    issues = []
    comp_result = tool_results.get("compliance_check")
    if not comp_result or not isinstance(comp_result, dict):
        return issues

    synth_lower = synthesis.lower()
    tool_passed = comp_result.get("passed", True)
    tool_violations = comp_result.get("violations", [])

    says_no_violations = (
        "no violations" in synth_lower
        or "no compliance issues" in synth_lower
        or "fully compliant" in synth_lower
    )

    if says_no_violations and (not tool_passed or len(tool_violations) > 0):
        issues.append(
            "Synthesis says no violations but compliance_check reported violations"
        )

    return issues


def _check_authoritative_consistency(synthesis: str, tool_results: dict) -> list[str]:
    """Check synthesis against authoritative tax/compliance rules."""
    issues = []
    synth_lower = synthesis.lower()

    # Wash sale window: if synthesis mentions wash sale but implies a window != 30 days
    if "compliance_check" in tool_results and "wash sale" in synth_lower:
        wrong_windows = re.findall(r'(\d+)\s*(?:-?\s*)?days?\b.*?(?:wash|before|after)', synth_lower)
        wrong_windows += re.findall(r'(?:wash|before|after).*?(\d+)\s*(?:-?\s*)?days?\b', synth_lower)
        for window in wrong_windows:
            try:
                days = int(window)
                if days not in (30, 60, 61, 90):
                    # 30 is correct window each side; 60/61 is the total window — both acceptable
                    issues.append(
                        f"Synthesis mentions wash sale with {days}-day window; "
                        "authoritative rule is 30 days before or after (IRC \u00a71091)"
                    )
            except ValueError:
                continue

    # Long-term capital gains: must be held more than 1 year
    has_tax_or_compliance = "tax_estimate" in tool_results or "compliance_check" in tool_results
    if has_tax_or_compliance and "long-term" in synth_lower:
        wrong_periods = re.findall(
            r'(?:long.?term).*?(?:held|hold|holding)\s+.*?(\d+)\s*(?:month|day|year)',
            synth_lower,
        )
        wrong_periods += re.findall(
            r'(?:held|hold|holding)\s+.*?(\d+)\s*(?:month|day|year).*?(?:long.?term)',
            synth_lower,
        )
        for period_match in wrong_periods:
            try:
                val = int(period_match)
                # Check context for unit
                period_ctx_match = re.search(
                    rf'{val}\s*(month|day|year)', synth_lower
                )
                if period_ctx_match:
                    unit = period_ctx_match.group(1)
                    if unit.startswith("year") and val < 1:
                        issues.append(
                            f"Synthesis implies long-term holding period of {val} year(s); "
                            "must be more than 1 year (IRC \u00a71222)"
                        )
                    elif unit.startswith("month") and val < 12:
                        issues.append(
                            f"Synthesis implies long-term holding period of {val} months; "
                            "must be more than 12 months (IRC \u00a71222)"
                        )
                    elif unit.startswith("day") and val < 365:
                        issues.append(
                            f"Synthesis implies long-term holding period of {val} days; "
                            "must be more than 365 days (IRC \u00a71222)"
                        )
            except ValueError:
                continue

    return issues


def verify_node(state: AgentState) -> dict[str, Any]:
    """Verify the synthesis: fact-check, confidence, guardrails, domain checks."""
    synthesis = state.get("synthesis", "")
    tool_results = state.get("tool_results", {})
    tools_called = state.get("tools_called", [])
    intent = infer_intent_from_tools(tools_called)
    attempts = state.get("verification_attempts", 0)
    node_latencies = dict(state.get("node_latencies") or {})
    trace_log = list(state.get("trace_log") or [])

    _start = time.perf_counter()
    all_issues = []

    last_user_message = ""
    for msg in reversed(state.get("messages") or []):
        if isinstance(msg, HumanMessage):
            last_user_message = getattr(msg, "content", "") or str(msg)
            break
    extracted_params = state.get("extracted_params") or {}

    fact_issues = _check_facts(
        synthesis, tool_results, intent,
        last_user_message=last_user_message,
        extracted_params=extracted_params,
    )
    all_issues.extend(fact_issues)

    price_quote_issues = _check_price_quote_freshness(intent, tool_results, synthesis)
    all_issues.extend(price_quote_issues)

    confidence = _compute_confidence(state)

    guardrail_issues = _check_guardrails(synthesis, intent, tool_results)
    all_issues.extend(guardrail_issues)

    tax_issues = _check_tax_estimate_sanity(synthesis, tool_results)
    all_issues.extend(tax_issues)

    compliance_issues = _check_compliance_consistency(synthesis, tool_results)
    all_issues.extend(compliance_issues)

    authoritative_issues = _check_authoritative_consistency(synthesis, tool_results)
    all_issues.extend(authoritative_issues)

    passed = len(all_issues) == 0

    verification_result = {
        "passed": passed,
        "issues": all_issues,
        "confidence": confidence,
        "fact_check_issues": len(fact_issues),
        "guardrail_issues": len(guardrail_issues),
    }

    verify_key = f"verify_{attempts}"
    node_latencies[verify_key] = round(time.perf_counter() - _start, 4)
    trace_log.append(make_trace_entry(
        verify_key,
        input_summary=f"synthesis ({len(synthesis)} chars)",
        output_summary=f"passed={passed}, issues={len(all_issues)}, confidence={confidence}",
    ))

    return {
        "verification_result": verification_result,
        "verification_attempts": attempts + 1,
        "node_latencies": node_latencies,
        "trace_log": trace_log,
    }
