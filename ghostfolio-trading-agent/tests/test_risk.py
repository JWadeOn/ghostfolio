"""Unit tests for portfolio_guardrails_check, trade_guardrails_check, and guardrails_check."""

import pytest
from unittest.mock import patch, MagicMock
from agent.tools.risk import portfolio_guardrails_check, trade_guardrails_check, check_risk, guardrails_check


class TestPortfolioGuardrailsCheck:
    @patch("agent.tools.risk.get_portfolio_snapshot")
    @patch("agent.tools.risk._get_sector")
    def test_passes_well_diversified(self, mock_sector, mock_portfolio):
        mock_portfolio.return_value = {
            "holdings": [
                {"symbol": "AAPL", "weight": 0.03, "sectors": []},
                {"symbol": "GOOG", "weight": 0.02, "sectors": []},
            ],
            "summary": {"total_value": 100000, "total_cash": 15000, "holding_count": 2},
        }
        mock_sector.return_value = "Technology"

        result = portfolio_guardrails_check()
        assert result["passed"] is True
        assert result.get("portfolio_level") is True
        assert len(result["violations"]) == 0

    @patch("agent.tools.risk.get_portfolio_snapshot")
    @patch("agent.tools.risk._get_sector")
    def test_flags_single_holding_concentration(self, mock_sector, mock_portfolio):
        mock_portfolio.return_value = {
            "holdings": [{"symbol": "GOOG", "weight": 1.0, "sectors": []}],
            "summary": {"total_value": 155000, "total_cash": 0, "holding_count": 1},
        }
        mock_sector.return_value = "Technology"

        result = portfolio_guardrails_check()
        assert result["passed"] is False
        rules = [v["rule"] for v in result["violations"]]
        assert "concentration" in rules or "zero_cash" in rules

    @patch("agent.tools.risk.get_portfolio_snapshot")
    @patch("agent.tools.risk._get_sector")
    def test_warns_low_cash(self, mock_sector, mock_portfolio):
        mock_portfolio.return_value = {
            "holdings": [
                {"symbol": "AAPL", "weight": 0.03, "sectors": []},
                {"symbol": "MSFT", "weight": 0.02, "sectors": []},
            ],
            "summary": {"total_value": 100000, "total_cash": 7000, "holding_count": 2},
        }
        mock_sector.return_value = "Technology"

        result = portfolio_guardrails_check()
        assert any(w["rule"] == "low_cash" for w in result.get("warnings", []))


class TestTradeGuardrailsCheckBuy:
    @patch("agent.tools.risk.get_portfolio_snapshot")
    @patch("agent.tools.risk.get_market_data")
    @patch("agent.tools.risk._get_sector")
    def test_passes_within_limits(self, mock_sector, mock_market, mock_portfolio):
        mock_portfolio.return_value = {
            "holdings": [
                {"symbol": "MSFT", "weight": 0.03, "sectors": [{"name": "Technology"}]},
            ],
            "summary": {"total_value": 100000, "total_cash": 20000, "holding_count": 1},
        }
        mock_sector.return_value = "Consumer Discretionary"
        mock_market.return_value = {"TSLA": [{"date": "2024-01-01", "close": 200}]}

        result = trade_guardrails_check("TSLA", side="buy", position_size_pct=3.0)
        assert result["passed"] is True
        assert len(result["violations"]) == 0
        assert result.get("action") == "buy"

    @patch("agent.tools.risk.get_portfolio_snapshot")
    @patch("agent.tools.risk.get_market_data")
    @patch("agent.tools.risk._get_sector")
    def test_fails_position_too_large(self, mock_sector, mock_market, mock_portfolio):
        mock_portfolio.return_value = {
            "holdings": [{"symbol": "TSLA", "weight": 0.04, "sectors": []}],
            "summary": {"total_value": 100000, "total_cash": 20000, "holding_count": 1},
        }
        mock_sector.return_value = "Consumer Discretionary"
        mock_market.return_value = {}

        result = trade_guardrails_check("TSLA", side="buy", position_size_pct=3.0)
        assert result["passed"] is False
        assert any(v["rule"] == "position_size" for v in result["violations"])

    @patch("agent.tools.risk.get_portfolio_snapshot")
    @patch("agent.tools.risk.get_market_data")
    @patch("agent.tools.risk._get_sector")
    def test_fails_insufficient_cash(self, mock_sector, mock_market, mock_portfolio):
        mock_portfolio.return_value = {
            "holdings": [],
            "summary": {"total_value": 100000, "total_cash": 5000, "holding_count": 0},
        }
        mock_sector.return_value = "Technology"
        mock_market.return_value = {}

        result = trade_guardrails_check("AAPL", side="buy", dollar_amount=10000)
        assert result["passed"] is False
        assert any(v["rule"] == "cash_available" for v in result["violations"])

    @patch("agent.tools.risk.get_portfolio_snapshot")
    @patch("agent.tools.risk.get_market_data")
    @patch("agent.tools.risk._get_sector")
    def test_suggests_adjusted_size(self, mock_sector, mock_market, mock_portfolio):
        mock_portfolio.return_value = {
            "holdings": [{"symbol": "AAPL", "weight": 0.04, "sectors": []}],
            "summary": {"total_value": 100000, "total_cash": 50000, "holding_count": 1},
        }
        mock_sector.return_value = "Technology"
        mock_market.return_value = {}

        result = trade_guardrails_check("AAPL", side="buy", position_size_pct=5.0)
        assert result["suggested_size_pct"] <= 1.0

    @patch("agent.tools.risk.get_portfolio_snapshot")
    @patch("agent.tools.risk.get_market_data")
    @patch("agent.tools.risk._get_sector")
    def test_buy_includes_stop_loss_level(self, mock_sector, mock_market, mock_portfolio):
        mock_portfolio.return_value = {
            "holdings": [],
            "summary": {"total_value": 100000, "total_cash": 50000, "holding_count": 0},
        }
        mock_sector.return_value = "Technology"
        mock_market.return_value = {"AAPL": [{"date": "2024-01-01", "close": 200}]}

        result = trade_guardrails_check("AAPL", side="buy", position_size_pct=3.0)
        assert result.get("stop_loss_level") is not None
        assert result["stop_loss_level"] < 200


class TestTradeGuardrailsCheckSell:
    @patch("agent.tools.risk.get_portfolio_snapshot")
    @patch("agent.tools.risk._get_sector")
    def test_sell_recommends_when_concentrated(self, mock_sector, mock_portfolio):
        mock_portfolio.return_value = {
            "holdings": [
                {
                    "symbol": "GOOG",
                    "weight": 100.0,
                    "value": 155460,
                    "value_in_base_currency": 155460,
                    "investment": 140000,
                    "quantity": 100,
                    "sectors": [],
                },
            ],
            "summary": {"total_value": 155460, "total_cash": 0, "holding_count": 1},
        }
        mock_sector.return_value = "Communication Services"

        result = trade_guardrails_check("GOOG", side="sell")
        assert result.get("sell_evaluation") is True
        assert result.get("action") == "sell"
        assert result["passed"] is True
        assert result["recommend_sell"] is True
        assert len(result["reasons_to_sell"]) > 0
        assert result["position"]["symbol"] == "GOOG"
        assert result["position"]["unrealized_pnl_pct"] is not None
        assert "portfolio_after_sell" in result

    @patch("agent.tools.risk.get_portfolio_snapshot")
    @patch("agent.tools.risk._get_sector")
    def test_sell_includes_stop_loss_and_hold_period(self, mock_sector, mock_portfolio):
        mock_portfolio.return_value = {
            "holdings": [
                {
                    "symbol": "GOOG",
                    "weight": 100.0,
                    "value": 155460,
                    "investment": 140000,
                    "quantity": 100,
                    "sectors": [],
                },
            ],
            "summary": {"total_value": 155460, "total_cash": 0, "holding_count": 1},
        }
        mock_sector.return_value = "Communication Services"

        result = trade_guardrails_check("GOOG", side="sell")
        assert result.get("stop_loss_level") is not None
        # hold_period may be None if no client provided — that's fine
        assert "hold_period" in result

    @patch("agent.tools.risk.get_portfolio_snapshot")
    def test_sell_no_position(self, mock_portfolio):
        mock_portfolio.return_value = {
            "holdings": [{"symbol": "AAPL", "weight": 50.0, "value": 10000}],
            "summary": {"total_value": 20000, "total_cash": 0, "holding_count": 1},
        }

        result = trade_guardrails_check("GOOG", side="sell")
        assert result.get("sell_evaluation") is True
        assert result["passed"] is False
        assert "error" in result


class TestCheckRiskLegacy:
    """Ensure the legacy check_risk wrapper still delegates correctly."""

    @patch("agent.tools.risk.get_portfolio_snapshot")
    @patch("agent.tools.risk._get_sector")
    def test_legacy_no_symbol_calls_portfolio(self, mock_sector, mock_portfolio):
        mock_portfolio.return_value = {
            "holdings": [],
            "summary": {"total_value": 10000, "total_cash": 10000, "holding_count": 0},
        }
        mock_sector.return_value = None

        result = check_risk()
        assert result.get("portfolio_level") is True

    @patch("agent.tools.risk.get_portfolio_snapshot")
    @patch("agent.tools.risk.get_market_data")
    @patch("agent.tools.risk._get_sector")
    def test_legacy_buy_delegates(self, mock_sector, mock_market, mock_portfolio):
        mock_portfolio.return_value = {
            "holdings": [],
            "summary": {"total_value": 100000, "total_cash": 50000, "holding_count": 0},
        }
        mock_sector.return_value = "Technology"
        mock_market.return_value = {}

        result = check_risk("AAPL", position_size_pct=3.0)
        assert result.get("action") == "buy"

    @patch("agent.tools.risk.get_portfolio_snapshot")
    @patch("agent.tools.risk._get_sector")
    def test_legacy_sell_delegates(self, mock_sector, mock_portfolio):
        mock_portfolio.return_value = {
            "holdings": [{"symbol": "GOOG", "weight": 50.0, "value": 10000, "investment": 8000, "quantity": 10}],
            "summary": {"total_value": 20000, "total_cash": 0, "holding_count": 1},
        }
        mock_sector.return_value = "Communication Services"

        result = check_risk("GOOG", action="sell")
        assert result.get("sell_evaluation") is True


class TestGuardrailsCheck:
    """Tests for the unified guardrails_check() function."""

    @patch("agent.tools.risk.get_portfolio_snapshot")
    @patch("agent.tools.risk._get_sector")
    def test_no_symbol_routes_to_portfolio(self, mock_sector, mock_portfolio):
        mock_portfolio.return_value = {
            "holdings": [
                {"symbol": "AAPL", "weight": 0.03, "sectors": []},
                {"symbol": "GOOG", "weight": 0.02, "sectors": []},
            ],
            "summary": {"total_value": 100000, "total_cash": 15000, "holding_count": 2},
        }
        mock_sector.return_value = "Technology"

        result = guardrails_check()
        assert result.get("portfolio_level") is True
        assert result["passed"] is True

    @patch("agent.tools.risk.get_portfolio_snapshot")
    @patch("agent.tools.risk._get_sector")
    def test_empty_symbol_routes_to_portfolio(self, mock_sector, mock_portfolio):
        mock_portfolio.return_value = {
            "holdings": [],
            "summary": {"total_value": 10000, "total_cash": 10000, "holding_count": 0},
        }
        mock_sector.return_value = None

        result = guardrails_check(symbol="")
        assert result.get("portfolio_level") is True

    @patch("agent.tools.risk.get_portfolio_snapshot")
    @patch("agent.tools.risk.get_market_data")
    @patch("agent.tools.risk._get_sector")
    def test_with_symbol_routes_to_trade(self, mock_sector, mock_market, mock_portfolio):
        mock_portfolio.return_value = {
            "holdings": [],
            "summary": {"total_value": 100000, "total_cash": 50000, "holding_count": 0},
        }
        mock_sector.return_value = "Technology"
        mock_market.return_value = {"AAPL": [{"date": "2024-01-01", "close": 200}]}

        result = guardrails_check(symbol="AAPL", side="buy", position_size_pct=3.0)
        assert result.get("action") == "buy"
        assert result.get("symbol") == "AAPL"

    @patch("agent.tools.risk.get_portfolio_snapshot")
    @patch("agent.tools.risk._get_sector")
    def test_sell_via_unified(self, mock_sector, mock_portfolio):
        mock_portfolio.return_value = {
            "holdings": [{"symbol": "GOOG", "weight": 50.0, "value": 10000, "investment": 8000, "quantity": 10}],
            "summary": {"total_value": 20000, "total_cash": 0, "holding_count": 1},
        }
        mock_sector.return_value = "Communication Services"

        result = guardrails_check(symbol="GOOG", side="sell")
        assert result.get("sell_evaluation") is True
        assert result.get("action") == "sell"

    @patch("agent.tools.risk.get_portfolio_snapshot")
    @patch("agent.tools.risk._get_sector")
    def test_accepts_portfolio_data_kwarg(self, mock_sector, mock_portfolio):
        """Ensure pre-fetched portfolio_data is accepted and used."""
        portfolio_data = {
            "holdings": [{"symbol": "AAPL", "weight": 0.03, "sectors": []}],
            "summary": {"total_value": 100000, "total_cash": 15000, "holding_count": 1},
        }
        mock_sector.return_value = "Technology"

        result = guardrails_check(portfolio_data=portfolio_data)
        assert result.get("portfolio_level") is True
        # get_portfolio_snapshot should NOT be called since we pass portfolio_data
        mock_portfolio.assert_not_called()
