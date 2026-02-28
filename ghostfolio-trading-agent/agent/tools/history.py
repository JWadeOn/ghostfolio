"""Tool 6: get_trade_history — fetch orders from Ghostfolio and compute P&L outcomes."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from agent.ghostfolio_client import GhostfolioClient
from agent.tools.market_data import get_market_data, get_latest_prices

logger = logging.getLogger(__name__)


def _parse_time_range(time_range: str) -> datetime | None:
    """Parse a time range string like '90d', '6m', '1y' into a cutoff datetime."""
    now = datetime.now()
    try:
        if time_range.endswith("d"):
            days = int(time_range[:-1])
            return now - timedelta(days=days)
        elif time_range.endswith("m"):
            months = int(time_range[:-1])
            return now - timedelta(days=months * 30)
        elif time_range.endswith("y"):
            years = int(time_range[:-1])
            return now - timedelta(days=years * 365)
    except (ValueError, IndexError):
        pass
    return None


def _symbol_from_order(order: dict) -> str:
    """Resolve symbol from order; API may put it in SymbolProfile/symbolProfile."""
    sym = order.get("symbol") or ""
    if not sym and isinstance(order.get("SymbolProfile"), dict):
        sym = (order["SymbolProfile"] or {}).get("symbol") or ""
    if not sym and isinstance(order.get("symbolProfile"), dict):
        sym = (order.get("symbolProfile") or {}).get("symbol") or ""
    return sym or "UNKNOWN"


def _match_trades(orders: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Match BUY and SELL orders to create trade pairs.
    Returns (closed_trades, open_positions).
    """
    # Group by symbol
    by_symbol: dict[str, list[dict]] = {}
    for order in orders:
        sym = _symbol_from_order(order)
        by_symbol.setdefault(sym, []).append(order)

    closed_trades = []
    open_positions = []

    for symbol, sym_orders in by_symbol.items():
        # Sort by date
        sym_orders.sort(key=lambda o: o.get("date", ""))

        buys = []
        for order in sym_orders:
            order_type = order.get("type", "").upper()
            if order_type == "BUY":
                buys.append(order)
            elif order_type == "SELL" and buys:
                buy = buys.pop(0)  # FIFO matching
                closed_trades.append({
                    "symbol": symbol,
                    "buy_date": buy.get("date", ""),
                    "buy_price": buy.get("unitPrice", 0),
                    "buy_quantity": buy.get("quantity", 0),
                    "sell_date": order.get("date", ""),
                    "sell_price": order.get("unitPrice", 0),
                    "sell_quantity": order.get("quantity", 0),
                })

        # Remaining buys are open positions
        for buy in buys:
            open_positions.append({
                "symbol": symbol,
                "buy_date": buy.get("date", ""),
                "buy_price": buy.get("unitPrice", 0),
                "quantity": buy.get("quantity", 0),
            })

    return closed_trades, open_positions


def get_trade_history(
    time_range: str = "90d",
    symbol: str | None = None,
    strategy_tag: str | None = None,
    include_patterns: bool = False,
    client: GhostfolioClient | None = None,
) -> dict[str, Any]:
    """
    Fetch trade history and compute P&L outcomes.

    Args:
        time_range: Time range string (e.g., "90d", "6m", "1y")
        symbol: Optional filter by symbol
        strategy_tag: Optional filter by strategy tag
        include_patterns: When True, also categorize transactions and detect patterns
            (recurring dividends, DCA, fee clusters). Merges transaction_categorize output.
        client: Optional GhostfolioClient

    Returns:
        Dict with enriched trades list and aggregate statistics.
        When include_patterns=True, also includes 'categories' and 'patterns' keys.
    """
    if client is None:
        client = GhostfolioClient()

    # Fetch orders
    filters = {}
    if symbol:
        filters["symbol"] = symbol
    orders_data = client.get_orders(**filters)

    if isinstance(orders_data, dict) and "error" in orders_data:
        return {"error": orders_data["error"]}

    # Parse orders
    raw_orders = orders_data if isinstance(orders_data, list) else orders_data.get("activities", []) if isinstance(orders_data, dict) else []

    # Filter by time range
    cutoff = _parse_time_range(time_range)
    if cutoff:
        cutoff_str = cutoff.strftime("%Y-%m-%d")
        raw_orders = [o for o in raw_orders if o.get("date", "") >= cutoff_str]

    # Filter by strategy tag
    if strategy_tag:
        raw_orders = [
            o for o in raw_orders
            if strategy_tag in [t.get("name", "") for t in o.get("tags", [])]
        ]

    if not raw_orders:
        return {
            "trades": [],
            "open_positions": [],
            "aggregates": {
                "trade_count": 0, "win_rate": 0, "avg_win": 0, "avg_loss": 0,
                "profit_factor": 0, "total_pnl": 0
            },
            "time_range": time_range,
        }

    closed_trades, open_positions = _match_trades(raw_orders)

    # Enrich closed trades with P&L
    enriched_trades = []
    for trade in closed_trades:
        buy_price = trade["buy_price"]
        sell_price = trade["sell_price"]
        quantity = min(trade["buy_quantity"], trade["sell_quantity"])

        if buy_price > 0:
            pnl_pct = (sell_price - buy_price) / buy_price * 100
            pnl_dollar = (sell_price - buy_price) * quantity
        else:
            pnl_pct = 0
            pnl_dollar = 0

        # Duration
        try:
            buy_dt = datetime.fromisoformat(trade["buy_date"].replace("Z", "+00:00"))
            sell_dt = datetime.fromisoformat(trade["sell_date"].replace("Z", "+00:00"))
            hold_days = (sell_dt - buy_dt).days
        except (ValueError, TypeError):
            hold_days = None

        enriched_trades.append({
            **trade,
            "pnl_pct": round(pnl_pct, 2),
            "pnl_dollar": round(pnl_dollar, 2),
            "hold_days": hold_days,
            "is_winner": pnl_pct > 0,
        })

    # Enrich open positions with current prices (same source as portfolio snapshot:
    # get_latest_prices so "current" price and unrealized P&L are consistent and not stale).
    if open_positions:
        open_symbols = list({p["symbol"] for p in open_positions})
        latest_prices = get_latest_prices(open_symbols)
        for pos in open_positions:
            current_price = latest_prices.get(pos["symbol"])
            if current_price is not None and current_price > 0:
                pos["current_price"] = current_price
                buy_price = pos.get("buy_price") or 0
                qty = pos.get("quantity") or 0
                if buy_price > 0:
                    pos["unrealized_pnl_pct"] = round(
                        (current_price - buy_price) / buy_price * 100, 2
                    )
                    pos["unrealized_pnl_dollar"] = round(
                        (current_price - buy_price) * qty, 2
                    )
                else:
                    pos["unrealized_pnl_pct"] = 0
                    pos["unrealized_pnl_dollar"] = 0
            else:
                # No live price; do not set current_price so agent does not claim "currently at X"
                pos["current_price"] = None
                pos["unrealized_pnl_pct"] = None
                pos["unrealized_pnl_dollar"] = None

    # Compute aggregates
    wins = [t for t in enriched_trades if t["is_winner"]]
    losses = [t for t in enriched_trades if not t["is_winner"]]

    total_wins = sum(t["pnl_dollar"] for t in wins) if wins else 0
    total_losses = abs(sum(t["pnl_dollar"] for t in losses)) if losses else 0

    aggregates = {
        "trade_count": len(enriched_trades),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": round(len(wins) / len(enriched_trades) * 100, 1) if enriched_trades else 0,
        "avg_win": round(total_wins / len(wins), 2) if wins else 0,
        "avg_loss": round(-total_losses / len(losses), 2) if losses else 0,
        "profit_factor": round(total_wins / total_losses, 2) if total_losses > 0 else float("inf") if total_wins > 0 else 0,
        "total_pnl": round(sum(t["pnl_dollar"] for t in enriched_trades), 2),
        "avg_hold_days": round(
            sum(t["hold_days"] for t in enriched_trades if t["hold_days"]) /
            max(1, len([t for t in enriched_trades if t["hold_days"]])),
            1
        ) if enriched_trades else 0,
    }

    result = {
        "trades": enriched_trades,
        "open_positions": open_positions,
        "aggregates": aggregates,
        "time_range": time_range,
    }

    if include_patterns:
        from agent.tools.transaction_categorize import _normalize_activity, _categorize, _detect_patterns
        normalized = [_normalize_activity(o) for o in raw_orders]
        result["categories"] = [_categorize(t) for t in normalized]
        result["patterns"] = _detect_patterns(normalized)

    return result
