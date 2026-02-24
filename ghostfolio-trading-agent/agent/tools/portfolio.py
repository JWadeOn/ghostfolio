"""Tool 2: get_portfolio_snapshot — fetch holdings, performance, accounts from Ghostfolio."""

from __future__ import annotations

import logging
from typing import Any

from agent.ghostfolio_client import GhostfolioClient

logger = logging.getLogger(__name__)


def get_portfolio_snapshot(client: GhostfolioClient | None = None) -> dict[str, Any]:
    """
    Get a combined portfolio snapshot: holdings + performance + accounts.

    Returns a structured dict with:
    - holdings: list of positions with symbol, quantity, value, weight, performance
    - performance: overall P&L, gross/net returns, current value
    - accounts: list of accounts with cash balances
    - summary: total value, cash, invested, P&L
    """
    if client is None:
        client = GhostfolioClient()

    holdings_data = client.get_holdings()
    performance_data = client.get_performance()
    accounts_data = client.get_accounts()

    # Check for errors
    errors = []
    if isinstance(holdings_data, dict) and "error" in holdings_data:
        errors.append(f"Holdings: {holdings_data['error']}")
    if isinstance(performance_data, dict) and "error" in performance_data:
        errors.append(f"Performance: {performance_data['error']}")
    if isinstance(accounts_data, dict) and "error" in accounts_data:
        errors.append(f"Accounts: {accounts_data['error']}")

    if errors:
        return {"error": "; ".join(errors), "partial": True}

    # Parse holdings
    holdings = []
    if isinstance(holdings_data, dict) and "holdings" in holdings_data:
        raw_holdings = holdings_data["holdings"]
    elif isinstance(holdings_data, list):
        raw_holdings = holdings_data
    else:
        raw_holdings = []

    for h in raw_holdings:
        holdings.append({
            "symbol": h.get("symbol", ""),
            "name": h.get("name", ""),
            "quantity": h.get("quantity", 0),
            "currency": h.get("currency", ""),
            "market_price": h.get("marketPrice", 0),
            "value": h.get("value", 0) or h.get("marketValue", 0),
            "weight": h.get("allocationInPercentage", 0),
            "performance_pct": h.get("netPerformancePercentage", 0),
            "performance_value": h.get("netPerformance", 0),
            "asset_class": h.get("assetClass", ""),
            "asset_sub_class": h.get("assetSubClass", ""),
            "data_source": h.get("dataSource", ""),
            "sectors": h.get("sectors", []),
        })

    # Parse performance
    perf = {}
    if isinstance(performance_data, dict):
        chart = performance_data.get("chart", [])
        perf_data = performance_data.get("performance", performance_data)
        perf = {
            "current_value": perf_data.get("currentValue", 0),
            "net_performance": perf_data.get("netPerformance", 0),
            "net_performance_pct": perf_data.get("netPerformancePercentage", 0),
            "gross_performance": perf_data.get("grossPerformance", 0),
            "total_investment": perf_data.get("totalInvestment", 0),
        }

    # Parse accounts
    accounts = []
    raw_accounts = accounts_data if isinstance(accounts_data, list) else []
    total_cash = 0
    for a in raw_accounts:
        balance = a.get("balance", 0)
        total_cash += balance
        accounts.append({
            "id": a.get("id", ""),
            "name": a.get("name", ""),
            "balance": balance,
            "currency": a.get("currency", ""),
            "platform": a.get("platform", {}).get("name", "") if a.get("platform") else "",
            "value": a.get("value", 0),
        })

    total_value = perf.get("current_value", 0)

    return {
        "holdings": holdings,
        "performance": perf,
        "accounts": accounts,
        "summary": {
            "total_value": total_value,
            "total_cash": total_cash,
            "total_invested": perf.get("total_investment", 0),
            "net_pnl": perf.get("net_performance", 0),
            "net_pnl_pct": perf.get("net_performance_pct", 0),
            "holding_count": len(holdings),
        },
    }
