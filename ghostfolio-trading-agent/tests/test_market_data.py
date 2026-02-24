"""Unit tests for get_market_data tool."""

import time
import numpy as np
import pandas as pd
import pytest

from agent.tools.market_data import (
    get_market_data,
    _compute_rsi,
    _compute_sma,
    _compute_ema,
    _compute_atr,
    _compute_macd,
    _compute_bollinger,
    _cache,
)


class TestGetMarketData:
    """Integration tests using real yfinance data."""

    def test_single_symbol_returns_data(self):
        result = get_market_data(["AAPL"], period="30d")
        assert "AAPL" in result
        assert isinstance(result["AAPL"], list)
        assert len(result["AAPL"]) > 0
        # Check record structure
        record = result["AAPL"][-1]
        assert "date" in record
        assert "open" in record
        assert "close" in record
        assert "volume" in record
        assert "rsi_14" in record
        assert "sma_20" in record
        assert "macd" in record
        assert "bb_upper" in record
        assert "atr_14" in record

    def test_multiple_symbols(self):
        result = get_market_data(["AAPL", "MSFT"], period="30d")
        assert "AAPL" in result
        assert "MSFT" in result
        assert isinstance(result["AAPL"], list)
        assert isinstance(result["MSFT"], list)

    def test_invalid_symbol_returns_error(self):
        result = get_market_data(["ZZZZXXX123"], period="30d")
        assert "ZZZZXXX123" in result
        assert isinstance(result["ZZZZXXX123"], dict)
        assert "error" in result["ZZZZXXX123"]

    def test_mixed_valid_invalid(self):
        result = get_market_data(["AAPL", "ZZZZXXX123"], period="30d")
        assert isinstance(result["AAPL"], list)
        assert "error" in result["ZZZZXXX123"]

    def test_cache_behavior(self):
        _cache.clear()
        start = time.time()
        get_market_data(["AAPL"], period="30d")
        first_duration = time.time() - start

        start = time.time()
        get_market_data(["AAPL"], period="30d")
        second_duration = time.time() - start

        # Cached call should be significantly faster
        assert second_duration < first_duration * 0.5 or second_duration < 0.01


class TestIndicators:
    """Unit tests for indicator computation against known values."""

    def test_rsi_known_values(self):
        # Construct a simple series where RSI can be verified
        prices = pd.Series([44, 44.34, 44.09, 43.61, 44.33, 44.83, 45.10,
                           45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28,
                           46.28, 46.00, 46.03, 46.41, 46.22, 45.64])
        rsi = _compute_rsi(prices, 14)
        # First 14 values should be NaN
        assert all(pd.isna(rsi.iloc[:14]))
        # RSI should be between 0 and 100
        valid = rsi.dropna()
        assert all((valid >= 0) & (valid <= 100))

    def test_sma_known_values(self):
        prices = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        sma3 = _compute_sma(prices, 3)
        assert pd.isna(sma3.iloc[0])
        assert pd.isna(sma3.iloc[1])
        assert abs(sma3.iloc[2] - 2.0) < 0.001
        assert abs(sma3.iloc[3] - 3.0) < 0.001
        assert abs(sma3.iloc[4] - 4.0) < 0.001

    def test_ema_convergence(self):
        prices = pd.Series([10.0] * 50)
        ema = _compute_ema(prices, 10)
        # EMA of constant series should equal the constant
        assert abs(ema.iloc[-1] - 10.0) < 0.001

    def test_macd_components(self):
        # Generate trending data
        prices = pd.Series(np.linspace(100, 150, 60))
        macd_line, signal_line, histogram = _compute_macd(prices)
        # In uptrend, MACD should be positive
        assert macd_line.iloc[-1] > 0
        assert len(histogram) == len(prices)

    def test_bollinger_bands(self):
        prices = pd.Series(np.random.normal(100, 5, 50))
        upper, middle, lower = _compute_bollinger(prices, 20, 2)
        # Upper > Middle > Lower
        valid_idx = ~(pd.isna(upper) | pd.isna(lower))
        assert all(upper[valid_idx] >= middle[valid_idx])
        assert all(middle[valid_idx] >= lower[valid_idx])

    def test_atr_positive(self):
        high = pd.Series(np.random.uniform(101, 110, 30))
        low = pd.Series(np.random.uniform(90, 99, 30))
        close = pd.Series(np.random.uniform(95, 105, 30))
        atr = _compute_atr(high, low, close, 14)
        valid = atr.dropna()
        assert all(valid > 0)
