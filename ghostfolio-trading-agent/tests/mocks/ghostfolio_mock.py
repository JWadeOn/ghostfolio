"""Mock Ghostfolio client for eval runs — no HTTP calls."""

from __future__ import annotations

from tests.mocks.ghostfolio_responses import (
    MOCK_HOLDINGS,
    MOCK_PERFORMANCE,
    MOCK_ACCOUNTS,
    MOCK_ORDERS,
    get_mock_symbol_lookup,
    get_mock_create_order_response,
)


class MockGhostfolioClient:
    """Drop-in mock for GhostfolioClient. Returns canned responses."""

    def __init__(self, base_url: str | None = None, access_token: str | None = None):
        self.base_url = base_url or "http://localhost:3333"
        self.access_token = access_token

    def get_holdings(self, range_: str = "max"):
        return MOCK_HOLDINGS

    def get_performance(self, range_: str = "1d"):
        return MOCK_PERFORMANCE

    def get_portfolio_details(self, range_: str = "max"):
        return {"holdings": MOCK_HOLDINGS.get("holdings", []), "range": range_}

    def get_accounts(self):
        return MOCK_ACCOUNTS

    def get_orders(self, **filters):
        return MOCK_ORDERS

    def create_order(self, payload: dict):
        return get_mock_create_order_response(payload)

    def get_watchlist(self):
        return []

    def create_watchlist_item(self, data_source: str, symbol: str):
        return {"success": True, "symbol": symbol, "data_source": data_source}

    def lookup_symbol(self, query: str):
        return get_mock_symbol_lookup(query)

    def get_symbol(self, data_source: str, symbol: str):
        return {"symbol": symbol, "dataSource": data_source}

    def health_check(self) -> bool:
        return True

    def close(self):
        pass
