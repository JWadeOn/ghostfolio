"""Unit tests for detect_regime tool."""

import pytest
from agent.tools.regime import (
    detect_regime,
    _classify_trend,
    _classify_volatility,
    _classify_breadth,
    _classify_rotation,
    _classify_correlation,
)


class TestClassifyTrend:
    def test_trending_up(self):
        # Price > SMA50 > SMA200, positive slope
        data = []
        for i in range(20):
            data.append({
                "close": 450 + i * 2,
                "sma_20": 440 + i * 2,
                "sma_50": 430 + i,
                "sma_200": 400,
            })
        result = _classify_trend(data)
        assert result["classification"] == "trending_up"

    def test_trending_down(self):
        data = []
        for i in range(20):
            data.append({
                "close": 350 - i * 2,
                "sma_20": 360 - i * 2,
                "sma_50": 380 - i,
                "sma_200": 400,
            })
        result = _classify_trend(data)
        assert result["classification"] == "trending_down"

    def test_ranging(self):
        data = []
        for i in range(20):
            data.append({
                "close": 400,
                "sma_20": 400,
                "sma_50": 405,
                "sma_200": 395,
            })
        result = _classify_trend(data)
        assert result["classification"] == "ranging"

    def test_empty_data(self):
        result = _classify_trend([])
        assert result["classification"] == "unknown"


class TestClassifyBreadth:
    def test_broad_participation(self):
        # 8 out of 9 above SMA20
        sector_data = {}
        for i, sym in enumerate(["XLK", "XLF", "XLE", "XLV", "XLI", "XLP", "XLU", "XLRE", "XLY"]):
            sector_data[sym] = [{"close": 105, "sma_20": 100}]
        sector_data["XLU"] = [{"close": 95, "sma_20": 100}]  # 1 below
        result = _classify_breadth(sector_data)
        assert result["classification"] == "broad_participation"

    def test_narrow_leadership(self):
        sector_data = {}
        for sym in ["XLK", "XLF", "XLE", "XLV", "XLI", "XLP", "XLU", "XLRE", "XLY"]:
            sector_data[sym] = [{"close": 95, "sma_20": 100}]
        # Only 2 above
        sector_data["XLK"] = [{"close": 105, "sma_20": 100}]
        sector_data["XLRE"] = [{"close": 105, "sma_20": 100}]
        result = _classify_breadth(sector_data)
        assert result["classification"] == "narrow_leadership"


class TestDetectRegime:
    def test_returns_all_dimensions(self):
        """Integration test: detect_regime should return all 5 dimensions."""
        result = detect_regime("SPY")
        assert "composite" in result or "error" in result
        if "error" not in result:
            assert "dimensions" in result
            dims = result["dimensions"]
            assert "trend" in dims
            assert "volatility" in dims
            assert "correlation" in dims
            assert "breadth" in dims
            assert "rotation" in dims
            assert "confidence" in result
            assert 0 <= result["confidence"] <= 100
            assert "timestamp" in result
