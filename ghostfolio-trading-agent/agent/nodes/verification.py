"""Node 5: Verification — fact-check, confidence score, guardrails. Code only, no LLM."""

from __future__ import annotations

import re
import logging
from datetime import datetime, timezone
from typing import Any

from agent.state import AgentState

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


def _find_in_tool_results(value: float, tool_results: dict, tolerance: float = 0.05) -> bool:
    """Check if a number can be found in any tool result (with tolerance)."""
    def search_dict(d: Any, depth: int = 0) -> bool:
        if depth > 5:
            return False
        if isinstance(d, (int, float)):
            if d == 0 and value == 0:
                return True
            if d != 0 and abs(d - value) / abs(d) < tolerance:
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

    return search_dict(tool_results)


def _check_facts(synthesis: str, tool_results: dict) -> list[str]:
    """Fact-check numbers in synthesis against tool results."""
    issues = []
    numbers = _extract_numbers(synthesis)

    for context, value in numbers:
        # Skip very common numbers that might not be from tools (like "1", "2", etc.)
        if value in (0, 1, 2, 3, 4, 5, 10, 14, 20, 50, 100, 200):
            continue

        if not _find_in_tool_results(value, tool_results):
            issues.append(
                f"Number {value} (in '...{context.strip()}...') not found in tool results"
            )

    return issues


def _check_price_quote_freshness(intent: str, tool_results: dict) -> list[str]:
    """
    Domain check: ensure stated prices are from the current trading day.
    Applies to price_quote and risk_check (buy/sell recommendations).
    """
    issues = []
    if intent not in ("price_quote", "risk_check"):
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
            # date is "YYYY-MM-DD"
            data_date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
            if data_date < today_utc:
                issues.append(
                    f"Price data for {symbol} is from {date_str}, not current trading day — "
                    "may be delayed or previous close; consider stating 'as of [date]'."
                )
        except (ValueError, TypeError):
            continue

    return issues


def _compute_confidence(state: AgentState) -> int:
    """Compute confidence score 0-100 based on multiple factors."""
    score = 50  # Base

    tool_results = state.get("tool_results", {})
    intent = state.get("intent", "general")
    regime = state.get("regime")

    # +10 for each tool that returned successfully
    for tool_name, result in tool_results.items():
        if isinstance(result, dict) and "error" in result:
            score -= 5
        else:
            score += 10

    # Regime alignment bonus
    if regime and "composite" in regime:
        confidence = regime.get("confidence", 0)
        score += confidence // 10  # +0 to +10

    # Scanner results bonus
    scan_result = tool_results.get("scan_strategies")
    if scan_result and isinstance(scan_result, dict):
        matches = scan_result.get("matches", 0)
        if matches > 0:
            score += min(10, matches * 3)

    # Risk check result
    risk_result = tool_results.get("check_risk")
    if risk_result and isinstance(risk_result, dict):
        if risk_result.get("passed"):
            score += 10
        else:
            score -= 5

    return max(0, min(100, score))


def _check_guardrails(synthesis: str, intent: str, tool_results: dict) -> list[str]:
    """Check risk guardrails in the synthesis."""
    issues = []

    # If response suggests a trade (buy/enter), must include stop loss and target
    trade_keywords = ["buy", "enter", "long", "short", "position"]
    has_trade_suggestion = any(kw in synthesis.lower() for kw in trade_keywords)
    # For sell evaluations, we recommend selling — not entering a trade — so skip stop/target requirement
    risk_result = tool_results.get("check_risk", {})
    is_sell_evaluation = risk_result.get("sell_evaluation") or risk_result.get("action") == "sell"

    if has_trade_suggestion and not is_sell_evaluation and intent in ("opportunity_scan", "risk_check", "chart_validation"):
        if "stop" not in synthesis.lower() and "stop loss" not in synthesis.lower():
            issues.append("Trade suggestion missing stop loss level")
        if "target" not in synthesis.lower() and "take profit" not in synthesis.lower():
            issues.append("Trade suggestion missing target/take profit level")

    # Check for guaranteed language
    guarantee_words = ["guaranteed", "will definitely", "100% certain", "can't lose", "sure thing"]
    for word in guarantee_words:
        if word in synthesis.lower():
            issues.append(f"Contains guarantee language: '{word}'")

    return issues


def verify_node(state: AgentState) -> dict[str, Any]:
    """Verify the synthesis: fact-check, confidence, guardrails."""
    synthesis = state.get("synthesis", "")
    tool_results = state.get("tool_results", {})
    intent = state.get("intent", "general")
    attempts = state.get("verification_attempts", 0)

    all_issues = []

    # 1. Fact check
    fact_issues = _check_facts(synthesis, tool_results)
    all_issues.extend(fact_issues)

    # 2. Price quote domain check: data freshness
    price_quote_issues = _check_price_quote_freshness(intent, tool_results)
    all_issues.extend(price_quote_issues)

    # 3. Confidence score
    confidence = _compute_confidence(state)

    # 4. Risk guardrails
    guardrail_issues = _check_guardrails(synthesis, intent, tool_results)
    all_issues.extend(guardrail_issues)

    passed = len(all_issues) == 0

    verification_result = {
        "passed": passed,
        "issues": all_issues,
        "confidence": confidence,
        "fact_check_issues": len(fact_issues),
        "guardrail_issues": len(guardrail_issues),
    }

    return {
        "verification_result": verification_result,
        "verification_attempts": attempts + 1,
    }


def route_after_verification(state: AgentState) -> str:
    """Route: pass → format, fail → re-synthesize, max_retries → format with warnings."""
    verification = state.get("verification_result", {})
    attempts = state.get("verification_attempts", 0)

    if verification.get("passed", False):
        return "pass"
    elif attempts >= 2:
        return "max_retries"
    else:
        return "fail"
