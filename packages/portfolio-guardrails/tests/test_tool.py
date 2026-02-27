"""Tests for portfolio_guardrails tool."""

import pytest
from portfolio_guardrails import portfolio_guardrails_check
from portfolio_guardrails.tool import _check_impl


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CLEAN_PORTFOLIO = [
    {"symbol": "AAPL", "value": 14_000, "sector": "Technology"},
    {"symbol": "JNJ", "value": 14_000, "sector": "Healthcare"},
    {"symbol": "JPM", "value": 14_000, "sector": "Financials"},
    {"symbol": "XOM", "value": 14_000, "sector": "Energy"},
    {"symbol": "PG", "value": 14_000, "sector": "Consumer Staples"},
    {"symbol": "VZ", "value": 14_000, "sector": "Telecom"},
    {"symbol": "CASH", "value": 16_000, "sector": "Cash"},
]


# ---------------------------------------------------------------------------
# 1. Clean portfolio passes
# ---------------------------------------------------------------------------

def test_clean_portfolio_passes():
    result = _check_impl(CLEAN_PORTFOLIO)
    assert result["passed"] is True
    assert result["violations"] == []


# ---------------------------------------------------------------------------
# 2. Over-concentrated single position
# ---------------------------------------------------------------------------

def test_position_concentration_violation():
    holdings = [
        {"symbol": "TSLA", "value": 80_000, "sector": "Technology"},
        {"symbol": "AAPL", "value": 10_000, "sector": "Technology"},
        {"symbol": "CASH", "value": 10_000, "sector": "Cash"},
    ]
    result = _check_impl(holdings)
    assert result["passed"] is False
    assert any("Position concentration" in v and "TSLA" in v for v in result["violations"])


def test_position_concentration_warning():
    holdings = [
        {"symbol": "TSLA", "value": 18_000, "sector": "Technology"},
        {"symbol": "AAPL", "value": 30_000, "sector": "Technology"},
        {"symbol": "JNJ", "value": 30_000, "sector": "Healthcare"},
        {"symbol": "JPM", "value": 15_000, "sector": "Financials"},
        {"symbol": "CASH", "value": 7_000, "sector": "Cash"},
    ]
    result = _check_impl(holdings)
    assert any("Position concentration" in w and "TSLA" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# 3. Over-concentrated sector
# ---------------------------------------------------------------------------

def test_sector_concentration_violation():
    holdings = [
        {"symbol": "AAPL", "value": 25_000, "sector": "Technology"},
        {"symbol": "MSFT", "value": 25_000, "sector": "Technology"},
        {"symbol": "JNJ", "value": 5_000, "sector": "Healthcare"},
        {"symbol": "CASH", "value": 5_000, "sector": "Cash"},
    ]
    result = _check_impl(holdings)
    assert result["passed"] is False
    assert any("Sector concentration" in v and "Technology" in v for v in result["violations"])


# ---------------------------------------------------------------------------
# 4. Insufficient cash
# ---------------------------------------------------------------------------

def test_cash_buffer_violation():
    holdings = [
        {"symbol": "AAPL", "value": 20_000, "sector": "Technology"},
        {"symbol": "JNJ", "value": 20_000, "sector": "Healthcare"},
        {"symbol": "JPM", "value": 20_000, "sector": "Financials"},
        {"symbol": "XOM", "value": 20_000, "sector": "Energy"},
        {"symbol": "CASH", "value": 500, "sector": "Cash"},
    ]
    result = _check_impl(holdings)
    assert result["passed"] is False
    assert any("Cash buffer" in v for v in result["violations"])


# ---------------------------------------------------------------------------
# 5. Single holding → diversification violation
# ---------------------------------------------------------------------------

def test_single_holding_violation():
    holdings = [
        {"symbol": "BTC", "value": 97_000, "sector": "Crypto"},
        {"symbol": "CASH", "value": 3_000, "sector": "Cash"},
    ]
    result = _check_impl(holdings)
    assert result["passed"] is False
    assert any("Diversification" in v for v in result["violations"])


# ---------------------------------------------------------------------------
# 6. Combined violations
# ---------------------------------------------------------------------------

def test_combined_violations():
    holdings = [
        {"symbol": "TSLA", "value": 95_000, "sector": "Technology"},
        {"symbol": "CASH", "value": 500, "sector": "Cash"},
    ]
    result = _check_impl(holdings)
    assert result["passed"] is False
    # Should have position, sector, cash, diversification, and extreme violations
    assert len(result["violations"]) >= 3


# ---------------------------------------------------------------------------
# 7. LangChain tool interface
# ---------------------------------------------------------------------------

def test_langchain_tool_interface_invoke():
    result = portfolio_guardrails_check.invoke({"holdings": CLEAN_PORTFOLIO})
    assert isinstance(result, dict)
    assert "passed" in result
    assert result["passed"] is True


def test_langchain_tool_metadata():
    assert portfolio_guardrails_check.name == "portfolio_guardrails_check"
    assert len(portfolio_guardrails_check.description) > 0
    assert "portfolio" in portfolio_guardrails_check.description.lower()
