"""Mock yfinance OHLCV data for eval runs — AAPL, TSLA, GOOG, SPY, VIX. No network calls."""

from __future__ import annotations

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Any

# Symbols we provide mock OHLCV for (regime uses SPY, VIX; price_quote uses AAPL, etc.)
MOCK_OHLCV_SYMBOLS = {"AAPL", "TSLA", "GOOG", "MSFT", "NVDA", "SPY", "VIX"}

# Realistic last prices for synthesis (so agent can say "$187.50" etc.)
MOCK_LAST_CLOSE = {
    "AAPL": 187.50,
    "TSLA": 248.00,
    "GOOG": 142.00,
    "MSFT": 415.00,
    "NVDA": 875.00,
    "SPY": 545.00,
    "VIX": 16.50,
}


def _make_mock_ohlcv_df(symbol: str, num_days: int = 252) -> pd.DataFrame:
    """Build a DataFrame with Open, High, Low, Close, Volume for indicator computation."""
    base = MOCK_LAST_CLOSE.get(symbol, 100.0)
    end = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    dates = pd.date_range(end=end, periods=num_days, freq="B")
    np.random.seed(hash(symbol) % 2**32)
    returns = np.random.randn(num_days) * 0.01
    close = base * np.exp(np.cumsum(returns))
    close = np.maximum(close, base * 0.5)
    open_ = np.roll(close, 1)
    open_[0] = close[0] * 0.99
    high = np.maximum(open_, close) * (1 + np.abs(np.random.randn(num_days)) * 0.005)
    low = np.minimum(open_, close) * (1 - np.abs(np.random.randn(num_days)) * 0.005)
    volume = (np.random.rand(num_days) * 1e7 + 5e6).astype(int)
    df = pd.DataFrame(
        {
            "Open": open_,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": volume,
        },
        index=dates,
    )
    df.index.name = "Date"
    return df


def mock_fetch_with_retry(
    symbols: list[str], period: str, interval: str, max_retries: int = 3
) -> dict[str, pd.DataFrame]:
    """Replace agent.tools.market_data._fetch_with_retry for evals. Returns mock DataFrames."""
    result: dict[str, pd.DataFrame] = {}
    num_days = 252
    if period in ("1d", "5d"):
        num_days = 5 if period == "5d" else 1
    elif "d" in period:
        try:
            num_days = min(252, int(period.replace("d", "")))
        except ValueError:
            num_days = 60
    for symbol in symbols:
        sym_upper = (symbol or "").strip().upper()
        if sym_upper in MOCK_OHLCV_SYMBOLS or not sym_upper:
            result[symbol] = _make_mock_ohlcv_df(sym_upper or "AAPL", num_days=num_days)
        else:
            # Unknown symbol: still return data so agent doesn't error (use AAPL shape)
            result[symbol] = _make_mock_ohlcv_df("AAPL", num_days=num_days)
    return result
