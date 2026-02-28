"""Tool: tax_estimate — estimate US federal income tax from income and deductions.

Use when: "tax bill", "estimate taxes", "tax implications", "tax liability", "taxable income", "tax rate", "tax calculation", "tax planning", "tax-loss harvesting", "tax-efficient portfolio", "tax-efficient investment", "tax-efficient trading", "tax-efficient retirement", "tax-efficient savings", "tax-efficient estate planning", "tax-efficient retirement planning", "tax-efficient estate planning", "tax-efficient retirement planning", "tax-efficient estate planning", "tax-efficient retirement planning".
"""

from __future__ import annotations

from typing import Any

# Simplified 2025 US federal income tax brackets
BRACKETS = {
    "single": [
        (11925, 0.10),
        (48475, 0.12),
        (103350, 0.22),
        (197300, 0.24),
        (250525, 0.32),
        (626350, 0.35),
        (float("inf"), 0.37),
    ],
    "married_filing_jointly": [
        (23850, 0.10),
        (96950, 0.12),
        (206700, 0.22),
        (394600, 0.24),
        (501050, 0.32),
        (751600, 0.35),
        (float("inf"), 0.37),
    ],
    "head_of_household": [
        (17000, 0.10),
        (64850, 0.12),
        (103350, 0.22),
        (197300, 0.24),
        (250500, 0.32),
        (626350, 0.35),
        (float("inf"), 0.37),
    ],
}


def _compute_tax(taxable_income: float, brackets: list[tuple[float, float]]) -> tuple[float, list[dict]]:
    """Apply progressive brackets to taxable income. Returns (total_tax, breakdown)."""
    remaining = max(0.0, taxable_income)
    total_tax = 0.0
    breakdown: list[dict] = []
    prev_limit = 0.0

    for limit, rate in brackets:
        band = min(remaining, limit - prev_limit)
        if band <= 0:
            break
        tax_in_band = band * rate
        total_tax += tax_in_band
        breakdown.append({
            "bracket": f"{prev_limit:,.0f}–{limit:,.0f}" if limit != float("inf") else f"{prev_limit:,.0f}+",
            "rate": f"{rate * 100:.0f}%",
            "taxable_in_bracket": round(band, 2),
            "tax": round(tax_in_band, 2),
        })
        remaining -= band
        prev_limit = limit

    return round(total_tax, 2), breakdown


def tax_estimate(
    income: float,
    deductions: float = 0,
    filing_status: str = "single",
    currency: str = "USD",
) -> dict[str, Any]:
    """Estimate US federal income tax liability.

    Args:
        income: Gross income in USD.
        deductions: Total deductions (standard or itemized).
        filing_status: One of "single", "married_filing_jointly", "head_of_household".
        currency: Currency label (estimates are always USD-based).

    Returns:
        Dict with estimated_liability, taxable_income, effective_rate, filing_status, breakdown.
    """
    status_key = (filing_status or "single").strip().lower().replace(" ", "_")
    brackets = BRACKETS.get(status_key)
    if brackets is None:
        return {"error": f"Unknown filing status '{filing_status}'. Use single, married_filing_jointly, or head_of_household."}

    taxable_income = max(0.0, income - deductions)
    estimated_liability, breakdown = _compute_tax(taxable_income, brackets)
    effective_rate = round((estimated_liability / taxable_income * 100) if taxable_income > 0 else 0, 2)

    result: dict[str, Any] = {
        "estimated_liability": estimated_liability,
        "taxable_income": round(taxable_income, 2),
        "effective_rate": effective_rate,
        "filing_status": status_key,
        "breakdown": breakdown,
    }

    if (currency or "USD").upper() != "USD":
        result["note"] = "This estimate uses US federal tax brackets and is denominated in USD. For informational use only."

    return result
