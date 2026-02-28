"""Tests for the authoritative sources verification layer."""

import json
from pathlib import Path

import pytest

from agent.authoritative_sources import (
    TOOL_TO_SOURCES,
    get_excerpts_for_tools,
    get_source_by_id,
    get_sources_for_tools,
    _load_sources,
)
from agent.nodes.verification import _check_authoritative_consistency


# ── sources.json integrity ──────────────────────────────────────────

class TestSourcesJSON:
    def test_sources_file_exists(self):
        path = Path(__file__).parent.parent / "agent" / "authoritative_sources" / "sources.json"
        assert path.exists(), "sources.json not found"

    def test_sources_valid_json(self):
        sources = _load_sources()
        assert isinstance(sources, list)
        assert len(sources) >= 9

    def test_each_source_has_required_fields(self):
        sources = _load_sources()
        required = {"id", "label", "url", "excerpt", "as_of"}
        for s in sources:
            missing = required - set(s.keys())
            assert not missing, f"Source {s.get('id', '?')} missing fields: {missing}"

    def test_source_ids_unique(self):
        sources = _load_sources()
        ids = [s["id"] for s in sources]
        assert len(ids) == len(set(ids)), "Duplicate source IDs found"

    def test_all_mapped_ids_exist_in_json(self):
        """Every id referenced in TOOL_TO_SOURCES must exist in sources.json."""
        sources = _load_sources()
        known_ids = {s["id"] for s in sources}
        for tool, source_ids in TOOL_TO_SOURCES.items():
            for sid in source_ids:
                assert sid in known_ids, f"TOOL_TO_SOURCES['{tool}'] references '{sid}' not in sources.json"


# ── get_sources_for_tools ────────────────────────────────────────────

class TestGetSourcesForTools:
    def test_compliance_check_returns_sources(self):
        result = get_sources_for_tools(["compliance_check"])
        assert len(result) > 0
        assert all("label" in s and "url" in s and "id" in s for s in result)

    def test_tax_estimate_returns_sources(self):
        result = get_sources_for_tools(["tax_estimate"])
        assert len(result) > 0

    def test_unknown_tool_returns_empty(self):
        result = get_sources_for_tools(["get_market_data"])
        assert result == []

    def test_empty_tools_returns_empty(self):
        result = get_sources_for_tools([])
        assert result == []

    def test_deduplicates_shared_sources(self):
        """compliance_check and tax_estimate share irc_1222 and irc_1h; should not duplicate."""
        result = get_sources_for_tools(["compliance_check", "tax_estimate"])
        ids = [s["id"] for s in result]
        assert len(ids) == len(set(ids)), "Duplicate sources returned"

    def test_both_tools_union(self):
        compliance = get_sources_for_tools(["compliance_check"])
        tax = get_sources_for_tools(["tax_estimate"])
        both = get_sources_for_tools(["compliance_check", "tax_estimate"])
        compliance_ids = {s["id"] for s in compliance}
        tax_ids = {s["id"] for s in tax}
        both_ids = {s["id"] for s in both}
        assert both_ids == compliance_ids | tax_ids


# ── get_excerpts_for_tools ───────────────────────────────────────────

class TestGetExcerptsForTools:
    def test_compliance_excerpts_not_empty(self):
        result = get_excerpts_for_tools(["compliance_check"])
        assert result != ""
        assert "Authoritative Tax" in result

    def test_tax_excerpts_not_empty(self):
        result = get_excerpts_for_tools(["tax_estimate"])
        assert result != ""

    def test_unknown_tool_returns_empty_string(self):
        result = get_excerpts_for_tools(["get_portfolio_snapshot"])
        assert result == ""

    def test_empty_tools_returns_empty_string(self):
        result = get_excerpts_for_tools([])
        assert result == ""

    def test_excerpts_contain_key_facts(self):
        result = get_excerpts_for_tools(["compliance_check"])
        assert "30 days" in result
        assert "IRC" in result or "1091" in result

    def test_excerpts_contain_tax_rates(self):
        result = get_excerpts_for_tools(["tax_estimate"])
        assert "0%" in result or "15%" in result or "20%" in result


# ── get_source_by_id ─────────────────────────────────────────────────

class TestGetSourceById:
    def test_found(self):
        s = get_source_by_id("irc_1091")
        assert s is not None
        assert s["id"] == "irc_1091"
        assert "wash" in s["excerpt"].lower()

    def test_not_found(self):
        assert get_source_by_id("nonexistent") is None


# ── _check_authoritative_consistency ─────────────────────────────────

class TestCheckAuthoritativeConsistency:
    def test_correct_wash_sale_window_no_issue(self):
        synthesis = "The wash sale rule applies within 30 days before or after the sale."
        issues = _check_authoritative_consistency(synthesis, {"compliance_check": {}})
        assert issues == []

    def test_wrong_wash_sale_window_flagged(self):
        synthesis = "A wash sale occurs if you repurchase within 45 days of the sale."
        issues = _check_authoritative_consistency(synthesis, {"compliance_check": {}})
        assert any("wash sale" in i.lower() for i in issues)

    def test_60_day_total_window_accepted(self):
        """60-day total window (30+30) should not be flagged."""
        synthesis = "The wash sale window spans 61 days total."
        issues = _check_authoritative_consistency(synthesis, {"compliance_check": {}})
        assert issues == []

    def test_no_wash_sale_mention_no_issue(self):
        synthesis = "Your portfolio looks well-diversified."
        issues = _check_authoritative_consistency(synthesis, {"compliance_check": {}})
        assert issues == []

    def test_no_compliance_tool_no_check(self):
        synthesis = "A wash sale occurs if you repurchase within 45 days."
        issues = _check_authoritative_consistency(synthesis, {"get_market_data": {}})
        assert issues == []

    def test_wrong_longterm_holding_period_months(self):
        synthesis = "Long-term capital gains require holding for 6 months."
        issues = _check_authoritative_consistency(synthesis, {"tax_estimate": {}})
        assert any("long-term" in i.lower() or "1222" in i for i in issues)

    def test_correct_longterm_holding_period_no_issue(self):
        synthesis = "Long-term gains apply to assets held more than 1 year (365 days)."
        issues = _check_authoritative_consistency(synthesis, {"tax_estimate": {}})
        # Should not flag correct holding period
        holding_issues = [i for i in issues if "long-term" in i.lower() or "1222" in i]
        assert holding_issues == []

    def test_no_longterm_mention_no_issue(self):
        synthesis = "Your estimated tax liability is $5,000."
        issues = _check_authoritative_consistency(synthesis, {"tax_estimate": {}})
        assert issues == []
