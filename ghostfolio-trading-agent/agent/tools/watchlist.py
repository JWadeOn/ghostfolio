"""Tool: add_to_watchlist — add a symbol to the user's Ghostfolio watchlist."""

from __future__ import annotations

import logging
from typing import Any

from agent.ghostfolio_client import GhostfolioClient

logger = logging.getLogger(__name__)

DEFAULT_DATA_SOURCE = "FINANCIAL_MODELING_PREP"


def _resolve_data_source(symbol: str, client: GhostfolioClient) -> str:
    """Look up the symbol in Ghostfolio and return the best data source.

    Falls back to DEFAULT_DATA_SOURCE if the lookup fails or returns no results.
    """
    try:
        result = client.lookup_symbol(symbol)
        items = result.get("items", []) if isinstance(result, dict) else []
        for item in items:
            ds = (item.get("dataSource") or "").strip()
            sym = (item.get("symbol") or "").strip().upper()
            if sym == symbol.strip().upper() and ds:
                logger.info(
                    "Resolved data_source for %s via symbol lookup: %s",
                    symbol,
                    ds,
                )
                return ds
        if items:
            ds = (items[0].get("dataSource") or "").strip()
            if ds:
                logger.info(
                    "Resolved data_source for %s from first lookup match: %s",
                    symbol,
                    ds,
                )
                return ds
    except Exception as e:
        logger.warning("Symbol lookup for data_source resolution failed: %s", e)

    logger.info(
        "Could not resolve data_source for %s; defaulting to %s",
        symbol,
        DEFAULT_DATA_SOURCE,
    )
    return DEFAULT_DATA_SOURCE


def add_to_watchlist(
    symbol: str,
    data_source: str | None = None,
    client: GhostfolioClient | None = None,
) -> dict[str, Any]:
    """Add a symbol to the user's Ghostfolio watchlist.

    Uses POST /api/v1/watchlist. If data_source is not provided, resolves it
    via Ghostfolio symbol lookup (same pattern as create_activity). Ghostfolio
    will create the symbol profile if needed and gather market data.

    Args:
        symbol: Ticker symbol to add (e.g. "AAPL", "MSFT").
        data_source: Optional; Ghostfolio data source (e.g. YAHOO, FINANCIAL_MODELING_PREP).
            Resolved from symbol lookup when omitted.
        client: GhostfolioClient injected by the tools node when token is present.

    Returns:
        Success message or {"error": "..."} on failure.
    """
    if client is None:
        return {
            "error": "Ghostfolio is not connected. Please connect or link your Ghostfolio account to add symbols to your watchlist."
        }

    symbol_str = (symbol or "").strip()
    if not symbol_str:
        return {"error": "symbol is required."}

    symbol_upper = symbol_str.upper()
    resolved_data_source = (data_source or "").strip()
    if not resolved_data_source:
        resolved_data_source = _resolve_data_source(symbol_upper, client)

    result = client.create_watchlist_item(resolved_data_source, symbol_upper)
    if isinstance(result, dict) and result.get("error"):
        return result
    return {
        "success": True,
        "message": f"Added {symbol_upper} to your watchlist.",
        "symbol": symbol_upper,
        "data_source": resolved_data_source,
    }
