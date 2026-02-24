"""Tool 3: detect_regime — rules-based market regime classification across 5 dimensions."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from agent.tools.market_data import get_market_data

logger = logging.getLogger(__name__)

SECTOR_ETFS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLP", "XLU", "XLRE", "XLY"]
RISK_ON_SECTORS = {"XLK", "XLY", "XLI"}  # tech, discretionary, industrials
RISK_OFF_SECTORS = {"XLU", "XLP", "XLV"}  # utilities, staples, healthcare


def _classify_trend(spy_data: list[dict]) -> dict[str, Any]:
    """Classify trend using SPY price vs SMAs and slope of SMA(20)."""
    if not spy_data or len(spy_data) < 10:
        return {"classification": "unknown", "details": {}}

    latest = spy_data[-1]
    price = latest["close"]
    sma_50 = latest.get("sma_50")
    sma_200 = latest.get("sma_200")
    sma_20_now = latest.get("sma_20")

    # Compute slope of SMA(20) over last 10 days
    sma_20_10ago = None
    if len(spy_data) >= 11:
        sma_20_10ago = spy_data[-11].get("sma_20")

    slope = None
    if sma_20_now and sma_20_10ago and sma_20_10ago != 0:
        slope = (sma_20_now - sma_20_10ago) / sma_20_10ago * 100

    classification = "ranging"
    if price and sma_50 and sma_200:
        if price > sma_50 > sma_200 and slope is not None and slope > 0:
            classification = "trending_up"
        elif price < sma_50 < sma_200 and slope is not None and slope < 0:
            classification = "trending_down"

    return {
        "classification": classification,
        "details": {
            "price": price,
            "sma_50": sma_50,
            "sma_200": sma_200,
            "sma_20_slope_pct": round(slope, 3) if slope else None,
        },
    }


def _classify_volatility(spy_data: list[dict], vix_data: list[dict]) -> dict[str, Any]:
    """Classify volatility using VIX level and ATR expansion/contraction."""
    if not vix_data or not spy_data:
        return {"classification": "unknown", "details": {}}

    vix_closes = [d["close"] for d in vix_data if d.get("close") is not None]
    vix_current = vix_closes[-1] if vix_closes else None

    # VIX 20-day percentile
    vix_recent = vix_closes[-20:] if len(vix_closes) >= 20 else vix_closes
    vix_percentile = None
    if vix_current and len(vix_recent) > 1:
        vix_percentile = sum(1 for v in vix_recent if v <= vix_current) / len(vix_recent) * 100

    # VIX trend (rising or falling)
    vix_rising = len(vix_closes) >= 5 and vix_closes[-1] > vix_closes[-5]

    # ATR analysis
    atr_current = spy_data[-1].get("atr_14")
    atr_values = [d.get("atr_14") for d in spy_data[-20:] if d.get("atr_14") is not None]
    atr_avg = np.mean(atr_values) if atr_values else None
    atr_expanding = atr_current and atr_avg and atr_current > atr_avg

    classification = "low_vol"
    if vix_current is not None:
        if vix_current < 16 and not atr_expanding:
            classification = "low_vol"
        elif vix_rising and atr_expanding:
            classification = "rising_vol"
        elif vix_current > 25 and atr_expanding:
            classification = "high_vol"
        elif not vix_rising and not atr_expanding:
            classification = "falling_vol"
        else:
            classification = "rising_vol" if vix_rising else "low_vol"

    return {
        "classification": classification,
        "details": {
            "vix": vix_current,
            "vix_percentile": round(vix_percentile, 1) if vix_percentile else None,
            "vix_rising": vix_rising,
            "atr_current": atr_current,
            "atr_20d_avg": round(atr_avg, 4) if atr_avg else None,
            "atr_expanding": atr_expanding,
        },
    }


def _classify_correlation(sector_data: dict[str, list[dict]]) -> dict[str, Any]:
    """Compute average pairwise 20-day correlation between sector ETFs."""
    # Build a DataFrame of closes
    closes = {}
    for symbol, records in sector_data.items():
        if isinstance(records, list) and len(records) >= 20:
            closes[symbol] = {r["date"]: r["close"] for r in records if r.get("close")}

    if len(closes) < 3:
        return {"classification": "unknown", "details": {}}

    try:
        df = pd.DataFrame(closes).dropna()
        if len(df) < 20:
            return {"classification": "unknown", "details": {}}

        # Use last 20 rows for correlation
        df_recent = df.tail(20)
        returns = df_recent.pct_change().dropna()
        if returns.empty:
            return {"classification": "unknown", "details": {}}

        # Drop constant columns to avoid singular matrix / SIGFPE in correlation
        const_cols = returns.columns[returns.std() <= 0].tolist()
        if const_cols:
            returns = returns.drop(columns=const_cols)
        if returns.shape[1] < 2:
            return {"classification": "unknown", "details": {}}

        corr_matrix = returns.corr()
        # Average of upper triangle (excluding diagonal)
        mask = np.triu(np.ones_like(corr_matrix, dtype=bool), k=1)
        avg_corr = corr_matrix.where(mask).stack().mean()

        if avg_corr > 0.75:
            classification = "high_correlation"
        elif avg_corr > 0.5:
            classification = "moderate"
        else:
            classification = "low_correlation"

        return {
            "classification": classification,
            "details": {"avg_pairwise_correlation": round(float(avg_corr), 3)},
        }
    except Exception as e:
        logger.warning(f"Correlation classification failed: {e}")
        return {"classification": "unknown", "details": {"error": str(e)}}


def _classify_breadth(sector_data: dict[str, list[dict]]) -> dict[str, Any]:
    """Count how many sector ETFs are above their 20 SMA."""
    above_count = 0
    total = 0
    sector_status = {}

    for symbol, records in sector_data.items():
        if not isinstance(records, list) or not records:
            continue
        latest = records[-1]
        price = latest.get("close")
        sma_20 = latest.get("sma_20")
        if price is not None and sma_20 is not None:
            total += 1
            above = price > sma_20
            if above:
                above_count += 1
            sector_status[symbol] = {"above_sma20": above, "price": price, "sma_20": sma_20}

    if total == 0:
        return {"classification": "unknown", "details": {}}

    if above_count >= 7:
        classification = "broad_participation"
    elif above_count >= 4:
        classification = "moderate"
    else:
        classification = "narrow_leadership"

    return {
        "classification": classification,
        "details": {
            "above_sma20": above_count,
            "total": total,
            "ratio": f"{above_count}/{total}",
            "sectors": sector_status,
        },
    }


def _classify_rotation(sector_data: dict[str, list[dict]]) -> dict[str, Any]:
    """Identify sector rotation by 1-week and 4-week returns."""
    returns_1w = {}
    returns_4w = {}

    for symbol, records in sector_data.items():
        if not isinstance(records, list) or len(records) < 20:
            continue
        current = records[-1].get("close")
        week_ago = records[-5].get("close") if len(records) >= 5 else None
        month_ago = records[-20].get("close") if len(records) >= 20 else None

        if current and week_ago and week_ago > 0:
            returns_1w[symbol] = (current - week_ago) / week_ago * 100
        if current and month_ago and month_ago > 0:
            returns_4w[symbol] = (current - month_ago) / month_ago * 100

    if not returns_1w:
        return {"classification": "unknown", "details": {}}

    # Sort by combined rank
    combined = {}
    for sym in returns_1w:
        combined[sym] = returns_1w.get(sym, 0) + returns_4w.get(sym, 0)

    sorted_sectors = sorted(combined.items(), key=lambda x: x[1], reverse=True)
    top_3 = {s[0] for s in sorted_sectors[:3]}
    bottom_3 = {s[0] for s in sorted_sectors[-3:]}

    # Classify
    risk_on_leading = len(top_3 & RISK_ON_SECTORS) >= 2
    risk_off_leading = len(top_3 & RISK_OFF_SECTORS) >= 2

    if risk_on_leading:
        classification = "risk_on"
    elif risk_off_leading:
        classification = "risk_off"
    else:
        classification = "mixed"

    return {
        "classification": classification,
        "details": {
            "top_3": [{"symbol": s, "return_1w": round(returns_1w.get(s, 0), 2),
                        "return_4w": round(returns_4w.get(s, 0), 2)} for s, _ in sorted_sectors[:3]],
            "bottom_3": [{"symbol": s, "return_1w": round(returns_1w.get(s, 0), 2),
                          "return_4w": round(returns_4w.get(s, 0), 2)} for s, _ in sorted_sectors[-3:]],
        },
    }


def _compute_composite(dimensions: dict) -> tuple[str, int]:
    """Compute a composite regime label and confidence score (0-100)."""
    trend = dimensions["trend"]["classification"]
    volatility = dimensions["volatility"]["classification"]
    breadth = dimensions["breadth"]["classification"]
    rotation = dimensions["rotation"]["classification"]
    correlation = dimensions["correlation"]["classification"]

    # Confidence: how many dimensions give clear (non-borderline) signals
    clear_signals = 0
    total_dims = 5

    if trend in ("trending_up", "trending_down"):
        clear_signals += 1
    if volatility in ("low_vol", "high_vol"):
        clear_signals += 1
    if breadth in ("broad_participation", "narrow_leadership"):
        clear_signals += 1
    if rotation in ("risk_on", "risk_off"):
        clear_signals += 1
    if correlation in ("high_correlation", "low_correlation"):
        clear_signals += 1

    confidence = int(clear_signals / total_dims * 100)

    # Composite label
    if trend == "trending_up" and volatility in ("low_vol", "falling_vol") and breadth == "broad_participation":
        composite = "bullish_expansion"
    elif trend == "trending_down" and volatility in ("high_vol", "rising_vol"):
        composite = "bearish_contraction"
    elif trend == "trending_up" and breadth == "narrow_leadership":
        composite = "selective_bull"
    elif volatility == "high_vol" and correlation == "high_correlation":
        composite = "risk_off_panic"
    elif trend == "ranging" and volatility == "low_vol":
        composite = "quiet_consolidation"
    else:
        composite = "transitional"

    return composite, confidence


def detect_regime(index: str = "SPY") -> dict[str, Any]:
    """
    Detect the current market regime across 5 dimensions.

    Args:
        index: Base index symbol (default "SPY")

    Returns:
        RegimeClassification dict with trend, volatility, correlation,
        breadth, rotation, composite label, confidence, and timestamp.
    """
    # Fetch all needed data
    all_symbols = [index, "^VIX"] + SECTOR_ETFS
    data = get_market_data(all_symbols, period="120d", interval="1d")

    spy_data = data.get(index, [])
    vix_data = data.get("^VIX", [])

    # Check for errors
    if isinstance(spy_data, dict) and "error" in spy_data:
        return {"error": f"Failed to fetch {index}: {spy_data['error']}"}

    sector_data = {sym: data.get(sym, []) for sym in SECTOR_ETFS}

    # Classify each dimension
    trend = _classify_trend(spy_data if isinstance(spy_data, list) else [])
    volatility = _classify_volatility(
        spy_data if isinstance(spy_data, list) else [],
        vix_data if isinstance(vix_data, list) else [],
    )
    correlation = _classify_correlation(sector_data)
    breadth = _classify_breadth(sector_data)
    rotation = _classify_rotation(sector_data)

    dimensions = {
        "trend": trend,
        "volatility": volatility,
        "correlation": correlation,
        "breadth": breadth,
        "rotation": rotation,
    }

    composite, confidence = _compute_composite(dimensions)

    return {
        "composite": composite,
        "confidence": confidence,
        "dimensions": dimensions,
        "index": index,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
