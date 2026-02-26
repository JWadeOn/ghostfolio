"""Unit tests for GhostfolioClient."""

import pytest
from unittest.mock import patch, MagicMock

from agent.ghostfolio_client import GhostfolioClient


class TestGhostfolioClientCreateOrder:
    """Tests for GhostfolioClient.create_order."""

    @patch.object(GhostfolioClient, "_post")
    def test_create_order_calls_post_with_path_and_payload(self, mock_post):
        """create_order calls _post with /api/v1/order and the given payload."""
        mock_post.return_value = {"id": "order-123", "symbol": "AAPL", "type": "BUY"}
        # Use a token starting with eyJ so the client skips JWT exchange
        client = GhostfolioClient(
            base_url="http://localhost:3333", access_token="eyJfake-jwt-token"
        )

        payload = {
            "currency": "USD",
            "date": "2025-02-26",
            "fee": 0,
            "quantity": 10,
            "symbol": "AAPL",
            "type": "BUY",
            "unitPrice": 150.0,
        }
        result = client.create_order(payload)

        mock_post.assert_called_once_with("/api/v1/order", json_body=payload)
        assert result == {"id": "order-123", "symbol": "AAPL", "type": "BUY"}

    @patch.object(GhostfolioClient, "_post")
    def test_create_order_returns_error_from_post(self, mock_post):
        """create_order returns the error dict when _post returns an error."""
        mock_post.return_value = {"error": "API returned 400: Bad Request"}
        client = GhostfolioClient(
            base_url="http://localhost:3333", access_token="eyJfake-jwt-token"
        )

        payload = {
            "currency": "USD",
            "date": "2025-02-26",
            "fee": 0,
            "quantity": 10,
            "symbol": "INVALID",
            "type": "BUY",
            "unitPrice": 100,
        }
        result = client.create_order(payload)

        assert result == {"error": "API returned 400: Bad Request"}
