"""Unit tests for the compliance_check tool."""

from unittest.mock import MagicMock
from agent.tools.compliance_check import compliance_check


def _mock_client(orders=None, holdings=None):
    client = MagicMock()
    client.get_orders.return_value = {"activities": orders or []}
    client.get_holdings.return_value = {"holdings": holdings or []}
    return client


class TestWashSale:
    def test_flags_buy_after_loss_sale(self):
        """Buying within 30 days of a loss sale should trigger wash sale."""
        orders = [
            {"type": "BUY", "symbol": "AAPL", "date": "2026-01-01", "quantity": 10, "unitPrice": 200},
            {"type": "SELL", "symbol": "AAPL", "date": "2026-02-10", "quantity": 10, "unitPrice": 180},
        ]
        client = _mock_client(orders=orders)

        txn = {"type": "BUY", "symbol": "AAPL", "date": "2026-02-20", "quantity": 5, "unitPrice": 185}
        result = compliance_check(txn, ["wash_sale"], client=client)

        assert any(f["rule"] == "wash_sale" for f in result["violations"])
        assert result["passed"] is False

    def test_no_wash_sale_when_sale_was_profit(self):
        """Repurchasing after a profitable sale is not a wash sale."""
        orders = [
            {"type": "BUY", "symbol": "AAPL", "date": "2026-01-01", "quantity": 10, "unitPrice": 150},
            {"type": "SELL", "symbol": "AAPL", "date": "2026-02-10", "quantity": 10, "unitPrice": 200},
        ]
        client = _mock_client(orders=orders)

        txn = {"type": "BUY", "symbol": "AAPL", "date": "2026-02-20", "quantity": 5, "unitPrice": 195}
        result = compliance_check(txn, ["wash_sale"], client=client)

        assert not any(f["rule"] == "wash_sale" and f["severity"] == "violation" for f in result["violations"])

    def test_warns_on_loss_sale(self):
        """Selling at a loss should warn about wash sale risk."""
        orders = [
            {"type": "BUY", "symbol": "TSLA", "date": "2026-01-01", "quantity": 10, "unitPrice": 300},
        ]
        client = _mock_client(orders=orders)

        txn = {"type": "SELL", "symbol": "TSLA", "date": "2026-02-10", "quantity": 5, "unitPrice": 250}
        result = compliance_check(txn, ["wash_sale"], client=client)

        assert any(f["rule"] == "wash_sale" for f in result["warnings"])


class TestCapitalGains:
    def test_classifies_short_term(self):
        """Sale within a year should be short-term."""
        orders = [
            {"type": "BUY", "symbol": "MSFT", "date": "2025-06-01", "quantity": 10, "unitPrice": 400},
        ]
        client = _mock_client(orders=orders)

        txn = {"type": "SELL", "symbol": "MSFT", "date": "2025-10-01", "quantity": 10, "unitPrice": 450}
        result = compliance_check(txn, ["capital_gains"], client=client)

        cg = [f for f in result["warnings"] if f["rule"] == "capital_gains"]
        assert len(cg) == 1
        assert cg[0]["classification"] == "short-term"

    def test_classifies_long_term(self):
        """Sale after a year should be long-term."""
        orders = [
            {"type": "BUY", "symbol": "MSFT", "date": "2024-01-01", "quantity": 10, "unitPrice": 350},
        ]
        client = _mock_client(orders=orders)

        txn = {"type": "SELL", "symbol": "MSFT", "date": "2025-06-01", "quantity": 10, "unitPrice": 450}
        result = compliance_check(txn, ["capital_gains"], client=client)

        warnings_and_info = result["warnings"]
        cg = [f for f in warnings_and_info if f["rule"] == "capital_gains"]
        assert len(cg) == 1
        assert cg[0]["classification"] == "long-term"

    def test_no_op_for_buy(self):
        """capital_gains check only applies to sells."""
        client = _mock_client()
        txn = {"type": "BUY", "symbol": "AAPL", "date": "2025-06-01", "quantity": 5, "unitPrice": 200}
        result = compliance_check(txn, ["capital_gains"], client=client)
        assert len(result["violations"]) == 0
        assert len(result["warnings"]) == 0


class TestTaxLossHarvesting:
    def test_identifies_harvestable_loss_on_sell(self):
        """Selling at a loss should flag as harvestable."""
        orders = [
            {"type": "BUY", "symbol": "GOOG", "date": "2025-01-01", "quantity": 5, "unitPrice": 200},
        ]
        client = _mock_client(orders=orders)

        txn = {"type": "SELL", "symbol": "GOOG", "date": "2025-06-01", "quantity": 5, "unitPrice": 150}
        result = compliance_check(txn, ["tax_loss_harvesting"], client=client)

        tlh = [f for f in result["warnings"] if f["rule"] == "tax_loss_harvesting"]
        assert len(tlh) == 1
        assert "harvesting" in tlh[0]["message"].lower()

    def test_suggests_harvesting_other_losers_on_buy(self):
        """When buying, suggest harvesting losses in other losing positions."""
        holdings = [
            {"symbol": "MSFT", "valueInBaseCurrency": 800, "investment": 1000},
        ]
        client = _mock_client(holdings=holdings)

        txn = {"type": "BUY", "symbol": "AAPL", "date": "2025-06-01", "quantity": 5, "unitPrice": 200}
        result = compliance_check(txn, ["tax_loss_harvesting"], client=client)

        tlh = [f for f in result["warnings"] if f["rule"] == "tax_loss_harvesting"]
        assert len(tlh) >= 1
        assert "MSFT" in tlh[0]["message"]


class TestStubRegulation:
    def test_unknown_regulation_returns_stub(self):
        result = compliance_check(
            {"type": "BUY", "symbol": "AAPL", "date": "2025-01-01"},
            ["unknown_rule"],
        )
        assert result["passed"] is True
        assert any("not yet implemented" in f["message"] for f in result["warnings"])


class TestMultipleRegulations:
    def test_checks_all_requested(self):
        orders = [
            {"type": "BUY", "symbol": "AAPL", "date": "2026-01-01", "quantity": 10, "unitPrice": 200},
            {"type": "SELL", "symbol": "AAPL", "date": "2026-02-10", "quantity": 10, "unitPrice": 180},
        ]
        client = _mock_client(orders=orders)

        txn = {"type": "BUY", "symbol": "AAPL", "date": "2026-02-20", "quantity": 5, "unitPrice": 185}
        result = compliance_check(txn, ["wash_sale", "capital_gains", "tax_loss_harvesting"], client=client)

        rules_found = set()
        for f in result["violations"] + result["warnings"]:
            rules_found.add(f["rule"])
        assert "wash_sale" in rules_found
