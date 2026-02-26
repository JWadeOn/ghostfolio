"""Unit tests for create_activity tool."""

import pytest
from unittest.mock import MagicMock

from agent.tools.activities import create_activity


class TestCreateActivity:
    """Tests for create_activity tool."""

    def test_returns_error_when_client_is_none(self):
        """When client is None, returns a clear error asking user to connect Ghostfolio."""
        result = create_activity(
            activity_type="BUY",
            symbol="AAPL",
            quantity=10,
            unit_price=150.0,
            currency="USD",
            date="2025-02-26",
            client=None,
        )
        assert "error" in result
        assert "Ghostfolio" in result["error"] and "connect" in result["error"].lower()

    def test_returns_error_for_invalid_activity_type(self):
        """When activity_type is invalid, returns error listing valid types."""
        mock_client = MagicMock()
        result = create_activity(
            activity_type="INVALID",
            symbol="AAPL",
            quantity=10,
            unit_price=150.0,
            currency="USD",
            date="2025-02-26",
            client=mock_client,
        )
        assert "error" in result
        assert "Invalid activity_type" in result["error"]
        for t in ("BUY", "SELL"):
            assert t in result["error"]
        mock_client.create_order.assert_not_called()

    def test_returns_error_for_empty_symbol(self):
        """When symbol is empty, returns error."""
        mock_client = MagicMock()
        result = create_activity(
            activity_type="BUY",
            symbol="",
            quantity=10,
            unit_price=150.0,
            currency="USD",
            date="2025-02-26",
            client=mock_client,
        )
        assert "error" in result
        assert "symbol" in result["error"].lower()
        mock_client.create_order.assert_not_called()
