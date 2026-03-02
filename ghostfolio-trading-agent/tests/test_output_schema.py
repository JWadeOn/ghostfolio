"""Tests for output validation via AgentResponse schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent.schemas import AgentResponse, Citation, Observability
from agent.nodes.formatter import format_output_node, DISCLAIMER


def _minimal_response(**overrides) -> dict:
    """Return a minimal valid response dict with optional overrides."""
    base = {
        "summary": "Test summary",
        "confidence": 75,
        "intent": "general",
        "data": {},
        "citations": [],
        "warnings": [],
        "tools_used": [],
        "authoritative_sources": [],
        "disclaimer": DISCLAIMER,
        "observability": {},
    }
    base.update(overrides)
    return base


class TestAgentResponseValidation:
    """Unit tests for the AgentResponse Pydantic model."""

    def test_valid_response_passes(self):
        resp = AgentResponse(**_minimal_response())
        assert resp.summary == "Test summary"
        assert resp.confidence == 75
        assert resp.intent == "general"

    def test_empty_summary_rejected(self):
        with pytest.raises(ValidationError, match="String should have at least 1 character"):
            AgentResponse(**_minimal_response(summary=""))

    def test_confidence_clamped_high(self):
        resp = AgentResponse(**_minimal_response(confidence=150))
        assert resp.confidence == 100

    def test_confidence_clamped_low(self):
        resp = AgentResponse(**_minimal_response(confidence=-20))
        assert resp.confidence == 0

    def test_confidence_boundary_zero(self):
        resp = AgentResponse(**_minimal_response(confidence=0))
        assert resp.confidence == 0

    def test_confidence_boundary_hundred(self):
        resp = AgentResponse(**_minimal_response(confidence=100))
        assert resp.confidence == 100

    def test_missing_required_summary_rejected(self):
        data = _minimal_response()
        del data["summary"]
        with pytest.raises(ValidationError):
            AgentResponse(**data)

    def test_missing_required_confidence_rejected(self):
        data = _minimal_response()
        del data["confidence"]
        with pytest.raises(ValidationError):
            AgentResponse(**data)

    def test_missing_required_intent_rejected(self):
        data = _minimal_response()
        del data["intent"]
        with pytest.raises(ValidationError):
            AgentResponse(**data)

    def test_citations_validated(self):
        citations = [
            {"claim": "Price is $100", "source": "get_market_data", "verified": True},
            {"claim": "RSI is 65%", "source": None, "verified": False},
        ]
        resp = AgentResponse(**_minimal_response(citations=citations))
        assert len(resp.citations) == 2
        assert resp.citations[0].verified is True
        assert resp.citations[1].source is None

    def test_invalid_citation_rejected(self):
        citations = [{"not_a_field": "bad"}]
        with pytest.raises(ValidationError):
            AgentResponse(**_minimal_response(citations=citations))

    def test_escalation_defaults(self):
        resp = AgentResponse(**_minimal_response())
        assert resp.escalated is False
        assert resp.escalation_reason is None

    def test_escalation_fields_set(self):
        resp = AgentResponse(**_minimal_response(
            escalated=True,
            escalation_reason="low_confidence (15)",
        ))
        assert resp.escalated is True
        assert resp.escalation_reason == "low_confidence (15)"

    def test_observability_defaults(self):
        resp = AgentResponse(**_minimal_response(observability={}))
        assert resp.observability.token_usage == {}
        assert resp.observability.node_latencies == {}
        assert resp.observability.error_log == []
        assert resp.observability.trace_log == []
        assert resp.observability.total_latency_seconds is None

    def test_model_dump_roundtrip(self):
        resp = AgentResponse(**_minimal_response())
        dumped = resp.model_dump()
        resp2 = AgentResponse(**dumped)
        assert resp == resp2


class TestFormatOutputNodeIntegration:
    """Integration tests: format_output_node produces schema-valid output."""

    def test_minimal_state_produces_valid_output(self):
        state = {
            "synthesis": "Here is your analysis.",
            "tool_results": {},
            "tools_called": [],
            "verification_result": {"confidence": 80, "passed": True, "issues": []},
            "token_usage": {},
            "node_latencies": {},
            "error_log": [],
            "trace_log": [],
        }
        result = format_output_node(state)
        response = result["response"]
        # Should be schema-valid (already validated inside the function)
        validated = AgentResponse(**response)
        assert validated.summary == "Here is your analysis."
        assert validated.confidence == 80

    def test_empty_synthesis_triggers_fallback(self):
        state = {
            "synthesis": "",
            "tool_results": {},
            "tools_called": [],
            "verification_result": {"confidence": 50, "passed": True, "issues": []},
            "token_usage": {},
            "node_latencies": {},
            "error_log": [],
            "trace_log": [],
        }
        result = format_output_node(state)
        response = result["response"]
        # Should have fallen back due to empty summary validation failure
        assert "validation error" in response["warnings"][-1].lower() or response["summary"] != ""

    def test_output_contains_escalation_fields(self):
        state = {
            "synthesis": "Analysis complete.",
            "tool_results": {},
            "tools_called": [],
            "verification_result": {"confidence": 70, "passed": True, "issues": []},
            "token_usage": {},
            "node_latencies": {},
            "error_log": [],
            "trace_log": [],
        }
        result = format_output_node(state)
        response = result["response"]
        assert "escalated" in response
        assert "escalation_reason" in response
