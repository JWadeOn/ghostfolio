"""Tool 4: scan_strategies — run strategy scans against a universe of symbols."""

from __future__ import annotations

import logging
from typing import Any

from agent.tools.market_data import get_market_data
from agent.strategies.vcp_breakout import VCPBreakoutStrategy
from agent.strategies.mean_reversion import MeanReversionStrategy
from agent.strategies.momentum import MomentumStrategy

logger = logging.getLogger(__name__)

# All available strategies
ALL_STRATEGIES = [
    VCPBreakoutStrategy(),
    MeanReversionStrategy(),
    MomentumStrategy(),
]

# Default scan universe when no watchlist is provided
DEFAULT_UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    "AMD", "CRM", "NFLX", "AVGO", "ADBE", "ORCL", "INTC",
    "JPM", "V", "MA", "BAC", "GS", "UNH",
]


def scan_strategies(
    symbols: list[str] | None = None,
    strategy_names: list[str] | None = None,
    regime: dict | None = None,
) -> dict[str, Any]:
    """
    Scan a universe of symbols with active strategies.

    Args:
        symbols: List of symbols to scan. Defaults to DEFAULT_UNIVERSE.
        strategy_names: Filter to specific strategies. None = all.
        regime: Current regime dict (used to filter regime-aligned strategies).

    Returns:
        Dict with opportunities list sorted by score, plus scan metadata.
    """
    if not symbols:
        symbols = DEFAULT_UNIVERSE

    # Select strategies
    active_strategies = ALL_STRATEGIES
    if strategy_names:
        active_strategies = [s for s in ALL_STRATEGIES if s.name in strategy_names]

    if not active_strategies:
        return {"error": f"No matching strategies for: {strategy_names}",
                "available": [s.name for s in ALL_STRATEGIES]}

    # Optionally filter by regime alignment
    if regime and "composite" in regime:
        composite = regime["composite"]
        regime_aligned = [s for s in active_strategies if composite in s.favorable_regimes]
        if regime_aligned:
            active_strategies = regime_aligned

    # Fetch market data for all symbols at once (leverages caching)
    data = get_market_data(symbols, period="120d", interval="1d")

    opportunities = []
    errors = []

    for symbol in symbols:
        symbol_data = data.get(symbol, {})
        if isinstance(symbol_data, dict) and "error" in symbol_data:
            errors.append({"symbol": symbol, "error": symbol_data["error"]})
            continue

        if not isinstance(symbol_data, list):
            continue

        for strategy in active_strategies:
            try:
                result = strategy.scan(symbol, symbol_data)
                if result:
                    opportunities.append(result)
            except Exception as e:
                logger.error(f"Strategy {strategy.name} failed on {symbol}: {e}")

    # Sort by score descending
    opportunities.sort(key=lambda x: x.get("score", 0), reverse=True)

    return {
        "opportunities": opportunities,
        "scanned": len(symbols),
        "strategies_used": [s.name for s in active_strategies],
        "matches": len(opportunities),
        "errors": errors if errors else None,
    }
