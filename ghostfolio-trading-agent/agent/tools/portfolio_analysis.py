"""Tool: portfolio_analysis — holdings, allocation, and performance for a specific account or all."""

from __future__ import annotations

import logging
from typing import Any

from agent.ghostfolio_client import GhostfolioClient

logger = logging.getLogger(__name__)


def portfolio_analysis(
    account_id: str | None = None,
    client: GhostfolioClient | None = None,
) -> dict[str, Any]:
    """Return holdings, allocation, and performance for a specific account or the full portfolio.

    Args:
        account_id: Ghostfolio account ID to scope the analysis to. Omit for full portfolio.
        client: GhostfolioClient injected by the tools node.
    """
    if client is None:
        client = GhostfolioClient()

    accounts_filter = account_id if account_id else None

    if accounts_filter:
        all_accounts = client.get_accounts()
        known_ids = set()
        if isinstance(all_accounts, list):
            known_ids = {a.get("id") for a in all_accounts if a.get("id")}
        if known_ids and accounts_filter not in known_ids:
            return {"error": f"Account '{accounts_filter}' not found. Known accounts: {sorted(known_ids)}"}

    holdings_data = client.get_holdings(accounts=accounts_filter)
    performance_data = client.get_performance(accounts=accounts_filter)

    errors = []
    if isinstance(holdings_data, dict) and "error" in holdings_data:
        errors.append(f"Holdings: {holdings_data['error']}")
    if isinstance(performance_data, dict) and "error" in performance_data:
        errors.append(f"Performance: {performance_data['error']}")
    if errors:
        return {"error": "; ".join(errors)}

    raw_holdings = []
    if isinstance(holdings_data, dict) and "holdings" in holdings_data:
        raw_holdings = holdings_data["holdings"]
    elif isinstance(holdings_data, list):
        raw_holdings = holdings_data

    holdings = []
    alloc_by_symbol: dict[str, float] = {}
    alloc_by_asset_class: dict[str, float] = {}

    for h in raw_holdings:
        qty = h.get("quantity", 0) or 0
        market_price = h.get("marketPrice", 0) or 0
        value_bc = h.get("valueInBaseCurrency") or h.get("value", 0) or 0
        weight = (h.get("allocationInPercentage", 0) or 0) * 100
        symbol = h.get("symbol", "")
        asset_class = h.get("assetClass", "unknown")

        holdings.append({
            "symbol": symbol,
            "name": h.get("name", ""),
            "quantity": qty,
            "market_price": market_price,
            "value": value_bc,
            "weight_pct": round(weight, 2),
            "performance_pct": h.get("netPerformancePercentage", 0),
            "performance_value": h.get("netPerformance", 0),
            "investment": h.get("investment", 0) or 0,
            "currency": h.get("currency", ""),
            "asset_class": asset_class,
            "sectors": h.get("sectors", []),
        })

        if symbol:
            alloc_by_symbol[symbol] = round(weight, 2)
        alloc_by_asset_class[asset_class] = round(
            alloc_by_asset_class.get(asset_class, 0) + weight, 2
        )

    perf: dict[str, Any] = {}
    if isinstance(performance_data, dict):
        perf_data = performance_data.get("performance", performance_data)
        current_val = (
            perf_data.get("currentValueInBaseCurrency")
            or perf_data.get("currentValue")
            or perf_data.get("currentNetWorth")
            or 0
        )
        perf = {
            "current_value": current_val,
            "net_performance": perf_data.get("netPerformance", 0),
            "net_performance_pct": perf_data.get("netPerformancePercentage", 0),
            "gross_performance": perf_data.get("grossPerformance", 0),
            "total_investment": perf_data.get("totalInvestment", 0),
        }

    total_value = perf.get("current_value", 0)
    if total_value == 0 and holdings:
        total_value = sum(h.get("value", 0) for h in holdings)

    return {
        "holdings": holdings,
        "allocation": {
            "by_symbol": alloc_by_symbol,
            "by_asset_class": alloc_by_asset_class,
        },
        "performance": perf,
        "account_id": account_id,
        "summary": {
            "total_value": total_value,
            "holding_count": len(holdings),
        },
    }
