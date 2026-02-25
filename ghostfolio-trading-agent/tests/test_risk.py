"""Unit tests for check_risk tool."""

import pytest
from unittest.mock import patch, MagicMock
from agent.tools.risk import check_risk


class TestCheckRisk:
    @patch("agent.tools.risk.get_portfolio_snapshot")
    @patch("agent.tools.risk.get_market_data")
    @patch("agent.tools.risk._get_sector")
    def test_passes_within_limits(self, mock_sector, mock_market, mock_portfolio):
        mock_portfolio.return_value = {
            "holdings": [
                {"symbol": "MSFT", "weight": 0.03, "sectors": [{"name": "Technology"}]},
            ],
            "summary": {
                "total_value": 100000,
                "total_cash": 20000,
                "holding_count": 1,
            },
        }
        mock_sector.return_value = "Consumer Discretionary"
        mock_market.return_value = {"TSLA": [{"date": "2024-01-01", "close": 200}]}

        result = check_risk("TSLA", "LONG", position_size_pct=3.0)
        assert result["passed"] is True
        assert len(result["violations"]) == 0

    @patch("agent.tools.risk.get_portfolio_snapshot")
    @patch("agent.tools.risk.get_market_data")
    @patch("agent.tools.risk._get_sector")
    def test_fails_position_too_large(self, mock_sector, mock_market, mock_portfolio):
        mock_portfolio.return_value = {
            "holdings": [
                {"symbol": "TSLA", "weight": 0.04, "sectors": []},  # Already 4%
            ],
            "summary": {
                "total_value": 100000,
                "total_cash": 20000,
                "holding_count": 1,
            },
        }
        mock_sector.return_value = "Consumer Discretionary"
        mock_market.return_value = {}

        result = check_risk("TSLA", "LONG", position_size_pct=3.0)
        assert result["passed"] is False
        violation_rules = [v["rule"] for v in result["violations"]]
        assert "position_size" in violation_rules

    @patch("agent.tools.risk.get_portfolio_snapshot")
    @patch("agent.tools.risk.get_market_data")
    @patch("agent.tools.risk._get_sector")
    def test_fails_insufficient_cash(self, mock_sector, mock_market, mock_portfolio):
        mock_portfolio.return_value = {
            "holdings": [],
            "summary": {
                "total_value": 100000,
                "total_cash": 5000,
                "holding_count": 0,
            },
        }
        mock_sector.return_value = "Technology"
        mock_market.return_value = {}

        result = check_risk("AAPL", "LONG", dollar_amount=10000)
        assert result["passed"] is False
        violation_rules = [v["rule"] for v in result["violations"]]
        assert "cash_available" in violation_rules

    @patch("agent.tools.risk.get_portfolio_snapshot")
    @patch("agent.tools.risk.get_market_data")
    @patch("agent.tools.risk._get_sector")
    def test_suggests_adjusted_size(self, mock_sector, mock_market, mock_portfolio):
        mock_portfolio.return_value = {
            "holdings": [
                {"symbol": "AAPL", "weight": 0.04, "sectors": []},
            ],
            "summary": {
                "total_value": 100000,
                "total_cash": 50000,
                "holding_count": 1,
            },
        }
        mock_sector.return_value = "Technology"
        mock_market.return_value = {}

        result = check_risk("AAPL", "LONG", position_size_pct=5.0)
        # Should suggest smaller size since already at 4%
        assert result["suggested_size_pct"] <= 1.0

    @patch("agent.tools.risk.get_portfolio_snapshot")
    @patch("agent.tools.risk._get_sector")
    def test_portfolio_level_risk_no_symbol(self, mock_sector, mock_portfolio):
        """When symbol is None, check_risk runs portfolio-level assessment (no proposed trade)."""
        mock_portfolio.return_value = {
            "holdings": [
                {"symbol": "GOOG", "weight": 1.0, "sectors": []},
            ],
            "summary": {
                "total_value": 155460,
                "total_cash": 0,
                "holding_count": 1,
            },
        }
        mock_sector.return_value = "Technology"

        result = check_risk()
        assert result.get("portfolio_level") is True
        assert result.get("symbol") is None
        assert "portfolio_summary" in result
        assert result["portfolio_summary"]["holding_count"] == 1
        assert result["passed"] is False
        violation_rules = [v["rule"] for v in result["violations"]]
        assert "concentration" in violation_rules or "zero_cash" in violation_rules

    @patch("agent.tools.risk.get_portfolio_snapshot")
    @patch("agent.tools.risk._get_sector")
    def test_sell_evaluation_recommends_sell_when_concentrated(self, mock_sector, mock_portfolio):
        """When action='sell' and position is concentrated, recommend_sell=True and passed=True."""
        mock_portfolio.return_value = {
            "holdings": [
                {
                    "symbol": "GOOG",
                    "weight": 100.0,
                    "value": 155460,
                    "value_in_base_currency": 155460,
                    "investment": 140000,
                    "sectors": [],
                },
            ],
            "summary": {
                "total_value": 155460,
                "total_cash": 0,
                "holding_count": 1,
            },
        }
        mock_sector.return_value = "Communication Services"

        result = check_risk("GOOG", "LONG", action="sell")
        assert result.get("sell_evaluation") is True
        assert result.get("action") == "sell"
        assert result["passed"] is True
        assert result["recommend_sell"] is True
        assert len(result["reasons_to_sell"]) > 0
        assert result["position"]["symbol"] == "GOOG"
        assert result["position"]["unrealized_pnl_pct"] is not None
        assert "portfolio_after_sell" in result

    @patch("agent.tools.risk.get_portfolio_snapshot")
    def test_sell_evaluation_no_position(self, mock_portfolio):
        """When action='sell' but user doesn't hold symbol, return error and passed=False."""
        mock_portfolio.return_value = {
            "holdings": [{"symbol": "AAPL", "weight": 50.0, "value": 10000}],
            "summary": {"total_value": 20000, "total_cash": 0, "holding_count": 1},
        }

        result = check_risk("GOOG", "LONG", action="sell")
        assert result.get("sell_evaluation") is True
        assert result["passed"] is False
        assert "error" in result
        assert "do not hold" in result["error"].lower() or "nothing to sell" in result["error"].lower()
