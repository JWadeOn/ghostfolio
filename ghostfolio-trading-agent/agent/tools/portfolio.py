"""Tool 2: get_portfolio_snapshot — fetch holdings, performance, accounts from Ghostfolio."""

from __future__ import annotations

import logging
from typing import Any

from agent.ghostfolio_client import GhostfolioClient
from agent.tools.market_data import get_latest_prices

logger = logging.getLogger(__name__)

# Ghostfolio uses 1 as placeholder when market data is missing (see portfolio-calculator.ts)
PLACEHOLDER_PRICES = (0, 1)


def _cost_basis_from_activities(activities: list[dict]) -> dict[str, float]:
    """
    Compute cost basis per symbol from order/activity list (BUY/SELL only).
    Uses proportional cost reduction on sells. Returns symbol -> cost_basis for current position.
    """
    by_symbol: dict[str, list[dict]] = {}
    for a in activities:
        sym = a.get("symbol") or (a.get("SymbolProfile") or {}).get("symbol") or ""
        if not sym:
            continue
        t = (a.get("type") or "").upper()
        if t not in ("BUY", "SELL"):
            continue
        by_symbol.setdefault(sym, []).append(a)

    result: dict[str, float] = {}
    for symbol, orders in by_symbol.items():
        orders = sorted(orders, key=lambda o: o.get("date", ""))
        qty = 0.0
        cost_basis = 0.0
        for o in orders:
            order_qty = float(o.get("quantity") or 0)
            unit_price = float(o.get("unitPrice") or 0)
            if order_qty <= 0:
                continue
            if (o.get("type") or "").upper() == "BUY":
                qty += order_qty
                cost_basis += order_qty * unit_price
            else:
                if qty <= 0:
                    continue
                ratio = min(1.0, order_qty / qty)
                cost_basis -= ratio * cost_basis
                qty -= order_qty
        if qty > 0 and cost_basis > 0:
            result[symbol] = round(cost_basis, 2)
    return result


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
        qty = h.get("quantity", 0) or 0
        market_price = h.get("marketPrice", 0) or 0
        value_bc = h.get("valueInBaseCurrency")
        value = value_bc if value_bc is not None else (h.get("value", 0) or h.get("marketValue", 0) or 0)
        holdings.append({
            "symbol": h.get("symbol", ""),
            "name": h.get("name", ""),
            "quantity": qty,
            "currency": h.get("currency", ""),
            "market_price": market_price,
            "value": value,
            "value_in_base_currency": value_bc,
            "investment": h.get("investment", 0) or 0,  # cost basis for this position
            # Ghostfolio returns allocationInPercentage in 0-1 (e.g. 1.0 = 100%); normalize to 0-100 for consistent use in risk and synthesis
            "weight": (h.get("allocationInPercentage", 0) or 0) * 100,
            "performance_pct": h.get("netPerformancePercentage", 0),
            "performance_value": h.get("netPerformance", 0),
            "asset_class": h.get("assetClass", ""),
            "asset_sub_class": h.get("assetSubClass", ""),
            "data_source": h.get("dataSource", ""),
            "sectors": h.get("sectors", []),
        })

    # Enrich with real prices when Ghostfolio returned placeholders (0 or 1)
    symbols_to_fetch = [
        ho["symbol"] for ho in holdings
        if ho["symbol"] and (ho["market_price"] in PLACEHOLDER_PRICES or not ho["market_price"])
    ]
    if symbols_to_fetch:
        try:
            latest_prices = get_latest_prices(symbols_to_fetch)
            for ho in holdings:
                sym = ho["symbol"]
                if sym not in latest_prices:
                    continue
                price = latest_prices[sym]
                ho["market_price"] = price
                qty = ho["quantity"] or 0
                ho["value"] = round(qty * price, 2)
                ho["value_in_base_currency"] = ho["value"]
        except Exception as e:
            logger.warning("Failed to enrich portfolio with latest prices: %s", e)

    # Parse performance (v2 response: { chart, firstOrderDate, performance })
    perf = {}
    if isinstance(performance_data, dict):
        perf_data = performance_data.get("performance", performance_data)
        # v2 uses currentValueInBaseCurrency; support both
        current_val = perf_data.get("currentValueInBaseCurrency") or perf_data.get("currentValue") or perf_data.get("currentNetWorth")
        perf = {
            "current_value": current_val or 0,
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
    if total_value == 0 and holdings:
        total_from_holdings = sum(
            (h.get("value_in_base_currency") or h.get("value") or 0) for h in holdings
        )
        if total_from_holdings > 0:
            total_value = total_from_holdings

    # Total invested = cost basis (sum of what you paid). Prefer performance API, then sum from holdings, then compute from orders/activities.
    cost_basis_source = "none"
    total_invested = perf.get("total_investment", 0)
    if total_invested:
        cost_basis_source = "performance_api"

    if total_invested == 0 and holdings:
        total_invested = sum((h.get("investment") or 0) for h in holdings)
        if total_invested:
            cost_basis_source = "holdings_sum"

    # If still 0, derive from Order table (activities) using unit price data
    if total_invested == 0 and holdings:
        try:
            orders_data = client.get_orders()
            if isinstance(orders_data, dict) and "error" in orders_data:
                pass
            else:
                raw_activities = (
                    orders_data.get("activities", []) if isinstance(orders_data, dict) else
                    (orders_data if isinstance(orders_data, list) else [])
                )
                if raw_activities:
                    cost_by_symbol = _cost_basis_from_activities(raw_activities)
                    for ho in holdings:
                        sym = ho.get("symbol")
                        if sym and sym in cost_by_symbol:
                            ho["investment"] = cost_by_symbol[sym]
                    total_invested = sum(cost_by_symbol.get(h.get("symbol"), 0) for h in holdings)
                    if total_invested:
                        cost_basis_source = "computed_from_orders"
        except Exception as e:
            logger.warning("Failed to compute cost basis from orders: %s", e)

    if total_invested == 0 and holdings:
        logger.warning(
            "Cost basis is 0 for %d holding(s). All 3 sources failed: "
            "performance API totalInvestment=0, holdings investment sum=0, "
            "order-based computation=0. This usually means activities were "
            "created without a valid dataSource (e.g. MANUAL with no price feed).",
            len(holdings),
        )

    return {
        "holdings": holdings,
        "performance": perf,
        "accounts": accounts,
        "summary": {
            "total_value": total_value,
            "total_cash": total_cash,
            "total_invested": total_invested,
            "cost_basis_source": cost_basis_source,
            "net_pnl": perf.get("net_performance", 0),
            "net_pnl_pct": perf.get("net_performance_pct", 0),
            "holding_count": len(holdings),
        },
    }
