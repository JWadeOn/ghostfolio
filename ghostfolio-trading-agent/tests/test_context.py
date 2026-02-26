"""Unit tests for passive check_context node."""

from datetime import datetime, timezone, timedelta

from agent.nodes.context import check_context_node, REGIME_TTL, PORTFOLIO_TTL


def _fresh_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stale_ts(ttl: timedelta) -> str:
    return (datetime.now(timezone.utc) - ttl - timedelta(minutes=1)).isoformat()


def test_fresh_regime_is_preloaded():
    regime = {"composite": "bullish_expansion", "confidence": 75}
    state = {
        "regime": regime,
        "regime_timestamp": _fresh_ts(),
        "portfolio": None,
        "portfolio_timestamp": None,
    }
    result = check_context_node(state)
    assert result["regime"] == regime
    assert result["regime_timestamp"] is not None


def test_stale_regime_is_cleared():
    state = {
        "regime": {"composite": "old"},
        "regime_timestamp": _stale_ts(REGIME_TTL),
        "portfolio": None,
        "portfolio_timestamp": None,
    }
    result = check_context_node(state)
    assert result["regime"] is None
    assert result["regime_timestamp"] is None


def test_missing_regime_stays_none():
    state = {
        "regime": None,
        "regime_timestamp": None,
        "portfolio": None,
        "portfolio_timestamp": None,
    }
    result = check_context_node(state)
    assert result["regime"] is None


def test_fresh_portfolio_is_preloaded():
    portfolio = {"summary": {"total_value": 100000}}
    state = {
        "regime": None,
        "regime_timestamp": None,
        "portfolio": portfolio,
        "portfolio_timestamp": _fresh_ts(),
    }
    result = check_context_node(state)
    assert result["portfolio"] == portfolio
    assert result["portfolio_timestamp"] is not None


def test_stale_portfolio_is_cleared():
    state = {
        "regime": None,
        "regime_timestamp": None,
        "portfolio": {"summary": {"total_value": 100000}},
        "portfolio_timestamp": _stale_ts(PORTFOLIO_TTL),
    }
    result = check_context_node(state)
    assert result["portfolio"] is None
    assert result["portfolio_timestamp"] is None


def test_no_routing_or_tools_needed_in_result():
    """Passive context never sets tools_needed or returns routing info."""
    state = {
        "regime": {"composite": "bullish_expansion"},
        "regime_timestamp": _fresh_ts(),
        "portfolio": {"summary": {"total_value": 100000}},
        "portfolio_timestamp": _fresh_ts(),
    }
    result = check_context_node(state)
    assert "tools_needed" not in result
