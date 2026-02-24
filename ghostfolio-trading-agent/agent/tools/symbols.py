"""Tool 7: lookup_symbol — resolve symbol queries via Ghostfolio's symbol search."""

from __future__ import annotations

import logging
from typing import Any

from agent.ghostfolio_client import GhostfolioClient

logger = logging.getLogger(__name__)


def lookup_symbol(
    query: str, client: GhostfolioClient | None = None
) -> dict[str, Any]:
    """
    Look up a symbol using Ghostfolio's symbol search.

    Args:
        query: Search query (e.g., "AAPL", "Apple", "Tesla")

    Returns:
        Dict with matches list, each containing symbol, name, data_source, etc.
    """
    if client is None:
        client = GhostfolioClient()

    result = client.lookup_symbol(query)

    if isinstance(result, dict) and "error" in result:
        return result

    # Parse the lookup response
    items = []
    raw_items = result.get("items", []) if isinstance(result, dict) else result if isinstance(result, list) else []

    for item in raw_items:
        items.append({
            "symbol": item.get("symbol", ""),
            "name": item.get("name", ""),
            "currency": item.get("currency", ""),
            "data_source": item.get("dataSource", ""),
            "asset_class": item.get("assetClass", ""),
            "asset_sub_class": item.get("assetSubClass", ""),
        })

    return {
        "query": query,
        "matches": items,
        "count": len(items),
    }
