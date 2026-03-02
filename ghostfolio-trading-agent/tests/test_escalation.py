"""Tests for human-in-the-loop escalation logic."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.app import _check_escalation


def _make_settings(threshold: int = 30, enabled: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        escalation_confidence_threshold=threshold,
        escalation_enabled=enabled,
    )


def _make_response(
    confidence: int = 75,
    intent: str = "general",
    warnings: list[str] | None = None,
    summary: str = "Here is your analysis.",
) -> dict:
    return {
        "confidence": confidence,
        "intent": intent,
        "warnings": warnings or [],
        "summary": summary,
    }


class TestCheckEscalation:
    """Unit tests for _check_escalation."""

    def test_low_confidence_triggers(self):
        result = _check_escalation(
            _make_response(confidence=15),
            _make_settings(threshold=30),
        )
        assert result is not None
        assert "low_confidence (15)" in result

    def test_normal_confidence_does_not_trigger(self):
        result = _check_escalation(
            _make_response(confidence=75),
            _make_settings(threshold=30),
        )
        assert result is None

    def test_boundary_at_threshold_does_not_trigger(self):
        result = _check_escalation(
            _make_response(confidence=30),
            _make_settings(threshold=30),
        )
        assert result is None

    def test_boundary_just_below_threshold_triggers(self):
        result = _check_escalation(
            _make_response(confidence=29),
            _make_settings(threshold=30),
        )
        assert result is not None
        assert "low_confidence" in result

    def test_guardrail_on_trade_intent_triggers(self):
        result = _check_escalation(
            _make_response(
                confidence=75,
                intent="risk_check",
                warnings=["Position size violation detected"],
            ),
            _make_settings(),
        )
        assert result is not None
        assert "guardrail_violation" in result

    def test_guardrail_on_non_trade_intent_does_not_trigger(self):
        result = _check_escalation(
            _make_response(
                confidence=75,
                intent="general",
                warnings=["Position size violation detected"],
            ),
            _make_settings(),
        )
        assert result is None

    def test_guarantee_language_in_summary_triggers(self):
        result = _check_escalation(
            _make_response(
                confidence=75,
                summary="This investment is guaranteed to double.",
            ),
            _make_settings(),
        )
        assert result is not None
        assert "guarantee_language" in result

    def test_guarantee_language_in_warnings_triggers(self):
        result = _check_escalation(
            _make_response(
                confidence=75,
                warnings=["This is a risk-free opportunity"],
            ),
            _make_settings(),
        )
        assert result is not None
        assert "guarantee_language" in result

    def test_no_risk_pattern_triggers(self):
        result = _check_escalation(
            _make_response(summary="There is no risk in this trade."),
            _make_settings(),
        )
        assert result is not None
        assert "guarantee_language" in result

    def test_multiple_reasons_combined(self):
        result = _check_escalation(
            _make_response(
                confidence=10,
                intent="create_activity",
                warnings=["Guardrail violation: sector concentration"],
                summary="This is guaranteed to work.",
            ),
            _make_settings(threshold=30),
        )
        assert result is not None
        assert "low_confidence" in result
        assert "guardrail_violation" in result
        assert "guarantee_language" in result

    def test_escalation_disabled_never_triggers(self):
        result = _check_escalation(
            _make_response(confidence=5),
            _make_settings(enabled=False),
        )
        assert result is None

    def test_cannot_lose_pattern_triggers(self):
        result = _check_escalation(
            _make_response(summary="You cannot lose with this strategy."),
            _make_settings(),
        )
        assert result is not None
        assert "guarantee_language" in result

    def test_clean_response_no_escalation(self):
        result = _check_escalation(
            _make_response(
                confidence=80,
                intent="price_quote",
                summary="AAPL is currently trading at $150.25.",
            ),
            _make_settings(),
        )
        assert result is None
