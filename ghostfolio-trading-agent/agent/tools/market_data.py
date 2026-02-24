"""Tool 1: get_market_data — fetch OHLCV + compute technical indicators via yfinance."""

from __future__ import annotations

import time
import logging
from typing import Any
from functools import lru_cache

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# yfinance only accepts these periods: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
VALID_YF_PERIODS = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}


def _normalize_period(period: str) -> str:
    """Map user-friendly timeframes to valid yfinance period strings."""
    if not period or not isinstance(period, str):
        return "60d"
    p = period.strip().lower().replace(" ", "")
    if p in VALID_YF_PERIODS:
        return p
    # Map N-day / Nd style to a valid period with enough data
    if p.endswith("day") or (p.endswith("d") and len(p) > 1 and p[:-1].isdigit()):
        try:
            if p.endswith("day"):
                n = int(p.replace("day", "").replace("-", "").strip() or "0")
            else:
                n = int(p[:-1])
        except ValueError:
            return "1mo"
        if n <= 1:
            return "1d"
        if n <= 5:
            return "5d"
        if n <= 22:
            return "1mo"   # ~22 trading days
        if n <= 66:
            return "3mo"   # ~66 trading days
        if n <= 126:
            return "6mo"
        if n <= 252:
            return "1y"
        if n <= 504:
            return "2y"
        return "5y"
    # "1month" -> "1mo", "3months" -> "3mo", etc.
    if "month" in p or "mo" in p:
        for mo, yf in [("6mo", "6mo"), ("3mo", "3mo"), ("1mo", "1mo")]:
            if mo in p:
                return yf
        return "1mo"
    if "year" in p or ("y" in p and "day" not in p):
        for y, yf in [("10y", "10y"), ("5y", "5y"), ("2y", "2y"), ("1y", "1y")]:
            if y in p:
                return yf
        return "1y"
    return "1mo"


# Simple in-memory cache: (symbols_key, period, interval) -> (timestamp, result)
_cache: dict[tuple, tuple[float, dict]] = {}
_CACHE_TTL = 300  # 5 minutes


def _cache_key(symbols: list[str], period: str, interval: str) -> tuple:
    return (tuple(sorted(symbols)), period, interval)


def _fetch_with_retry(
    symbols: list[str], period: str, interval: str, max_retries: int = 3
) -> dict[str, pd.DataFrame]:
    """Fetch OHLCV data from yfinance with exponential backoff retry."""
    results: dict[str, pd.DataFrame] = {}

    for symbol in symbols:
        last_err = None
        for attempt in range(max_retries):
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(period=period, interval=interval)
                if df.empty:
                    last_err = f"No data returned for {symbol}"
                    break  # Don't retry if symbol is invalid/delisted
                results[symbol] = df
                last_err = None
                break
            except Exception as e:
                last_err = str(e)
                if attempt < max_retries - 1:
                    wait = 2**attempt
                    logger.warning(
                        f"yfinance retry {attempt+1}/{max_retries} for {symbol}: {e}"
                    )
                    time.sleep(wait)
        if last_err:
            results[symbol] = pd.DataFrame()  # Empty signals error
            logger.error(f"Failed to fetch {symbol}: {last_err}")

    return results


def _compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Compute RSI using exponential moving average method."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    # Avoid division by zero (e.g. when no losses in window) to prevent SIGFPE
    avg_loss_safe = avg_loss.replace(0, np.nan)
    rs = (avg_gain / avg_loss_safe).fillna(0).replace([np.inf, -np.inf], 1e10)
    rsi = 100 - (100 / (1 + rs))
    # First `period` values are unreliable
    rsi.iloc[:period] = np.nan
    return rsi


def _compute_sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def _compute_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _compute_macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Returns (macd_line, signal_line, histogram)."""
    ema_fast = _compute_ema(series, fast)
    ema_slow = _compute_ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _compute_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _compute_bollinger(
    series: pd.Series, period: int = 20, std_dev: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Returns (upper, middle, lower)."""
    middle = _compute_sma(series, period)
    rolling_std = series.rolling(window=period).std()
    upper = middle + (rolling_std * std_dev)
    lower = middle - (rolling_std * std_dev)
    return upper, middle, lower


def _compute_atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    """Compute Average True Range."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return true_range.rolling(window=period).mean()


def _compute_indicators(df: pd.DataFrame) -> dict[str, Any]:
    """Compute all technical indicators and return list of dated records."""
    # Ensure chronological order (oldest first) so warmup NaNs are in early rows
    # and the last record (used as "latest" by formatter) has valid RSI/SMA.
    df = df.sort_index(ascending=True).copy()
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"] if "Volume" in df.columns else pd.Series(
        np.nan, index=df.index
    )

    # Indicators
    rsi = _compute_rsi(close, 14)
    sma_20 = _compute_sma(close, 20)
    sma_50 = _compute_sma(close, 50)
    sma_200 = _compute_sma(close, 200)
    ema_10 = _compute_ema(close, 10)
    ema_21 = _compute_ema(close, 21)
    macd_line, macd_signal, macd_hist = _compute_macd(close)
    bb_upper, bb_middle, bb_lower = _compute_bollinger(close)
    atr = _compute_atr(high, low, close)

    # Relative volume (current / 20-day avg)
    vol_sma_20 = _compute_sma(volume, 20)
    relative_volume = volume / vol_sma_20.replace(0, np.nan)

    # 52-week high/low distances
    rolling_252_high = high.rolling(window=252, min_periods=1).max()
    rolling_252_low = low.rolling(window=252, min_periods=1).min()
    dist_52w_high = ((close - rolling_252_high) / rolling_252_high * 100)
    dist_52w_low = ((close - rolling_252_low) / rolling_252_low * 100)

    records = []
    for i, date in enumerate(df.index):
        record = {
            "date": date.strftime("%Y-%m-%d"),
            "open": _safe_float(df["Open"].iloc[i]),
            "high": _safe_float(high.iloc[i]),
            "low": _safe_float(low.iloc[i]),
            "close": _safe_float(close.iloc[i]),
            "volume": _safe_float(volume.iloc[i]),
            "rsi_14": _safe_float(rsi.iloc[i]),
            "sma_20": _safe_float(sma_20.iloc[i]),
            "sma_50": _safe_float(sma_50.iloc[i]),
            "sma_200": _safe_float(sma_200.iloc[i]),
            "ema_10": _safe_float(ema_10.iloc[i]),
            "ema_21": _safe_float(ema_21.iloc[i]),
            "macd": _safe_float(macd_line.iloc[i]),
            "macd_signal": _safe_float(macd_signal.iloc[i]),
            "macd_histogram": _safe_float(macd_hist.iloc[i]),
            "bb_upper": _safe_float(bb_upper.iloc[i]),
            "bb_middle": _safe_float(bb_middle.iloc[i]),
            "bb_lower": _safe_float(bb_lower.iloc[i]),
            "atr_14": _safe_float(atr.iloc[i]),
            "relative_volume": _safe_float(relative_volume.iloc[i]),
            "dist_52w_high_pct": _safe_float(dist_52w_high.iloc[i]),
            "dist_52w_low_pct": _safe_float(dist_52w_low.iloc[i]),
        }
        records.append(record)

    return records


def _safe_float(val: Any) -> float | None:
    """Convert to float, return None for NaN/inf."""
    if val is None:
        return None
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f):
            return None
        return round(f, 4)
    except (ValueError, TypeError):
        return None


def get_market_data(
    symbols: list[str],
    period: str = "60d",
    interval: str = "1d",
) -> dict[str, Any]:
    """
    Fetch OHLCV data and compute technical indicators for given symbols.

    Args:
        symbols: List of ticker symbols (e.g., ["AAPL", "MSFT"])
        period: yfinance period (e.g. "60d", "1y") or user-friendly (e.g. "20-day"); normalized internally
        interval: yfinance interval string (default "1d")

    Returns:
        Dict keyed by symbol. Each value is either:
        - A list of dated records with OHLCV + indicators
        - {"error": "..."} if the symbol failed
    """
    period = _normalize_period(period)
    # Check cache
    key = _cache_key(symbols, period, interval)
    now = time.time()
    if key in _cache:
        ts, cached_result = _cache[key]
        if now - ts < _CACHE_TTL:
            logger.info(f"Cache hit for {symbols}")
            return cached_result

    raw_data = _fetch_with_retry(symbols, period, interval)

    result: dict[str, Any] = {}
    for symbol in symbols:
        df = raw_data.get(symbol, pd.DataFrame())
        if df.empty:
            result[symbol] = {"error": f"No data available for {symbol}"}
            continue
        try:
            result[symbol] = _compute_indicators(df)
        except Exception as e:
            logger.error(f"Indicator computation failed for {symbol}: {e}")
            result[symbol] = {"error": f"Indicator computation failed: {str(e)}"}

    # Update cache
    _cache[key] = (now, result)

    return result
