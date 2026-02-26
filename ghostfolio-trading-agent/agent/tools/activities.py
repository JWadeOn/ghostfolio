"""Tool: create_activity — record a portfolio activity (trade, dividend, fee, etc.) in Ghostfolio."""

from __future__ import annotations

import logging
from typing import Any

from agent.ghostfolio_client import GhostfolioClient

logger = logging.getLogger(__name__)

VALID_ACTIVITY_TYPES = frozenset({"BUY", "SELL", "DIVIDEND", "FEE", "INTEREST", "LIABILITY"})


def create_activity(
    activity_type: str,
    symbol: str,
    quantity: float,
    unit_price: float,
    currency: str,
    date: str,
    account_id: str | None = None,
    fee: float = 0,
    data_source: str | None = None,
    comment: str | None = None,
    client: GhostfolioClient | None = None,
) -> dict[str, Any]:
    """Record a portfolio activity in Ghostfolio (buy, sell, dividend, fee, etc.).

    Builds a CreateOrderDto payload and calls GhostfolioClient.create_order.
    For "record a trade" flows, the user may first run check_risk and optionally
    get_portfolio_snapshot to obtain account_id when they have multiple accounts.

    Args:
        activity_type: One of BUY, SELL, DIVIDEND, FEE, INTEREST, LIABILITY.
        symbol: Ticker symbol (e.g. "AAPL").
        quantity: Number of shares/units (must be > 0 for BUY/SELL).
        unit_price: Price per unit (>= 0).
        currency: Currency code (e.g. "USD") — required by API.
        date: Trade date as ISO8601 string (e.g. "2025-02-26" or "2025-02-26T12:00:00Z").
        account_id: Optional; required by Ghostfolio if the user has multiple accounts.
        fee: Fee/commission (default 0).
        data_source: Optional; for BUY/SELL stocks, YAHOO is a safe default.
        comment: Optional note.
        client: GhostfolioClient injected by the tools node when token is present.

    Returns:
        Created order object on success, or {"error": "..."} on failure.
    """
    if client is None:
        return {
            "error": "Ghostfolio is not connected. Please connect or link your Ghostfolio account so activities can be recorded."
        }

    activity_type_upper = (activity_type or "").strip().upper()
    if activity_type_upper not in VALID_ACTIVITY_TYPES:
        return {
            "error": f"Invalid activity_type '{activity_type}'. Must be one of: {', '.join(sorted(VALID_ACTIVITY_TYPES))}"
        }

    try:
        qty = float(quantity)
        price = float(unit_price)
        fee_val = float(fee)
    except (TypeError, ValueError):
        return {"error": "quantity, unit_price, and fee must be valid numbers."}

    if qty <= 0:
        return {"error": "quantity must be greater than 0."}
    if price < 0:
        return {"error": "unit_price must be >= 0."}
    if fee_val < 0:
        return {"error": "fee must be >= 0."}

    symbol_str = (symbol or "").strip()
    if not symbol_str:
        return {"error": "symbol is required."}

    currency_str = (currency or "").strip()
    if not currency_str:
        return {"error": "currency is required (e.g. USD)."}

    date_str = (date or "").strip()
    if not date_str:
        return {"error": "date is required (ISO8601, e.g. 2025-02-26)."}

    payload: dict[str, Any] = {
        "currency": currency_str,
        "date": date_str,
        "fee": fee_val,
        "quantity": qty,
        "symbol": symbol_str,
        "type": activity_type_upper,
        "unitPrice": price,
    }
    if account_id:
        payload["accountId"] = account_id.strip()
    if data_source:
        payload["dataSource"] = data_source.strip()
    if comment is not None and str(comment).strip():
        payload["comment"] = str(comment).strip()

    result = client.create_order(payload)
    return result
