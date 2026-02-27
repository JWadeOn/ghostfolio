"""Portfolio guardrails tool for LangChain financial agents."""

import os
from typing import Dict, List

from langchain_core.tools import tool


# --- Threshold defaults (overridable via env vars or _check_impl kwargs) ---
_DEFAULTS = {
    "position_violation_pct": 20.0,
    "position_warning_pct": 15.0,
    "sector_violation_pct": 40.0,
    "sector_warning_pct": 30.0,
    "cash_violation_pct": 3.0,
    "cash_warning_pct": 5.0,
    "diversification_violation_count": 1,
    "diversification_warning_count": 3,
}


def _threshold(name: str, **overrides: float) -> float:
    """Return threshold from overrides → env → default, in that priority."""
    if name in overrides:
        return float(overrides[name])
    env_key = f"GUARDRAILS_{name.upper()}"
    env_val = os.environ.get(env_key)
    if env_val is not None:
        return float(env_val)
    return float(_DEFAULTS[name])


# ---------------------------------------------------------------------------
# Core logic (pure Python, no external deps beyond langchain-core)
# ---------------------------------------------------------------------------

def _check_impl(holdings: List[Dict], **overrides: float) -> Dict:
    """Run all five guardrail rules and return a structured result."""

    violations: List[str] = []
    warnings: List[str] = []
    per_rule: Dict[str, Dict] = {}

    total_value = sum(h.get("value", 0) for h in holdings)

    # --- Rule 1: Position concentration ---
    pos_viol_pct = _threshold("position_violation_pct", **overrides)
    pos_warn_pct = _threshold("position_warning_pct", **overrides)
    pos_details: List[Dict] = []
    for h in holdings:
        if total_value == 0:
            break
        symbol = h.get("symbol", "UNKNOWN")
        pct = (h.get("value", 0) / total_value) * 100
        entry = {"symbol": symbol, "pct": round(pct, 2), "status": "ok"}
        if pct > pos_viol_pct:
            entry["status"] = "violation"
            violations.append(
                f"Position concentration: {symbol} is {pct:.1f}% of portfolio "
                f"(limit {pos_viol_pct:.0f}%)"
            )
        elif pct > pos_warn_pct:
            entry["status"] = "warning"
            warnings.append(
                f"Position concentration: {symbol} is {pct:.1f}% of portfolio "
                f"(warning above {pos_warn_pct:.0f}%)"
            )
        pos_details.append(entry)
    per_rule["position_concentration"] = {
        "violation_threshold_pct": pos_viol_pct,
        "warning_threshold_pct": pos_warn_pct,
        "details": pos_details,
    }

    # --- Rule 2: Sector concentration ---
    sec_viol_pct = _threshold("sector_violation_pct", **overrides)
    sec_warn_pct = _threshold("sector_warning_pct", **overrides)
    sector_values: Dict[str, float] = {}
    for h in holdings:
        sector = h.get("sector", "Unknown")
        sector_values[sector] = sector_values.get(sector, 0) + h.get("value", 0)
    sec_details: List[Dict] = []
    for sector, val in sector_values.items():
        if total_value == 0:
            break
        pct = (val / total_value) * 100
        entry = {"sector": sector, "pct": round(pct, 2), "status": "ok"}
        if pct > sec_viol_pct:
            entry["status"] = "violation"
            violations.append(
                f"Sector concentration: {sector} is {pct:.1f}% of portfolio "
                f"(limit {sec_viol_pct:.0f}%)"
            )
        elif pct > sec_warn_pct:
            entry["status"] = "warning"
            warnings.append(
                f"Sector concentration: {sector} is {pct:.1f}% of portfolio "
                f"(warning above {sec_warn_pct:.0f}%)"
            )
        sec_details.append(entry)
    per_rule["sector_concentration"] = {
        "violation_threshold_pct": sec_viol_pct,
        "warning_threshold_pct": sec_warn_pct,
        "details": sec_details,
    }

    # --- Rule 3: Cash buffer ---
    cash_viol_pct = _threshold("cash_violation_pct", **overrides)
    cash_warn_pct = _threshold("cash_warning_pct", **overrides)
    cash_value = sum(
        h.get("value", 0) for h in holdings
        if h.get("symbol", "").upper() in ("CASH", "$CASH", "USD")
    )
    cash_pct = (cash_value / total_value * 100) if total_value else 0
    cash_status = "ok"
    if cash_pct < cash_viol_pct:
        cash_status = "violation"
        violations.append(
            f"Cash buffer: cash is {cash_pct:.1f}% of portfolio "
            f"(minimum {cash_viol_pct:.0f}%)"
        )
    elif cash_pct < cash_warn_pct:
        cash_status = "warning"
        warnings.append(
            f"Cash buffer: cash is {cash_pct:.1f}% of portfolio "
            f"(recommended minimum {cash_warn_pct:.0f}%)"
        )
    per_rule["cash_buffer"] = {
        "violation_threshold_pct": cash_viol_pct,
        "warning_threshold_pct": cash_warn_pct,
        "cash_pct": round(cash_pct, 2),
        "status": cash_status,
    }

    # --- Rule 4: Diversification (holding count) ---
    div_viol = int(_threshold("diversification_violation_count", **overrides))
    div_warn = int(_threshold("diversification_warning_count", **overrides))
    num_holdings = len([h for h in holdings if h.get("symbol", "").upper() not in ("CASH", "$CASH", "USD")])
    div_status = "ok"
    if num_holdings <= div_viol:
        div_status = "violation"
        violations.append(
            f"Diversification: only {num_holdings} non-cash holding(s) "
            f"(minimum {div_viol + 1} required)"
        )
    elif num_holdings < div_warn:
        div_status = "warning"
        warnings.append(
            f"Diversification: only {num_holdings} non-cash holding(s) "
            f"(recommend at least {div_warn})"
        )
    per_rule["diversification"] = {
        "violation_threshold_count": div_viol,
        "warning_threshold_count": div_warn,
        "non_cash_holdings": num_holdings,
        "status": div_status,
    }

    # --- Rule 5: Position count / extreme concentration ---
    # Flag if any single position exceeds 50% or if <=2 positions make up >80%
    extreme_details: List[str] = []
    extreme_status = "ok"
    if total_value > 0:
        sorted_holdings = sorted(holdings, key=lambda h: h.get("value", 0), reverse=True)
        top1_pct = (sorted_holdings[0].get("value", 0) / total_value) * 100 if sorted_holdings else 0
        if top1_pct > 50:
            extreme_status = "violation"
            msg = (
                f"Extreme concentration: top position "
                f"({sorted_holdings[0].get('symbol', '?')}) is {top1_pct:.1f}% of portfolio"
            )
            extreme_details.append(msg)
            violations.append(msg)
        if len(sorted_holdings) >= 2:
            top2_pct = sum(h.get("value", 0) for h in sorted_holdings[:2]) / total_value * 100
            if top2_pct > 80 and extreme_status != "violation":
                extreme_status = "warning"
                msg = f"Extreme concentration: top 2 positions make up {top2_pct:.1f}% of portfolio"
                extreme_details.append(msg)
                warnings.append(msg)
    per_rule["position_count"] = {
        "status": extreme_status,
        "details": extreme_details,
    }

    return {
        "violations": violations,
        "warnings": warnings,
        "passed": len(violations) == 0,
        "per_rule_breakdown": per_rule,
    }


@tool
def portfolio_guardrails_check(holdings: List[Dict]) -> Dict:
    """Check a portfolio against standard risk guardrails.

    Use when the user asks about portfolio health, concentration,
    diversification, or whether their portfolio is within safe limits.

    Args:
        holdings: List of positions, each with:
            - symbol (str): ticker symbol
            - value (float): current market value in USD
            - sector (str): sector name

    Returns:
        violations: list of rule violations (must fix)
        warnings: list of warnings (worth reviewing)
        passed: bool — True if no violations
        per_rule_breakdown: detailed result per rule
    """
    return _check_impl(holdings)
