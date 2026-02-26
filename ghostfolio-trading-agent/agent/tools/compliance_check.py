"""Tool: compliance_check — regulatory and tax law compliance checks.

This is NOT a portfolio risk tool. Portfolio guardrails (position limits,
concentration, pattern day trader, min notional) are handled by
portfolio_guardrails_check and trade_guardrails_check.

compliance_check answers: "Does this transaction comply with the requested
regulations (wash sale, capital gains classification, tax-loss harvesting)?"
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Callable

from agent.ghostfolio_client import GhostfolioClient

logger = logging.getLogger(__name__)

WASH_SALE_WINDOW_DAYS = 30
LONG_TERM_DAYS = 365


def _get_recent_orders(symbol: str, client: GhostfolioClient, days: int = 60) -> list[dict]:
    """Fetch recent orders for a symbol from Ghostfolio."""
    try:
        data = client.get_orders(symbol=symbol)
        raw = (
            data.get("activities", [])
            if isinstance(data, dict) and "activities" in data
            else (data if isinstance(data, list) else [])
        )
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        return [
            o for o in raw
            if (o.get("date") or "")[:10] >= cutoff
        ]
    except Exception as e:
        logger.warning("Failed to fetch orders for %s: %s", symbol, e)
        return []


def _get_all_orders(symbol: str, client: GhostfolioClient) -> list[dict]:
    """Fetch all orders for a symbol (needed for hold period / cost basis)."""
    try:
        data = client.get_orders(symbol=symbol)
        raw = (
            data.get("activities", [])
            if isinstance(data, dict) and "activities" in data
            else (data if isinstance(data, list) else [])
        )
        return raw
    except Exception as e:
        logger.warning("Failed to fetch orders for %s: %s", symbol, e)
        return []


# ---------------------------------------------------------------------------
# Regulation implementations
# ---------------------------------------------------------------------------

def _check_wash_sale(transaction: dict, context: dict) -> list[dict]:
    """IRC §1091: buying the same symbol within 30 days of a loss sale."""
    results: list[dict] = []
    txn_type = (transaction.get("type") or "").upper()
    txn_symbol = (transaction.get("symbol") or "").upper()
    txn_date_str = (transaction.get("date") or "")[:10]

    if not txn_symbol or not txn_date_str:
        return results

    try:
        txn_date = datetime.strptime(txn_date_str, "%Y-%m-%d")
    except ValueError:
        return results

    recent_orders = context.get("recent_orders", [])

    if txn_type == "BUY":
        for o in recent_orders:
            if (o.get("type") or "").upper() != "SELL":
                continue
            o_symbol = (o.get("symbol") or (o.get("SymbolProfile") or {}).get("symbol") or "").upper()
            if o_symbol != txn_symbol:
                continue
            o_date_str = (o.get("date") or "")[:10]
            try:
                o_date = datetime.strptime(o_date_str, "%Y-%m-%d")
            except ValueError:
                continue
            days_diff = abs((txn_date - o_date).days)
            if days_diff > WASH_SALE_WINDOW_DAYS:
                continue
            unit_price = o.get("unitPrice", 0) or 0
            cost_per_share = context.get("avg_cost_per_share", unit_price)
            if unit_price > 0 and unit_price < cost_per_share:
                results.append({
                    "rule": "wash_sale",
                    "severity": "violation",
                    "message": (
                        f"Potential wash sale: buying {txn_symbol} within {WASH_SALE_WINDOW_DAYS} days "
                        f"of a loss sale on {o_date_str} (sold at ${unit_price:.2f}, "
                        f"cost basis ~${cost_per_share:.2f}). "
                        f"IRC §1091 may disallow the loss deduction."
                    ),
                })

    elif txn_type == "SELL":
        txn_price = transaction.get("unitPrice", 0) or 0
        cost_per_share = context.get("avg_cost_per_share", txn_price)
        if txn_price > 0 and txn_price < cost_per_share:
            results.append({
                "rule": "wash_sale",
                "severity": "warning",
                "message": (
                    f"Selling {txn_symbol} at a loss (${txn_price:.2f} vs cost ~${cost_per_share:.2f}). "
                    f"If you repurchase within {WASH_SALE_WINDOW_DAYS} days, the loss may be "
                    f"disallowed under IRC §1091 (wash sale rule)."
                ),
            })

    return results


def _check_capital_gains(transaction: dict, context: dict) -> list[dict]:
    """Classify as short-term vs long-term capital gain based on hold period."""
    results: list[dict] = []
    txn_type = (transaction.get("type") or "").upper()
    if txn_type != "SELL":
        return results

    txn_symbol = (transaction.get("symbol") or "").upper()
    txn_date_str = (transaction.get("date") or "")[:10]
    if not txn_symbol or not txn_date_str:
        return results

    try:
        txn_date = datetime.strptime(txn_date_str, "%Y-%m-%d")
    except ValueError:
        return results

    all_orders = context.get("all_orders", [])
    buy_dates = []
    for o in all_orders:
        if (o.get("type") or "").upper() != "BUY":
            continue
        o_symbol = (o.get("symbol") or (o.get("SymbolProfile") or {}).get("symbol") or "").upper()
        if o_symbol != txn_symbol:
            continue
        o_date_str = (o.get("date") or "")[:10]
        if o_date_str:
            buy_dates.append(o_date_str)

    if not buy_dates:
        results.append({
            "rule": "capital_gains",
            "severity": "warning",
            "message": f"No purchase history found for {txn_symbol}; cannot classify hold period.",
        })
        return results

    earliest_buy = min(buy_dates)
    try:
        buy_dt = datetime.strptime(earliest_buy, "%Y-%m-%d")
    except ValueError:
        return results

    hold_days = (txn_date - buy_dt).days
    if hold_days >= LONG_TERM_DAYS:
        classification = "long-term"
        severity = "info"
        tax_note = "Taxed at favorable long-term capital gains rates (0%, 15%, or 20%)."
    else:
        classification = "short-term"
        severity = "warning"
        tax_note = "Taxed as ordinary income (up to 37%). Consider holding longer for long-term rates."

    results.append({
        "rule": "capital_gains",
        "severity": severity,
        "message": (
            f"{transaction.get('symbol', txn_symbol)} held for {hold_days} days "
            f"(acquired {earliest_buy}): {classification} capital gain. {tax_note}"
        ),
        "classification": classification,
        "hold_days": hold_days,
    })

    return results


def _check_tax_loss_harvesting(transaction: dict, context: dict) -> list[dict]:
    """Identify harvestable losses and flag wash sale risk on rebuy."""
    results: list[dict] = []
    txn_type = (transaction.get("type") or "").upper()
    txn_symbol = (transaction.get("symbol") or "").upper()

    holdings = context.get("holdings", [])

    if txn_type == "SELL":
        txn_price = transaction.get("unitPrice", 0) or 0
        cost_per_share = context.get("avg_cost_per_share", 0)
        if txn_price > 0 and cost_per_share > 0 and txn_price < cost_per_share:
            loss_per_share = round(cost_per_share - txn_price, 2)
            qty = transaction.get("quantity", 0) or 0
            results.append({
                "rule": "tax_loss_harvesting",
                "severity": "info",
                "message": (
                    f"Harvesting loss on {txn_symbol}: ~${loss_per_share:.2f}/share "
                    f"(total ~${loss_per_share * qty:,.2f}). "
                    f"Avoid repurchasing {txn_symbol} within 30 days to preserve the deduction."
                ),
            })
        return results

    if txn_type == "BUY":
        for h in holdings:
            h_symbol = (h.get("symbol") or "").upper()
            if not h_symbol or h_symbol == txn_symbol:
                continue
            investment = h.get("investment", 0) or 0
            value = h.get("valueInBaseCurrency") or h.get("value") or 0
            if investment > 0 and value < investment:
                unrealized_loss = round(investment - value, 2)
                results.append({
                    "rule": "tax_loss_harvesting",
                    "severity": "info",
                    "message": (
                        f"Consider harvesting loss on {h_symbol} "
                        f"(unrealized loss ~${unrealized_loss:,.2f}) before buying {txn_symbol}."
                    ),
                })
        return results

    return results


# ---------------------------------------------------------------------------
# Regulation registry
# ---------------------------------------------------------------------------

RegulationFn = Callable[[dict, dict], list[dict]]

REGULATION_REGISTRY: dict[str, RegulationFn] = {
    "wash_sale": _check_wash_sale,
    "capital_gains": _check_capital_gains,
    "tax_loss_harvesting": _check_tax_loss_harvesting,
}


def _stub_regulation(reg_id: str, transaction: dict, context: dict) -> list[dict]:
    return [{
        "rule": reg_id,
        "severity": "info",
        "message": f"Regulation '{reg_id}' is not yet implemented. Consult a tax professional.",
    }]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compliance_check(
    transaction: dict,
    regulations: list[str],
    client: GhostfolioClient | None = None,
) -> dict[str, Any]:
    """Check a transaction against regulatory/tax compliance rules.

    Args:
        transaction: Order-like dict with type, symbol, quantity, unitPrice, date, etc.
        regulations: List of regulation IDs to check (e.g. ["wash_sale", "capital_gains"]).
        client: GhostfolioClient for fetching context (order history, holdings).
    """
    txn_symbol = (transaction.get("symbol") or "").upper()

    context: dict[str, Any] = {}
    if client and txn_symbol:
        context["recent_orders"] = _get_recent_orders(txn_symbol, client, days=WASH_SALE_WINDOW_DAYS + 10)
        context["all_orders"] = _get_all_orders(txn_symbol, client)

        buy_orders = [
            o for o in context["all_orders"]
            if (o.get("type") or "").upper() == "BUY"
            and (o.get("symbol") or (o.get("SymbolProfile") or {}).get("symbol") or "").upper() == txn_symbol
        ]
        total_cost = sum((o.get("unitPrice", 0) or 0) * (o.get("quantity", 0) or 0) for o in buy_orders)
        total_qty = sum(o.get("quantity", 0) or 0 for o in buy_orders)
        context["avg_cost_per_share"] = (total_cost / total_qty) if total_qty > 0 else 0

        try:
            holdings_data = client.get_holdings()
            raw = []
            if isinstance(holdings_data, dict) and "holdings" in holdings_data:
                raw = holdings_data["holdings"]
            elif isinstance(holdings_data, list):
                raw = holdings_data
            context["holdings"] = raw
        except Exception:
            context["holdings"] = []
    else:
        context["recent_orders"] = []
        context["all_orders"] = []
        context["avg_cost_per_share"] = 0
        context["holdings"] = []

    all_violations: list[dict] = []
    all_warnings: list[dict] = []

    for reg_id in regulations:
        check_fn = REGULATION_REGISTRY.get(reg_id)
        if check_fn:
            findings = check_fn(transaction, context)
        else:
            findings = _stub_regulation(reg_id, transaction, context)

        for f in findings:
            severity = f.get("severity", "warning")
            if severity == "violation":
                all_violations.append(f)
            else:
                all_warnings.append(f)

    passed = len(all_violations) == 0

    return {
        "violations": all_violations,
        "warnings": all_warnings,
        "passed": passed,
    }
