"""Unit tests for the verification node: fact-check, guardrails, and domain checks."""

import pytest
from datetime import datetime, timezone, timedelta
from agent.nodes.verification import (
    verify_node,
    _check_facts,
    _check_guardrails,
    _check_price_quote_freshness,
    _check_tax_estimate_sanity,
    _check_compliance_consistency,
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


# --- Tax estimate domain checks ---


def test_tax_estimate_sanity_passes_with_valid_result():
    issues = _check_tax_estimate_sanity(
        "Your estimated liability is $12,500.",
        {"tax_estimate": {"estimated_liability": 12500, "effective_rate": 22.0}},
    )
    assert issues == []


def test_tax_estimate_sanity_flags_negative_liability():
    issues = _check_tax_estimate_sanity(
        "Estimated liability is negative.",
        {"tax_estimate": {"estimated_liability": -500, "effective_rate": 10.0}},
    )
    assert len(issues) == 1
    assert "negative" in issues[0].lower()


def test_tax_estimate_sanity_flags_out_of_range_rate():
    issues = _check_tax_estimate_sanity(
        "Effective rate is 150%.",
        {"tax_estimate": {"estimated_liability": 1000, "effective_rate": 150}},
    )
    assert len(issues) == 1
    assert "outside" in issues[0].lower()


def test_tax_estimate_sanity_no_op_when_tool_absent():
    issues = _check_tax_estimate_sanity("No tax info.", {})
    assert issues == []


# --- Compliance consistency domain checks ---


def test_compliance_consistency_flags_contradiction():
    issues = _check_compliance_consistency(
        "There are no violations for this transaction.",
        {"compliance_check": {"passed": False, "violations": [{"rule": "wash_sale"}]}},
    )
    assert len(issues) == 1
    assert "violations" in issues[0].lower()


def test_compliance_consistency_passes_when_aligned():
    issues = _check_compliance_consistency(
        "The wash sale rule was triggered. You have 1 violation.",
        {"compliance_check": {"passed": False, "violations": [{"rule": "wash_sale"}]}},
    )
    assert issues == []


def test_compliance_consistency_no_op_when_tool_absent():
    issues = _check_compliance_consistency("All clear.", {})
    assert issues == []


# --- Confidence scoring with guardrails tools ---


def test_confidence_boosts_on_guardrails_pass():
    state = {
        "tool_results": {
            "portfolio_guardrails_check": {"passed": True, "violations": []},
        },
        "intent": "general",
    }
    from agent.nodes.verification import _compute_confidence
    score = _compute_confidence(state)
    assert score >= 60  # base 50 + 10 (tool success) + 10 (guardrails passed)


def test_confidence_drops_on_guardrails_fail():
    state = {
        "tool_results": {
            "trade_guardrails_check": {"passed": False, "violations": [{"rule": "position_size"}]},
        },
        "intent": "general",
    }
    from agent.nodes.verification import _compute_confidence
    score = _compute_confidence(state)
    assert score <= 60  # base 50 + 10 (tool success) - 5 (guardrails failed)


def test_guardrails_check_uses_trade_guardrails_for_sell():
    """_check_guardrails should read sell_evaluation from trade_guardrails_check."""
    issues = _check_guardrails(
        "You should sell your position in AAPL.",
        "risk_check",
        {"trade_guardrails_check": {"sell_evaluation": True, "action": "sell"}},
    )
    assert not any("stop loss" in i.lower() for i in issues)


def test_confidence_boosts_on_unified_guardrails_pass():
    """_compute_confidence should recognize the unified guardrails_check tool name."""
    state = {
        "tool_results": {
            "guardrails_check": {"passed": True, "violations": []},
        },
        "intent": "general",
    }
    from agent.nodes.verification import _compute_confidence
    score = _compute_confidence(state)
    assert score >= 60  # base 50 + 10 (tool success) + 10 (guardrails passed)


def test_guardrails_check_uses_unified_for_sell():
    """_check_guardrails should read sell_evaluation from unified guardrails_check."""
    issues = _check_guardrails(
        "You should sell your position in AAPL.",
        "risk_check",
        {"guardrails_check": {"sell_evaluation": True, "action": "sell"}},
    )
    assert not any("stop loss" in i.lower() for i in issues)
