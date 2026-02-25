"""Unit tests for the verification node: fact-check and guardrails."""

import pytest
from datetime import datetime, timezone, timedelta
from agent.nodes.verification import (
    verify_node,
    _check_facts,
    _check_guardrails,
    _check_price_quote_freshness,
)


def test_verify_node_fails_when_synthesis_contains_unsourced_number():
    """Verification should fail when synthesis mentions a number not in tool_results."""
    state = {
        "synthesis": "AAPL is trading at $199.99 with RSI at 72.",
        "tool_results": {
            "get_market_data": {
                "AAPL": [{"close": 195.50, "rsi": 68.0}],
            },
        },
        "intent": "chart_validation",
        "verification_attempts": 0,
    }
    result = verify_node(state)
    assert result["verification_result"]["passed"] is False
    assert result["verification_result"]["fact_check_issues"] >= 1
    assert any("199" in str(i) or "72" in str(i) for i in result["verification_result"]["issues"])


def test_verify_node_passes_when_numbers_match_tool_results():
    """Verification should pass when all numbers in synthesis appear in tool_results."""
    state = {
        "synthesis": "AAPL closed near 195.50 with RSI at 68.",
        "tool_results": {
            "get_market_data": {
                "AAPL": [{"close": 195.50, "rsi": 68.0}],
            },
        },
        "intent": "chart_validation",
        "verification_attempts": 0,
    }
    result = verify_node(state)
    assert result["verification_result"]["passed"] is True
    assert result["verification_result"]["fact_check_issues"] == 0


def test_verify_node_guardrail_flags_guarantee_language():
    """Verification should flag synthesis containing guarantee language."""
    state = {
        "synthesis": "This trade is guaranteed to make 50% returns. Sure thing!",
        "tool_results": {},
        "intent": "general",
        "verification_attempts": 0,
    }
    result = verify_node(state)
    assert result["verification_result"]["passed"] is False
    assert result["verification_result"]["guardrail_issues"] >= 1
    assert any("guarantee" in str(i).lower() or "sure thing" in str(i).lower() for i in result["verification_result"]["issues"])


def test_verify_node_guardrail_requires_stop_and_target_for_trade_suggestion():
    """When synthesis suggests a trade, it must mention stop and target."""
    state = {
        "synthesis": "I recommend you buy NVDA here for a long position.",
        "tool_results": {"get_market_data": {}},
        "intent": "opportunity_scan",
        "verification_attempts": 0,
    }
    result = verify_node(state)
    assert result["verification_result"]["passed"] is False
    assert result["verification_result"]["guardrail_issues"] >= 1
    issues_text = " ".join(result["verification_result"]["issues"]).lower()
    assert "stop" in issues_text or "target" in issues_text


def test_price_quote_freshness_fails_when_data_not_from_today():
    """When intent is price_quote and latest data date is before today, verification should fail."""
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    state = {
        "synthesis": "TSLA is trading at $446.89.",
        "tool_results": {
            "get_market_data": {
                "TSLA": [
                    {"date": yesterday, "close": 446.89, "open": 448.95},
                ],
            },
        },
        "intent": "price_quote",
        "verification_attempts": 0,
    }
    result = verify_node(state)
    assert result["verification_result"]["passed"] is False
    assert any(
        "not current trading day" in str(i) or "as of" in str(i).lower()
        for i in result["verification_result"]["issues"]
    )


def test_price_quote_freshness_passes_when_data_from_today():
    """When intent is price_quote and latest data date is today, no freshness issue."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    state = {
        "synthesis": "TSLA is trading at $409.00.",
        "tool_results": {
            "get_market_data": {
                "TSLA": [{"date": today, "close": 409.0, "open": 408.5}],
            },
        },
        "intent": "price_quote",
        "verification_attempts": 0,
    }
    result = verify_node(state)
    assert not any(
        "not current trading day" in str(i) for i in result["verification_result"]["issues"]
    )
