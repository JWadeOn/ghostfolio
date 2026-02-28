"""Unit tests for the transaction_categorize tool."""

from unittest.mock import MagicMock
from agent.tools.transaction_categorize import transaction_categorize


def test_categorizes_provided_transactions():
    txns = [
        {"id": "1", "type": "BUY", "symbol": "AAPL", "date": "2025-01-10", "quantity": 5, "unitPrice": 200, "fee": 0, "currency": "USD", "tags": [{"name": "DCA"}]},
        {"id": "2", "type": "SELL", "symbol": "MSFT", "date": "2025-01-15", "quantity": 3, "unitPrice": 400, "fee": 1, "currency": "USD", "tags": []},
        {"id": "3", "type": "DIVIDEND", "symbol": "AAPL", "date": "2025-02-01", "quantity": 0, "unitPrice": 0.22, "fee": 0, "currency": "USD", "tags": []},
    ]
    result = transaction_categorize(transactions=txns)

    assert "error" not in result
    assert len(result["categories"]) == 3
    assert result["categories"][0]["category"] == "Purchase"
    assert result["categories"][0]["subcategory"] == "DCA"
    assert result["categories"][1]["category"] == "Sale"
    assert result["categories"][2]["category"] == "Dividend"


def test_detects_dca_pattern():
    txns = [
        {"id": str(i), "type": "BUY", "symbol": "VTI", "date": f"2025-0{m}-15", "quantity": 10, "unitPrice": 250, "fee": 0, "currency": "USD", "tags": []}
        for i, m in enumerate([1, 2, 3, 4, 5], start=1)
    ]
    result = transaction_categorize(transactions=txns)

    pattern_names = [p["name"] for p in result["patterns"]]
    assert "dca" in pattern_names


def test_detects_recurring_dividend():
    txns = [
        {"id": str(i), "type": "DIVIDEND", "symbol": "AAPL", "date": f"2025-0{m}-15", "quantity": 0, "unitPrice": 0.22, "fee": 0, "currency": "USD", "tags": []}
        for i, m in enumerate([1, 4, 7], start=1)
    ]
    result = transaction_categorize(transactions=txns)

    pattern_names = [p["name"] for p in result["patterns"]]
    assert "recurring_dividend" in pattern_names


def test_fetches_from_client_when_no_transactions():
    client = MagicMock()
    client.get_orders.return_value = {
        "activities": [
            {"id": "a1", "type": "BUY", "symbol": "GOOG", "date": "2025-12-01T00:00:00Z", "quantity": 2, "unitPrice": 140, "fee": 0, "currency": "USD", "tags": []},
        ]
    }

    result = transaction_categorize(client=client)
    assert "error" not in result
    assert len(result["categories"]) == 1
    assert result["categories"][0]["symbol"] == "GOOG"


def test_returns_error_when_no_client_and_no_transactions():
    result = transaction_categorize()
    assert "error" in result


# ══════════════════════════════════════════════════════════════════════
# Test include_patterns via get_trade_history
# ══════════════════════════════════════════════════════════════════════

def test_get_trade_history_include_patterns():
    """get_trade_history(include_patterns=True) should add categories and patterns."""
    from agent.tools.history import get_trade_history

    client = MagicMock()
    client.get_orders.return_value = {
        "activities": [
            {"id": "1", "type": "BUY", "symbol": "VTI", "date": "2025-06-15T00:00:00Z",
             "quantity": 10, "unitPrice": 250, "fee": 0, "currency": "USD", "tags": []},
            {"id": "2", "type": "BUY", "symbol": "VTI", "date": "2025-07-15T00:00:00Z",
             "quantity": 10, "unitPrice": 252, "fee": 0, "currency": "USD", "tags": []},
            {"id": "3", "type": "BUY", "symbol": "VTI", "date": "2025-08-15T00:00:00Z",
             "quantity": 10, "unitPrice": 248, "fee": 0, "currency": "USD", "tags": []},
            {"id": "4", "type": "BUY", "symbol": "VTI", "date": "2025-09-15T00:00:00Z",
             "quantity": 10, "unitPrice": 255, "fee": 0, "currency": "USD", "tags": []},
            {"id": "5", "type": "BUY", "symbol": "VTI", "date": "2025-10-15T00:00:00Z",
             "quantity": 10, "unitPrice": 260, "fee": 0, "currency": "USD", "tags": []},
        ]
    }

    result = get_trade_history(time_range="1y", include_patterns=True, client=client)

    assert "error" not in result
    assert "categories" in result
    assert "patterns" in result
    assert len(result["categories"]) == 5
    # DCA pattern should be detected
    pattern_names = [p["name"] for p in result["patterns"]]
    assert "dca" in pattern_names


def test_get_trade_history_no_patterns_by_default():
    """get_trade_history(include_patterns=False) should NOT have categories/patterns keys."""
    from agent.tools.history import get_trade_history

    client = MagicMock()
    client.get_orders.return_value = {
        "activities": [
            {"id": "1", "type": "BUY", "symbol": "AAPL", "date": "2025-01-10T00:00:00Z",
             "quantity": 5, "unitPrice": 200, "fee": 0, "currency": "USD", "tags": []},
        ]
    }

    result = get_trade_history(time_range="1y", client=client)

    assert "categories" not in result
    assert "patterns" not in result
