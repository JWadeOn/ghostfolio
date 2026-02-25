"""Tool 5: check_risk — validate position size, sector concentration, and correlation."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import yfinance as yf

from agent.tools.portfolio import get_portfolio_snapshot
from agent.tools.market_data import get_market_data
from agent.ghostfolio_client import GhostfolioClient

logger = logging.getLogger(__name__)

MAX_POSITION_PCT = 5.0
MAX_SECTOR_PCT = 30.0
MAX_CORRELATION = 0.7


def _get_sector(symbol: str) -> str | None:
    """Get sector for a symbol from yfinance."""
    try:
        info = yf.Ticker(symbol).info
        return info.get("sector", None)
    except Exception:
        return None


def _portfolio_level_risk(
    total_value: float,
    total_cash: float,
    holdings: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assess portfolio-level risk (concentration, cash, diversification) when no specific trade is proposed."""
    violations = []
    warnings = []
    cash_pct = (total_cash / total_value * 100) if total_value > 0 else 0
    holding_count = len(holdings)

    # Cash buffer
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

    # Concentration: single position or few positions
    if holding_count == 0:
        pass  # No holdings
    elif holding_count == 1:
        h = holdings[0]
        weight = h.get("weight", 0) * 100 if (h.get("weight", 0) or 0) < 1 else (h.get("weight", 0) or 0)
        violations.append({
            "rule": "concentration",
            "message": f"Single holding represents {weight:.1f}% of portfolio",
            "risk": "Maximum exposure to individual security risk",
            "recommendation": "Diversify across 3-5 positions minimum",
        })
    else:
        for h in holdings:
            weight = h.get("weight", 0) * 100 if (h.get("weight", 0) or 0) < 1 else (h.get("weight", 0) or 0)
            if weight > MAX_POSITION_PCT:
                violations.append({
                    "rule": "position_size",
                    "message": f"{h.get('symbol', '?')} is {weight:.1f}% of portfolio (max {MAX_POSITION_PCT}%)",
                    "symbol": h.get("symbol"),
                    "current": weight,
                    "limit": MAX_POSITION_PCT,
                })

    # Sector concentration across existing holdings
    sector_weights: dict[str, float] = {}
    for h in holdings:
        sym = h.get("symbol")
        weight = h.get("weight", 0) * 100 if (h.get("weight", 0) or 0) < 1 else (h.get("weight", 0) or 0)
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
        "symbol": None,
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


def check_risk(
    symbol: str | None = None,
    direction: str = "LONG",
    position_size_pct: float | None = None,
    dollar_amount: float | None = None,
    client: GhostfolioClient | None = None,
) -> dict[str, Any]:
    """
    Check if a proposed trade fits portfolio risk parameters, or assess portfolio-level risk when no symbol is given.

    Args:
        symbol: Ticker symbol to trade; if None, runs portfolio-level risk assessment (concentration, cash, diversification).
        direction: "LONG" or "SHORT"
        position_size_pct: Proposed position as % of portfolio (alternative to dollar_amount)
        dollar_amount: Proposed dollar amount (alternative to position_size_pct)
        client: Optional GhostfolioClient

    Returns:
        Dict with passed (bool), violations list, and suggested adjustments.
        When symbol is None, returns portfolio-level risk (no proposed trade).
    """
    portfolio = get_portfolio_snapshot(client)

    if isinstance(portfolio, dict) and "error" in portfolio and not portfolio.get("partial"):
        return {"error": portfolio["error"], "passed": False}

    total_value = portfolio.get("summary", {}).get("total_value", 0)
    total_cash = portfolio.get("summary", {}).get("total_cash", 0)
    holdings = portfolio.get("holdings", [])

    # Portfolio-level risk assessment when no symbol is provided
    if symbol is None or symbol == "":
        return _portfolio_level_risk(total_value, total_cash, holdings)

    # Compute proposed position size
    if dollar_amount and total_value > 0:
        position_size_pct = (dollar_amount / total_value) * 100
    elif position_size_pct and total_value > 0:
        dollar_amount = total_value * (position_size_pct / 100)
    elif not position_size_pct:
        position_size_pct = 5.0
        dollar_amount = total_value * 0.05 if total_value > 0 else 0

    violations = []
    warnings = []

    # 1. Position size check
    existing_weight = 0
    for h in holdings:
        if h.get("symbol", "").upper() == symbol.upper():
            existing_weight = h.get("weight", 0) * 100 if h.get("weight", 0) < 1 else h.get("weight", 0)

    proposed_total = existing_weight + position_size_pct
    if proposed_total > MAX_POSITION_PCT:
        violations.append({
            "rule": "position_size",
            "message": f"Total position in {symbol} would be {proposed_total:.1f}% (max {MAX_POSITION_PCT}%)",
            "current": existing_weight,
            "proposed_addition": position_size_pct,
            "limit": MAX_POSITION_PCT,
        })

    # 2. Sector concentration check
    target_sector = _get_sector(symbol)
    if target_sector:
        sector_weight = 0
        for h in holdings:
            h_sectors = h.get("sectors", [])
            for s in h_sectors:
                if s.get("name", "").lower() == target_sector.lower():
                    sector_weight += h.get("weight", 0) * 100 if h.get("weight", 0) < 1 else h.get("weight", 0)
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

    # 3. Correlation check
    holding_symbols = [h["symbol"] for h in holdings if h.get("symbol")]
    if holding_symbols:
        all_syms = [symbol] + holding_symbols[:10]  # limit for performance
        try:
            data = get_market_data(all_syms, period="30d")
            # Build returns matrix
            closes = {}
            for sym in all_syms:
                sym_data = data.get(sym, [])
                if isinstance(sym_data, list):
                    closes[sym] = {r["date"]: r["close"] for r in sym_data if r.get("close")}

            if symbol in closes and len(closes[symbol]) > 5:
                import pandas as pd
                df = pd.DataFrame(closes).dropna()
                if len(df) >= 10:
                    returns = df.pct_change().dropna()
                    # Skip constant columns to avoid degenerate correlation / SIGFPE
                    if returns.std().gt(0).sum() >= 2 and symbol in returns.columns:
                        for h_sym in holding_symbols[:10]:
                            if h_sym in returns.columns and symbol in returns.columns:
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
            logger.warning(f"Correlation check failed: {e}")

    # 4. Existing exposure
    if existing_weight > 0:
        warnings.append({
            "rule": "existing_exposure",
            "message": f"Already holding {symbol} at {existing_weight:.1f}% of portfolio",
            "current_weight": existing_weight,
        })

    # 5. Cash availability
    if dollar_amount and dollar_amount > total_cash:
        violations.append({
            "rule": "cash_available",
            "message": f"Proposed ${dollar_amount:,.0f} exceeds available cash ${total_cash:,.0f}",
            "requested": dollar_amount,
            "available": total_cash,
        })

    passed = len(violations) == 0

    # Suggest adjusted size if violations
    suggested_size_pct = position_size_pct
    if not passed:
        for v in violations:
            if v["rule"] == "position_size":
                max_add = max(0, MAX_POSITION_PCT - existing_weight)
                suggested_size_pct = min(suggested_size_pct, max_add)
            if v["rule"] == "cash_available":
                if total_value > 0:
                    suggested_size_pct = min(suggested_size_pct, (total_cash / total_value) * 100)

    return {
        "passed": passed,
        "symbol": symbol,
        "direction": direction,
        "proposed_size_pct": round(position_size_pct, 2),
        "proposed_dollar": round(dollar_amount, 2) if dollar_amount else None,
        "violations": violations,
        "warnings": warnings,
        "suggested_size_pct": round(suggested_size_pct, 2),
        "suggested_dollar": round(total_value * suggested_size_pct / 100, 2) if total_value > 0 else None,
        "portfolio_summary": {
            "total_value": total_value,
            "total_cash": total_cash,
            "holding_count": len(holdings),
        },
    }
