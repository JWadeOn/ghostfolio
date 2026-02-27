"""Unit tests for the tax_estimate tool."""

from agent.tools.tax_estimate import tax_estimate


def test_basic_single_filer():
    result = tax_estimate(income=100000, deductions=20000)

    assert "error" not in result
    assert result["taxable_income"] == 80000
    assert result["filing_status"] == "single"
    assert result["estimated_liability"] > 0
    assert 0 < result["effective_rate"] < 37
    assert len(result["breakdown"]) > 0


def test_zero_income():
    result = tax_estimate(income=0)

    assert result["estimated_liability"] == 0
    assert result["taxable_income"] == 0
    assert result["effective_rate"] == 0


def test_deductions_exceed_income():
    result = tax_estimate(income=10000, deductions=50000)

    assert result["estimated_liability"] == 0
    assert result["taxable_income"] == 0


def test_married_filing_jointly():
    result = tax_estimate(income=200000, deductions=30000, filing_status="married_filing_jointly")

    assert result["filing_status"] == "married_filing_jointly"
    assert result["estimated_liability"] > 0
    # Married brackets are wider, so effective rate should be lower than single at same income
    single = tax_estimate(income=200000, deductions=30000, filing_status="single")
    assert result["effective_rate"] < single["effective_rate"]


def test_invalid_filing_status():
    result = tax_estimate(income=100000, filing_status="alien")
    assert "error" in result


def test_known_bracket_calculation():
    # First bracket only: $10,000 taxable at 10% = $1,000
    result = tax_estimate(income=10000, deductions=0, filing_status="single")

    assert result["taxable_income"] == 10000
    assert result["estimated_liability"] == 1000.0
    assert result["effective_rate"] == 10.0


def test_non_usd_currency_includes_note():
    result = tax_estimate(income=100000, currency="EUR")
    assert "note" in result
    assert "USD" in result["note"]
