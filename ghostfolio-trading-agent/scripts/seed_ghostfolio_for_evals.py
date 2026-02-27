#!/usr/bin/env python3
"""Seed a live Ghostfolio instance with the Phase 1 eval mock dataset.

Use this so you can run evals against a deployed instance (e.g. Railway) with
predictable portfolio data. The seeded state matches tests/mocks/ghostfolio_responses.py
(AAPL and GOOG holdings from two BUY activities).

Usage:
  From ghostfolio-trading-agent directory:
    python scripts/seed_ghostfolio_for_evals.py

  Or with explicit env (e.g. for Railway):
    GHOSTFOLIO_API_URL=https://your-ghostfolio.up.railway.app \\
    GHOSTFOLIO_ACCESS_TOKEN=your-security-token \\
    python scripts/seed_ghostfolio_for_evals.py

Requirements:
  - GHOSTFOLIO_API_URL and GHOSTFOLIO_ACCESS_TOKEN must be set (or in .env).
  - The token must have createOrder, deleteOrder, and createWatchlistItem permissions
    (and createAccount if no account exists yet; the script creates a DEMO account when needed).

After seeding, run evals against the live instance:
  EVAL_USE_MOCKS=0 python tests/eval/run_evals.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

# Project root = ghostfolio-trading-agent
_SCRIPT_DIR = Path(__file__).resolve().parent
_AGENT_ROOT = _SCRIPT_DIR.parent
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))

from agent.ghostfolio_client import GhostfolioClient
from agent.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MOCK_DATASET_PATH = _AGENT_ROOT / "tests" / "eval" / "mock_dataset.json"


def load_mock_dataset() -> dict:
    """Load the Phase 1 mock dataset JSON."""
    if not MOCK_DATASET_PATH.is_file():
        raise FileNotFoundError(f"Mock dataset not found: {MOCK_DATASET_PATH}")
    with open(MOCK_DATASET_PATH, encoding="utf-8") as f:
        return json.load(f)


def build_order_payload(activity: dict, account_id: str | None) -> dict:
    """Build CreateOrderDto-shaped payload for POST /api/v1/order."""
    payload = {
        "symbol": activity["symbol"],
        "type": activity["type"],
        "date": activity["date"],
        "quantity": float(activity["quantity"]),
        "unitPrice": float(activity["unitPrice"]),
        "currency": activity["currency"],
        "fee": float(activity.get("fee", 0)),
    }
    if account_id:
        payload["accountId"] = account_id
    payload["dataSource"] = activity.get("dataSource") or "MANUAL"
    if activity.get("comment"):
        payload["comment"] = activity["comment"]
    return payload


def _build_manual_fallback_activities(activities: list[dict]) -> list[dict]:
    """Build one BUY per symbol with net quantity (for MANUAL fallback when YAHOO fails)."""
    net: dict[str, float] = {}
    first_buy: dict[str, dict] = {}  # symbol -> first BUY activity (for date, unitPrice, etc.)
    for a in activities:
        sym = (a.get("symbol") or "").strip()
        if not sym:
            continue
        qty = float(a.get("quantity", 0))
        typ = (a.get("type") or "").upper()
        if typ == "BUY":
            net[sym] = net.get(sym, 0) + qty
            if sym not in first_buy:
                first_buy[sym] = dict(a)
        elif typ == "SELL":
            net[sym] = net.get(sym, 0) - qty
    out = []
    for sym, qty in net.items():
        if qty <= 0:
            continue
        base = first_buy.get(sym) or {}
        out.append({
            "symbol": sym,
            "type": "BUY",
            "quantity": qty,
            "unitPrice": float(base.get("unitPrice", 0)) or 1,
            "date": base.get("date", "2026-02-23"),
            "currency": base.get("currency", "USD"),
            "fee": float(base.get("fee", 0)),
            "dataSource": "MANUAL",
            "comment": "eval seed (MANUAL fallback)",
        })
    return out


def main() -> int:
    settings = get_settings()
    url = (os.environ.get("GHOSTFOLIO_API_URL") or settings.ghostfolio_api_url or "").strip()
    token = (os.environ.get("GHOSTFOLIO_ACCESS_TOKEN") or settings.ghostfolio_access_token or "").strip()
    if not url or not token:
        logger.error(
            "Set GHOSTFOLIO_API_URL and GHOSTFOLIO_ACCESS_TOKEN (or add them to .env)."
        )
        return 1

    data = load_mock_dataset()
    activities = data.get("activities", [])
    if not activities:
        logger.error("Mock dataset has no activities.")
        return 1

    client = GhostfolioClient(base_url=url, access_token=token)
    try:
        if not client.access_token:
            logger.error("Failed to obtain JWT (check GHOSTFOLIO_ACCESS_TOKEN).")
            return 1

        # Use first existing account, or create a DEMO account if none exist
        account_id: str | None = None
        accounts_res = client.get_accounts()
        accounts = (
            accounts_res.get("accounts", [])
            if isinstance(accounts_res, dict)
            else (accounts_res if isinstance(accounts_res, list) else [])
        )
        if accounts and len(accounts) > 0:
            first = accounts[0]
            if isinstance(first, dict) and first.get("id"):
                account_id = first["id"]
                logger.info("Using account: %s", first.get("name", account_id))
        if not account_id:
            logger.info("No account found; creating DEMO account...")
            create_res = client.create_account(name="DEMO", currency="USD", balance=0)
            if isinstance(create_res, dict) and create_res.get("error"):
                logger.error("Create account failed: %s", create_res["error"])
                return 1
            account_id = create_res.get("id") if isinstance(create_res, dict) else None
            if not account_id:
                logger.error("Create account did not return an id.")
                return 1
            logger.info("Created account DEMO (%s).", account_id)

        # Clear existing orders so seed state is deterministic
        logger.info("Deleting existing orders...")
        deleted = client.delete_orders()
        if isinstance(deleted, dict) and "error" in deleted:
            logger.error("Delete orders failed: %s", deleted["error"])
            return 1
        logger.info("Deleted %s existing order(s).", deleted)

        # Create seed activities
        created = 0
        for i, act in enumerate(activities):
            payload = build_order_payload(act, account_id)
            result = client.create_order(payload)
            if isinstance(result, dict) and result.get("error"):
                logger.error("Create order %d failed: %s", i + 1, result["error"])
                continue
            created += 1
            logger.info("Created: %s %s %s @ %s", act["type"], act["quantity"], act["symbol"], act["unitPrice"])

        # If YAHOO (or other) validation failed, fall back to MANUAL: one BUY per symbol with net quantity
        use_manual = any(
            (a.get("dataSource") or "MANUAL").upper() == "MANUAL"
            for a in activities
        )
        expected_count = len(activities)
        used_fallback = False
        if created < len(activities):
            fallback = _build_manual_fallback_activities(activities)
            if fallback:
                logger.info(
                    "Some orders failed (e.g. YAHOO not configured). Re-seeding with MANUAL (one BUY per symbol, net quantity)."
                )
                deleted = client.delete_orders()
                if isinstance(deleted, dict) and "error" in deleted:
                    logger.error("Delete orders (for fallback) failed: %s", deleted["error"])
                else:
                    created = 0
                    for i, act in enumerate(fallback):
                        payload = build_order_payload(act, account_id)
                        result = client.create_order(payload)
                        if isinstance(result, dict) and result.get("error"):
                            logger.error("Fallback order %d failed: %s", i + 1, result["error"])
                            continue
                        created += 1
                        logger.info("Created: %s %s %s @ %s", act["type"], act["quantity"], act["symbol"], act["unitPrice"])
                    use_manual = True  # skip watchlist after MANUAL fallback
                    used_fallback = True
                    expected_count = len(fallback)

        # Add watchlist items only when not using MANUAL (Ghostfolio stores MANUAL
        # profiles with UUID symbols, so watchlist lookup by dataSource+symbol returns 500)
        watchlist = data.get("watchlist", [])
        if watchlist and not use_manual:
            for item in watchlist:
                ds = item.get("dataSource") or "MANUAL"
                sym = item.get("symbol")
                if not sym:
                    continue
                res = client.create_watchlist_item(ds, sym)
                if isinstance(res, dict) and res.get("error"):
                    logger.warning("Watchlist add %s (%s) failed: %s", sym, ds, res.get("error"))
                else:
                    logger.info("Added to watchlist: %s (%s)", sym, ds)
        elif watchlist and use_manual:
            logger.info("Skipping watchlist (MANUAL data source: Ghostfolio uses UUID symbols).")

        logger.info("Seed complete. Created %d activity(ies). Run evals with EVAL_USE_MOCKS=0.", created)
        return 0 if created == expected_count else 1
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
