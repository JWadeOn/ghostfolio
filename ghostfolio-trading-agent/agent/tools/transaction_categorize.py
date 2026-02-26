"""Tool: transaction_categorize — assign categories and detect patterns in transactions."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from agent.ghostfolio_client import GhostfolioClient

logger = logging.getLogger(__name__)

TYPE_CATEGORY_MAP = {
    "BUY": "Purchase",
    "SELL": "Sale",
    "DIVIDEND": "Dividend",
    "FEE": "Fee",
    "INTEREST": "Interest",
    "LIABILITY": "Liability",
}


def _parse_time_range(time_range: str) -> datetime | None:
    now = datetime.now()
    try:
        if time_range.endswith("d"):
            return now - timedelta(days=int(time_range[:-1]))
        elif time_range.endswith("m"):
            return now - timedelta(days=int(time_range[:-1]) * 30)
        elif time_range.endswith("y"):
            return now - timedelta(days=int(time_range[:-1]) * 365)
    except (ValueError, IndexError):
        pass
    return None


def _normalize_activity(a: dict) -> dict:
    """Normalize a Ghostfolio order/activity into a common shape."""
    profile = a.get("SymbolProfile") or {}
    return {
        "id": a.get("id", ""),
        "type": (a.get("type") or "").upper(),
        "symbol": a.get("symbol") or profile.get("symbol") or "",
        "date": (a.get("date") or "")[:10],
        "quantity": a.get("quantity", 0),
        "unitPrice": a.get("unitPrice", 0),
        "fee": a.get("fee", 0),
        "currency": a.get("currency") or profile.get("currency") or "",
        "accountId": a.get("accountId") or a.get("Account", {}).get("id", ""),
        "comment": a.get("comment", ""),
        "tags": [t.get("name", "") for t in (a.get("tags") or []) if isinstance(t, dict)],
    }


def _categorize(txn: dict) -> dict:
    """Assign category and optional subcategory to a normalized transaction."""
    category = TYPE_CATEGORY_MAP.get(txn["type"], txn["type"])
    subcategory = txn["tags"][0] if txn.get("tags") else None
    return {
        "transaction_id": txn["id"],
        "symbol": txn["symbol"],
        "date": txn["date"],
        "type": txn["type"],
        "category": category,
        "subcategory": subcategory,
    }


def _detect_patterns(txns: list[dict]) -> list[dict]:
    """Simple deterministic pattern detection."""
    patterns: list[dict] = []

    by_sym_type: dict[str, list[dict]] = defaultdict(list)
    for t in txns:
        key = f"{t['symbol']}|{t['type']}"
        by_sym_type[key].append(t)

    # Recurring dividends: same symbol, DIVIDEND, >=2 occurrences
    for key, group in by_sym_type.items():
        sym, ttype = key.split("|", 1)
        if ttype != "DIVIDEND" or len(group) < 2:
            continue
        dates = sorted(t["date"] for t in group if t["date"])
        if len(dates) >= 2:
            intervals = []
            for i in range(1, len(dates)):
                try:
                    d1 = datetime.strptime(dates[i - 1], "%Y-%m-%d")
                    d2 = datetime.strptime(dates[i], "%Y-%m-%d")
                    intervals.append((d2 - d1).days)
                except ValueError:
                    pass
            avg_interval = sum(intervals) / len(intervals) if intervals else 0
            freq = "quarterly" if 60 < avg_interval < 120 else ("monthly" if avg_interval < 45 else "periodic")
            patterns.append({
                "name": "recurring_dividend",
                "description": f"{sym} has {len(group)} dividend payments (~{freq})",
                "transaction_ids": [t["id"] for t in group],
                "metadata": {"symbol": sym, "count": len(group), "avg_interval_days": round(avg_interval, 1), "frequency": freq},
            })

    # DCA: same symbol, BUY, >=3 buys
    for key, group in by_sym_type.items():
        sym, ttype = key.split("|", 1)
        if ttype != "BUY" or len(group) < 3:
            continue
        dates = sorted(t["date"] for t in group if t["date"])
        if len(dates) >= 3:
            intervals = []
            for i in range(1, len(dates)):
                try:
                    d1 = datetime.strptime(dates[i - 1], "%Y-%m-%d")
                    d2 = datetime.strptime(dates[i], "%Y-%m-%d")
                    intervals.append((d2 - d1).days)
                except ValueError:
                    pass
            if intervals:
                avg = sum(intervals) / len(intervals)
                std = (sum((x - avg) ** 2 for x in intervals) / len(intervals)) ** 0.5
                if avg > 0 and std / avg < 0.6:
                    patterns.append({
                        "name": "dca",
                        "description": f"{sym}: {len(group)} regular buys (~every {round(avg)} days)",
                        "transaction_ids": [t["id"] for t in group],
                        "metadata": {"symbol": sym, "count": len(group), "avg_interval_days": round(avg, 1)},
                    })

    # Trading spike: many BUY/SELL within a 7-day window
    trade_txns = [t for t in txns if t["type"] in ("BUY", "SELL") and t["date"]]
    trade_txns.sort(key=lambda t: t["date"])
    if len(trade_txns) >= 5:
        window_days = 7
        for i in range(len(trade_txns)):
            window = [trade_txns[i]]
            for j in range(i + 1, len(trade_txns)):
                try:
                    d1 = datetime.strptime(trade_txns[i]["date"], "%Y-%m-%d")
                    d2 = datetime.strptime(trade_txns[j]["date"], "%Y-%m-%d")
                    if (d2 - d1).days <= window_days:
                        window.append(trade_txns[j])
                    else:
                        break
                except ValueError:
                    break
            if len(window) >= 5:
                patterns.append({
                    "name": "trading_spike",
                    "description": f"{len(window)} trades in a {window_days}-day window starting {trade_txns[i]['date']}",
                    "transaction_ids": [t["id"] for t in window],
                    "metadata": {"start_date": trade_txns[i]["date"], "count": len(window)},
                })
                break  # report one spike

    # High-fee cluster: FEE activities above a threshold
    fee_txns = [t for t in txns if t["type"] == "FEE"]
    if len(fee_txns) >= 3:
        total_fees = sum(t.get("fee", 0) or (t.get("unitPrice", 0) * t.get("quantity", 0)) for t in fee_txns)
        patterns.append({
            "name": "fee_cluster",
            "description": f"{len(fee_txns)} fee transactions totalling ${total_fees:.2f}",
            "transaction_ids": [t["id"] for t in fee_txns],
            "metadata": {"count": len(fee_txns), "total": round(total_fees, 2)},
        })

    return patterns


def transaction_categorize(
    transactions: list[dict] | None = None,
    time_range: str | None = "1y",
    account_id: str | None = None,
    client: GhostfolioClient | None = None,
) -> dict[str, Any]:
    """Categorize transactions and detect patterns (recurring dividends, DCA, fee clusters).

    Args:
        transactions: Pre-fetched transaction list. If empty/None, fetches from Ghostfolio.
        time_range: Lookback period when fetching (e.g. "1y", "90d").
        account_id: Optional account filter when fetching.
        client: GhostfolioClient injected by the tools node.
    """
    if transactions:
        normalized = [_normalize_activity(t) for t in transactions]
    else:
        if client is None:
            return {"error": "No transactions provided and Ghostfolio is not connected."}
        params: dict[str, str] = {}
        if account_id:
            params["accounts"] = account_id
        orders_data = client.get_orders(**params)
        if isinstance(orders_data, dict) and "error" in orders_data:
            return {"error": orders_data["error"]}

        raw = (
            orders_data.get("activities", [])
            if isinstance(orders_data, dict) and "activities" in orders_data
            else (orders_data if isinstance(orders_data, list) else [])
        )
        normalized = [_normalize_activity(a) for a in raw]

        cutoff = _parse_time_range(time_range or "1y")
        if cutoff:
            cutoff_str = cutoff.strftime("%Y-%m-%d")
            normalized = [t for t in normalized if t["date"] >= cutoff_str]

    categories = [_categorize(t) for t in normalized]
    patterns = _detect_patterns(normalized)

    return {
        "categories": categories,
        "patterns": patterns,
    }
