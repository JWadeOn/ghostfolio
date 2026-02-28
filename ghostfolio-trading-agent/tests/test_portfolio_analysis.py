"""Unit tests for the portfolio_analysis tool and get_portfolio_snapshot enhancements."""

from unittest.mock import MagicMock, patch
from agent.tools.portfolio_analysis import portfolio_analysis
from agent.tools.portfolio import get_portfolio_snapshot


def _mock_client(holdings_resp=None, perf_resp=None, accounts_resp=None):
    client = MagicMock()
    client.get_holdings.return_value = holdings_resp or {"holdings": []}
    client.get_performance.return_value = perf_resp or {"performance": {}}
    client.get_accounts.return_value = accounts_resp or []
    return client


def test_full_portfolio_returns_holdings_and_allocation():
    client = _mock_client(
        holdings_resp={
            "holdings": [
                {
                    "symbol": "AAPL",
                    "name": "Apple Inc.",
                    "quantity": 10,
                    "marketPrice": 200,
                    "valueInBaseCurrency": 2000,
                    "allocationInPercentage": 0.4,
                    "investment": 1500,
                    "netPerformancePercentage": 0.33,
                    "netPerformance": 500,
                    "currency": "USD",
                    "assetClass": "EQUITY",
                    "sectors": [],
                },
                {
                    "symbol": "MSFT",
                    "name": "Microsoft",
                    "quantity": 5,
                    "marketPrice": 600,
                    "valueInBaseCurrency": 3000,
                    "allocationInPercentage": 0.6,
                    "investment": 2500,
                    "netPerformancePercentage": 0.2,
                    "netPerformance": 500,
                    "currency": "USD",
                    "assetClass": "EQUITY",
                    "sectors": [],
                },
            ]
        },
        perf_resp={
            "performance": {
                "currentValueInBaseCurrency": 5000,
                "netPerformance": 1000,
                "netPerformancePercentage": 0.25,
                "grossPerformance": 1050,
                "totalInvestment": 4000,
            }
        },
    )

    result = portfolio_analysis(client=client)

    assert "error" not in result
    assert len(result["holdings"]) == 2
    assert result["allocation"]["by_symbol"]["AAPL"] == 40.0
    assert result["allocation"]["by_symbol"]["MSFT"] == 60.0
    assert result["allocation"]["by_asset_class"]["EQUITY"] == 100.0
    assert result["performance"]["current_value"] == 5000
    assert result["account_id"] is None
    assert result["summary"]["holding_count"] == 2


def test_account_scoped_passes_filter():
    client = _mock_client(
        accounts_resp=[{"id": "acc-1", "name": "Brokerage"}],
        holdings_resp={"holdings": [{"symbol": "GOOG", "quantity": 2, "valueInBaseCurrency": 300, "allocationInPercentage": 1.0, "assetClass": "EQUITY"}]},
        perf_resp={"performance": {"currentValueInBaseCurrency": 300}},
    )

    result = portfolio_analysis(account_id="acc-1", client=client)
    assert "error" not in result
    assert result["account_id"] == "acc-1"
    client.get_holdings.assert_called_with(accounts="acc-1")
    client.get_performance.assert_called_with(accounts="acc-1")


def test_unknown_account_returns_error():
    client = _mock_client(accounts_resp=[{"id": "acc-1"}])

    result = portfolio_analysis(account_id="no-such-id", client=client)
    assert "error" in result
    assert "not found" in result["error"].lower()


def test_api_error_propagated():
    client = _mock_client(holdings_resp={"error": "Unauthorized"})

    result = portfolio_analysis(client=client)
    assert "error" in result


# ══════════════════════════════════════════════════════════════════════
# Tests for get_portfolio_snapshot enhancements (account_id + allocation)
# ══════════════════════════════════════════════════════════════════════


def _mock_gf_client(holdings_resp=None, perf_resp=None, accounts_resp=None, orders_resp=None):
    client = MagicMock()
    client.get_holdings.return_value = holdings_resp or {"holdings": []}
    client.get_performance.return_value = perf_resp or {"performance": {}}
    client.get_accounts.return_value = accounts_resp or []
    client.get_orders.return_value = orders_resp or []
    return client


@patch("agent.tools.portfolio.get_latest_prices", return_value={})
def test_snapshot_includes_allocation(mock_prices):
    client = _mock_gf_client(
        holdings_resp={
            "holdings": [
                {
                    "symbol": "AAPL", "name": "Apple", "quantity": 10,
                    "marketPrice": 200, "valueInBaseCurrency": 2000,
                    "allocationInPercentage": 0.4, "investment": 1500,
                    "netPerformancePercentage": 0.33, "netPerformance": 500,
                    "currency": "USD", "assetClass": "EQUITY", "sectors": [],
                },
                {
                    "symbol": "MSFT", "name": "Microsoft", "quantity": 5,
                    "marketPrice": 600, "valueInBaseCurrency": 3000,
                    "allocationInPercentage": 0.6, "investment": 2500,
                    "netPerformancePercentage": 0.2, "netPerformance": 500,
                    "currency": "USD", "assetClass": "EQUITY", "sectors": [],
                },
            ]
        },
        perf_resp={"performance": {"currentValueInBaseCurrency": 5000, "totalInvestment": 4000}},
    )

    result = get_portfolio_snapshot(client=client)

    assert "allocation" in result
    assert result["allocation"]["by_symbol"]["AAPL"] == 40.0
    assert result["allocation"]["by_symbol"]["MSFT"] == 60.0
    assert result["allocation"]["by_asset_class"]["EQUITY"] == 100.0
    assert result["account_id"] is None


@patch("agent.tools.portfolio.get_latest_prices", return_value={})
def test_snapshot_with_account_id(mock_prices):
    client = _mock_gf_client(
        accounts_resp=[{"id": "acc-1", "name": "Brokerage", "balance": 1000, "currency": "USD"}],
        holdings_resp={"holdings": [
            {"symbol": "GOOG", "quantity": 2, "valueInBaseCurrency": 300,
             "allocationInPercentage": 1.0, "assetClass": "EQUITY", "marketPrice": 150},
        ]},
        perf_resp={"performance": {"currentValueInBaseCurrency": 300}},
    )

    result = get_portfolio_snapshot(client=client, account_id="acc-1")
    assert "error" not in result
    assert result["account_id"] == "acc-1"
    client.get_holdings.assert_called_with(accounts="acc-1")
    client.get_performance.assert_called_with(accounts="acc-1")


@patch("agent.tools.portfolio.get_latest_prices", return_value={})
def test_snapshot_unknown_account_returns_error(mock_prices):
    client = _mock_gf_client(accounts_resp=[{"id": "acc-1"}])

    result = get_portfolio_snapshot(client=client, account_id="no-such-id")
    assert "error" in result
    assert "not found" in result["error"].lower()
