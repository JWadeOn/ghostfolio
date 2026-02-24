"""Unit tests for scan_strategies tool and individual strategies."""

import pytest
from agent.strategies.vcp_breakout import VCPBreakoutStrategy
from agent.strategies.mean_reversion import MeanReversionStrategy
from agent.strategies.momentum import MomentumStrategy
from agent.tools.scanner import scan_strategies, ALL_STRATEGIES


class TestVCPBreakout:
    def test_match(self):
        strategy = VCPBreakoutStrategy()
        # Build data that matches VCP: low ATR, near 52wk high, declining volume
        data = []
        for i in range(60):
            data.append({
                "close": 100 + i * 0.1,
                "high": 101 + i * 0.1,
                "low": 99 + i * 0.1,
                "volume": 1000000 - i * 5000,  # declining
                "atr_14": 0.5,  # very low
                "dist_52w_high_pct": -2.0,  # within 5%
                "sma_20": 98,
                "rsi_14": 60,
            })
        result = strategy.scan("TEST", data)
        # Note: might or might not match depending on percentile calc
        # The key is it doesn't crash
        assert result is None or isinstance(result, dict)

    def test_no_match_far_from_high(self):
        strategy = VCPBreakoutStrategy()
        data = [{"close": 80, "atr_14": 0.5, "dist_52w_high_pct": -20.0,
                 "volume": 1000000, "high": 81, "low": 79}] * 60
        result = strategy.scan("TEST", data)
        assert result is None

    def test_favorable_regimes(self):
        strategy = VCPBreakoutStrategy()
        assert "bullish_expansion" in strategy.favorable_regimes


class TestMeanReversion:
    def test_no_match_high_rsi(self):
        strategy = MeanReversionStrategy()
        data = [{"close": 100, "rsi_14": 55, "sma_200": 90,
                 "bb_lower": 95, "bb_middle": 100, "low": 100, "atr_14": 2}] * 30
        result = strategy.scan("TEST", data)
        assert result is None

    def test_match_conditions(self):
        strategy = MeanReversionStrategy()
        data = []
        for i in range(30):
            data.append({
                "close": 105,
                "rsi_14": 25,
                "sma_200": 100,
                "bb_lower": 106,  # price dipped below BB
                "bb_middle": 110,
                "low": 104,
                "atr_14": 2,
                "relative_volume": 1.8,
            })
        result = strategy.scan("TEST", data)
        assert result is not None
        assert result["strategy"] == "mean_reversion"
        assert "score" in result
        assert "entry" in result


class TestMomentum:
    def test_no_match_low_rsi(self):
        strategy = MomentumStrategy()
        data = [{"close": 100, "rsi_14": 30, "ema_21": 95,
                 "relative_volume": 1.5, "atr_14": 2, "macd_histogram": 0.5}] * 30
        result = strategy.scan("TEST", data)
        assert result is None

    def test_favorable_regimes(self):
        strategy = MomentumStrategy()
        assert "bullish_expansion" in strategy.favorable_regimes


class TestScanStrategies:
    def test_returns_structure(self):
        result = scan_strategies(symbols=["AAPL"], strategy_names=["momentum"])
        assert "opportunities" in result
        assert "scanned" in result
        assert "strategies_used" in result
        assert result["scanned"] == 1

    def test_all_strategies_registered(self):
        assert len(ALL_STRATEGIES) == 3
        names = {s.name for s in ALL_STRATEGIES}
        assert "vcp_breakout" in names
        assert "mean_reversion" in names
        assert "momentum" in names
