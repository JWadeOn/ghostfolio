"""Portfolio and trade guardrails — position sizing, concentration, correlation, cash checks."""

from __future__ import annotations

import logging
from datetime import datetime
from functools import lru_cache
from typing import Any

from agent.tools.portfolio import get_portfolio_snapshot
from agent.tools.market_data import get_market_data
from agent.ghostfolio_client import GhostfolioClient

logger = logging.getLogger(__name__)

MAX_POSITION_PCT = 5.0
MAX_SECTOR_PCT = 30.0
MAX_CORRELATION = 0.7
DEFAULT_STOP_LOSS_PCT = 2.0


@lru_cache(maxsize=256)
def _get_sector(symbol: str) -> str | None:
    """Get sector for a symbol from yfinance (imported lazily to avoid numpy SIGFPE on macOS)."""
    try:
        import yfinance as yf
        info = yf.Ticker(symbol).info
        return info.get("sector", None)
    except Exception:
        return None


def _normalize_weight(raw_weight: float) -> float:
    """Normalize weight to 0-100 scale (Ghostfolio may return 0-1 or 0-100)."""
    if (raw_weight or 0) < 1:
        return (raw_weight or 0) * 100
    return raw_weight or 0


def _compute_hold_period(symbol: str, client: GhostfolioClient | None) -> int | None:
    """Compute days held from earliest open buy for *symbol*."""
    if client is None:
        return None
    try:
        orders_data = client.get_orders(symbol=symbol)
        raw = (
            orders_data.get("activities", [])
            if isinstance(orders_data, dict) and "activities" in orders_data
            else (orders_data if isinstance(orders_data, list) else [])
        )
        buy_dates = []
        for o in raw:
            if (o.get("type") or "").upper() == "BUY" and o.get("date"):
                buy_dates.append(o["date"][:10])
        if not buy_dates:
            return None
        earliest = min(buy_dates)
        buy_dt = datetime.strptime(earliest, "%Y-%m-%d")
        return (datetime.now() - buy_dt).days
    except Exception as e:
        logger.warning("Failed to compute hold period for %s: %s", symbol, e)
        return None


# ---------------------------------------------------------------------------
# portfolio_guardrails_check
# ---------------------------------------------------------------------------

def portfolio_guardrails_check(
    client: GhostfolioClient | None = None,
    portfolio_data: dict | None = None,
) -> dict[str, Any]:
    """Assess portfolio-level risk: concentration, cash buffer, diversification.

    No symbol or trade amount — this is a health check on the portfolio itself.
    """
    portfolio = portfolio_data or get_portfolio_snapshot(client)

    if isinstance(portfolio, dict) and "error" in portfolio and not portfolio.get("partial"):
        return {"error": portfolio["error"], "passed": False}

    total_value = portfolio.get("summary", {}).get("total_value", 0)
    total_cash = portfolio.get("summary", {}).get("total_cash", 0)
    holdings = portfolio.get("holdings", [])

    violations: list[dict] = []
    warnings: list[dict] = []
    cash_pct = (total_cash / total_value * 100) if total_value > 0 else 0
    holding_count = len(holdings)

    if cash_pct < 5 and total_value > 0:
        violations.append({
            "rule": "zero_cash",
            "message": f"You have {cash_pct:.1f}% cash reserves",
            "risk": "No liquidity for opportunities or emergency exits",
            "recommendation": "Consider reducing position size to maintain 5-10% cash buffer",
        })
    elif cash_pct < 10 and total_value > 0:
        warnings.append({
            "rule": "low_cash",
            "message": f"Cash is {cash_pct:.1f}% of portfolio",
            "recommendation": "Aim for 5-10% cash buffer",
        })

    if holding_count == 0:
        pass
    elif holding_count == 1:
        h = holdings[0]
        weight = _normalize_weight(h.get("weight", 0))
        violations.append({
            "rule": "concentration",
            "message": f"Single holding represents {weight:.1f}% of portfolio",
            "risk": "Maximum exposure to individual security risk",
            "recommendation": "Diversify across 3-5 positions minimum",
        })
    else:
        for h in holdings:
            weight = _normalize_weight(h.get("weight", 0))
            if weight > MAX_POSITION_PCT:
                violations.append({
                    "rule": "position_size",
                    "message": f"{h.get('symbol', '?')} is {weight:.1f}% of portfolio (max {MAX_POSITION_PCT}%)",
                    "symbol": h.get("symbol"),
                    "current": weight,
                    "limit": MAX_POSITION_PCT,
                })

    sector_weights: dict[str, float] = {}
    for h in holdings:
        sym = h.get("symbol")
        weight = _normalize_weight(h.get("weight", 0))
        if not sym:
            continue
        sector = _get_sector(sym)
        if sector:
            sector_weights[sector] = sector_weights.get(sector, 0) + weight
    for sec, w in sector_weights.items():
        if w > MAX_SECTOR_PCT:
            violations.append({
                "rule": "sector_concentration",
                "message": f"Sector '{sec}' is {w:.1f}% of portfolio (max {MAX_SECTOR_PCT}%)",
                "sector": sec,
                "current": w,
                "limit": MAX_SECTOR_PCT,
            })

    passed = len(violations) == 0
    return {
        "passed": passed,
        "portfolio_level": True,
        "violations": violations,
        "warnings": warnings,
        "portfolio_summary": {
            "total_value": total_value,
            "total_cash": total_cash,
            "holding_count": holding_count,
            "cash_pct": round(cash_pct, 2),
        },
    }


# ---------------------------------------------------------------------------
# trade_guardrails_check
# ---------------------------------------------------------------------------

def _evaluate_sell(
    symbol: str,
    total_value: float,
    total_cash: float,
    holdings: list[dict[str, Any]],
    client: GhostfolioClient | None = None,
) -> dict[str, Any]:
    """Evaluate whether to sell an existing position."""
    position = None
    for h in holdings:
        if (h.get("symbol") or "").upper() == symbol.upper():
            position = h
            break

    if not position:
        return {
            "error": f"You do not hold {symbol}. Nothing to sell.",
            "passed": False,
            "sell_evaluation": True,
            "symbol": symbol,
        }

    weight = _normalize_weight(position.get("weight", 0))
    value = position.get("value") or position.get("value_in_base_currency") or 0
    cost_basis = position.get("investment", 0)
    if cost_basis and cost_basis > 0:
        unrealized_pnl_pct = round((value - cost_basis) / cost_basis * 100, 2)
        unrealized_pnl_dollar = round(value - cost_basis, 2)
    else:
        unrealized_pnl_pct = None
        unrealized_pnl_dollar = None

    sector = _get_sector(symbol)
    sector_weight = 0.0
    for h in holdings:
        s = _get_sector(h.get("symbol", ""))
        if s and s == sector:
            sector_weight += _normalize_weight(h.get("weight", 0))

    reasons_to_sell: list[dict] = []
    reasons_to_hold: list[dict] = []

    if weight > MAX_POSITION_PCT:
        reasons_to_sell.append({
            "rule": "position_concentration",
            "message": f"{symbol} is {weight:.1f}% of portfolio (max {MAX_POSITION_PCT}% for single position)",
            "current_weight": round(weight, 2),
            "limit": MAX_POSITION_PCT,
        })
    if len(holdings) == 1:
        reasons_to_sell.append({
            "rule": "single_holding",
            "message": "Portfolio is 100% in one position — no diversification",
            "recommendation": "Selling a portion would free cash and allow diversification",
        })
    cash_pct = (total_cash / total_value * 100) if total_value > 0 else 0
    if cash_pct < 5 and total_value > 0:
        reasons_to_sell.append({
            "rule": "no_cash_buffer",
            "message": f"Cash is {cash_pct:.1f}% of portfolio",
            "recommendation": "Selling part of this position would create a cash buffer",
        })
    if sector_weight > MAX_SECTOR_PCT and sector:
        reasons_to_sell.append({
            "rule": "sector_concentration",
            "message": f"Sector '{sector}' is {sector_weight:.1f}% of portfolio (max {MAX_SECTOR_PCT}%)",
            "sector": sector,
            "current": round(sector_weight, 2),
            "limit": MAX_SECTOR_PCT,
        })

    recommend_sell = len(reasons_to_sell) > 0
    cash_after_full_sell = round(total_cash + value, 2)
    portfolio_after_sell_value = round(total_value - value, 2) if total_value else 0

    hold_period = _compute_hold_period(symbol, client)

    stop_loss_level = None
    if cost_basis and cost_basis > 0:
        qty = position.get("quantity", 0) or 1
        avg_cost = cost_basis / qty
        stop_loss_level = round(avg_cost * (1 - DEFAULT_STOP_LOSS_PCT / 100), 2)

    return {
        "passed": recommend_sell,
        "symbol": symbol,
        "sell_evaluation": True,
        "action": "sell",
        "position": {
            "symbol": symbol,
            "value": round(value, 2),
            "cost_basis": round(cost_basis, 2) if cost_basis else None,
            "weight_pct": round(weight, 2),
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "unrealized_pnl_dollar": unrealized_pnl_dollar,
            "sector": sector,
        },
        "reasons_to_sell": reasons_to_sell,
        "reasons_to_hold": reasons_to_hold,
        "recommend_sell": recommend_sell,
        "hold_period": hold_period,
        "stop_loss_level": stop_loss_level,
        "portfolio_after_sell": {
            "portfolio_value": portfolio_after_sell_value,
            "cash_after_full_sell": cash_after_full_sell,
        },
        "portfolio_summary": {
            "total_value": total_value,
            "total_cash": total_cash,
            "holding_count": len(holdings),
            "cash_pct": round(cash_pct, 2),
        },
    }


def trade_guardrails_check(
    symbol: str,
    side: str = "buy",
    position_size_pct: float | None = None,
    dollar_amount: float | None = None,
    client: GhostfolioClient | None = None,
    portfolio_data: dict | None = None,
    market_data: dict | None = None,
) -> dict[str, Any]:
    """Check if a proposed buy or sell fits portfolio guardrails.

    For buys: position size, sector, correlation, cash, suggested size, stop loss.
    For sells: reasons to sell/hold, P&L, hold period, stop loss, portfolio after.
    """
    portfolio = portfolio_data or get_portfolio_snapshot(client)

    if isinstance(portfolio, dict) and "error" in portfolio and not portfolio.get("partial"):
        return {"error": portfolio["error"], "passed": False}

    total_value = portfolio.get("summary", {}).get("total_value", 0)
    total_cash = portfolio.get("summary", {}).get("total_cash", 0)
    holdings = portfolio.get("holdings", [])

    if (side or "buy").lower() == "sell":
        return _evaluate_sell(symbol, total_value, total_cash, holdings, client)

    # --- Buy path ---

    if dollar_amount and total_value > 0:
        position_size_pct = (dollar_amount / total_value) * 100
    elif position_size_pct and total_value > 0:
        dollar_amount = total_value * (position_size_pct / 100)
    elif not position_size_pct:
        position_size_pct = 5.0
        dollar_amount = total_value * 0.05 if total_value > 0 else 0

    violations: list[dict] = []
    warnings: list[dict] = []

    existing_weight = 0.0
    for h in holdings:
        if h.get("symbol", "").upper() == symbol.upper():
            existing_weight = _normalize_weight(h.get("weight", 0))

    proposed_total = existing_weight + position_size_pct
    if proposed_total > MAX_POSITION_PCT:
        violations.append({
            "rule": "position_size",
            "message": f"Total position in {symbol} would be {proposed_total:.1f}% (max {MAX_POSITION_PCT}%)",
            "current": existing_weight,
            "proposed_addition": position_size_pct,
            "limit": MAX_POSITION_PCT,
        })

    target_sector = _get_sector(symbol)
    if target_sector:
        sector_weight = 0.0
        for h in holdings:
            h_sectors = h.get("sectors", [])
            for s in h_sectors:
                sector_name = s.get("name", s) if isinstance(s, dict) else s
                if isinstance(sector_name, str) and sector_name.lower() == target_sector.lower():
                    sector_weight += _normalize_weight(h.get("weight", 0))
                    break
        proposed_sector = sector_weight + position_size_pct
        if proposed_sector > MAX_SECTOR_PCT:
            violations.append({
                "rule": "sector_concentration",
                "message": f"Sector '{target_sector}' would be {proposed_sector:.1f}% (max {MAX_SECTOR_PCT}%)",
                "current": sector_weight,
                "proposed_addition": position_size_pct,
                "limit": MAX_SECTOR_PCT,
            })

    holding_symbols = [h["symbol"] for h in holdings if h.get("symbol")]
    if holding_symbols:
        all_syms = [symbol] + holding_symbols[:10]
        try:
            data = market_data if market_data else get_market_data(all_syms, period="30d")
            closes: dict[str, dict] = {}
            for sym in all_syms:
                sym_data = data.get(sym, [])
                if isinstance(sym_data, list):
                    closes[sym] = {r["date"]: r["close"] for r in sym_data if r.get("close")}

            if symbol in closes and len(closes[symbol]) > 5:
                import pandas as pd
                df = pd.DataFrame(closes).dropna()
                if len(df) >= 10:
                    returns = df.pct_change().dropna()
                    import numpy as np
                    if returns.std().gt(0).sum() >= 2 and symbol in returns.columns:
                        for h_sym in holding_symbols[:10]:
                            if h_sym in returns.columns:
                                if returns[h_sym].std() > 0 and returns[symbol].std() > 0:
                                    corr = returns[symbol].corr(returns[h_sym])
                                    if not (np.isnan(corr) or np.isinf(corr)) and corr > MAX_CORRELATION:
                                        warnings.append({
                                            "rule": "correlation",
                                            "message": f"High correlation ({corr:.2f}) with existing holding {h_sym}",
                                            "correlated_with": h_sym,
                                            "correlation": round(float(corr), 3),
                                        })
        except Exception as e:
            logger.warning("Correlation check failed: %s", e)

    if existing_weight > 0:
        warnings.append({
            "rule": "existing_exposure",
            "message": f"Already holding {symbol} at {existing_weight:.1f}% of portfolio",
            "current_weight": existing_weight,
        })

    if dollar_amount and dollar_amount > total_cash:
        violations.append({
            "rule": "cash_available",
            "message": f"Proposed ${dollar_amount:,.0f} exceeds available cash ${total_cash:,.0f}",
            "requested": dollar_amount,
            "available": total_cash,
        })

    passed = len(violations) == 0

    suggested_size_pct = position_size_pct
    if not passed:
        for v in violations:
            if v["rule"] == "position_size":
                max_add = max(0, MAX_POSITION_PCT - existing_weight)
                suggested_size_pct = min(suggested_size_pct, max_add)
            if v["rule"] == "cash_available" and total_value > 0:
                suggested_size_pct = min(suggested_size_pct, (total_cash / total_value) * 100)

    stop_loss_level = None
    try:
        md = market_data if market_data else get_market_data([symbol], period="5d")
        sym_data = md.get(symbol, [])
        if isinstance(sym_data, list) and sym_data:
            current_price = sym_data[-1].get("close", 0)
            if current_price > 0:
                stop_loss_level = round(current_price * (1 - DEFAULT_STOP_LOSS_PCT / 100), 2)
    except Exception:
        pass

    return {
        "passed": passed,
        "symbol": symbol,
        "action": "buy",
        "proposed_size_pct": round(position_size_pct, 2),
        "proposed_dollar": round(dollar_amount, 2) if dollar_amount else None,
        "violations": violations,
        "warnings": warnings,
        "suggested_size_pct": round(suggested_size_pct, 2),
        "suggested_dollar": round(total_value * suggested_size_pct / 100, 2) if total_value > 0 else None,
        "stop_loss_level": stop_loss_level,
        "portfolio_summary": {
            "total_value": total_value,
            "total_cash": total_cash,
            "holding_count": len(holdings),
        },
    }


# ---------------------------------------------------------------------------
# Legacy wrapper — will be removed once all callers migrate
# ---------------------------------------------------------------------------

def check_risk(
    symbol: str | None = None,
    direction: str = "LONG",
    action: str = "buy",
    position_size_pct: float | None = None,
    dollar_amount: float | None = None,
    client: GhostfolioClient | None = None,
) -> dict[str, Any]:
    """Legacy wrapper — delegates to portfolio_guardrails_check or trade_guardrails_check."""
    if (action or "buy").lower() == "sell" and symbol:
        return trade_guardrails_check(symbol, side="sell", client=client)
    if symbol is None or symbol == "":
        return portfolio_guardrails_check(client=client)
    return trade_guardrails_check(
        symbol, side="buy",
        position_size_pct=position_size_pct,
        dollar_amount=dollar_amount,
        client=client,
    )
