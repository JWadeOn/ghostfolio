"""Canonical mock responses for Ghostfolio API — portfolio, orders, symbol lookup, create_activity."""

# Portfolio holdings (GET /api/v1/portfolio/holdings)
MOCK_HOLDINGS = {
    "holdings": [
        {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "quantity": 10,
            "currency": "USD",
            "marketPrice": 187.50,
            "valueInBaseCurrency": 1875.00,
            "investment": 1500.00,
            "allocationInPercentage": 0.35,
            "netPerformancePercentage": 25.0,
            "netPerformance": 375.0,
            "assetClass": "EQUITY",
            "assetSubClass": "STOCK",
            "dataSource": "YAHOO",
            "sectors": ["Technology"],
        },
        {
            "symbol": "GOOG",
            "name": "Alphabet Inc.",
            "quantity": 5,
            "currency": "USD",
            "marketPrice": 142.00,
            "valueInBaseCurrency": 710.00,
            "investment": 600.00,
            "allocationInPercentage": 0.15,
            "netPerformancePercentage": 18.33,
            "netPerformance": 110.00,
            "assetClass": "EQUITY",
            "assetSubClass": "STOCK",
            "dataSource": "YAHOO",
            "sectors": ["Technology"],
        },
    ]
}

# Performance (GET /api/v2/portfolio/performance)
MOCK_PERFORMANCE = {
    "performance": {
        "currentValueInBaseCurrency": 5357.50,
        "currentNetWorth": 5357.50,
        "netPerformance": 485.00,
        "netPerformancePercentage": 9.95,
        "grossPerformance": 500.00,
        "totalInvestment": 4872.50,
    }
}

# Accounts (GET /api/v1/account)
MOCK_ACCOUNTS = [
    {
        "id": "account-1",
        "name": "Brokerage",
        "balance": 1000.00,
        "currency": "USD",
        "platform": {"name": "Ghostfolio"},
        "value": 4357.50,
    }
]

# Orders/activities (GET /api/v1/order)
MOCK_ORDERS = {
    "activities": [
        {
            "id": "order-1",
            "symbol": "AAPL",
            "SymbolProfile": {"symbol": "AAPL", "currency": "USD"},
            "type": "BUY",
            "date": "2025-01-15",
            "quantity": 10,
            "unitPrice": 150.00,
            "fee": 0,
            "currency": "USD",
        },
        {
            "id": "order-2",
            "symbol": "GOOG",
            "SymbolProfile": {"symbol": "GOOG", "currency": "USD"},
            "type": "BUY",
            "date": "2025-02-01",
            "quantity": 5,
            "unitPrice": 120.00,
            "fee": 0,
            "currency": "USD",
        },
    ]
}

# Symbol lookup responses (GET /api/v1/symbol/lookup?query=...)
def get_mock_symbol_lookup(query: str) -> dict:
    q = (query or "").strip().upper()
    if not q:
        return {"items": [], "total": 0}
    # Map common queries to matches
    if q in ("APPLE", "AAPL"):
        return {
            "items": [
                {
                    "symbol": "AAPL",
                    "name": "Apple Inc.",
                    "currency": "USD",
                    "dataSource": "YAHOO",
                    "assetClass": "EQUITY",
                    "assetSubClass": "STOCK",
                }
            ],
            "total": 1,
        }
    if q in ("TESLA", "TSLA"):
        return {
            "items": [
                {
                    "symbol": "TSLA",
                    "name": "Tesla Inc.",
                    "currency": "USD",
                    "dataSource": "YAHOO",
                    "assetClass": "EQUITY",
                    "assetSubClass": "STOCK",
                }
            ],
            "total": 1,
        }
    if q in ("MICROSOFT", "MSFT", "GOOGLE", "GOOG", "ALPHABET"):
        sym = "MSFT" if "MSFT" in q or "MICROSOFT" in q else "GOOG"
        name = "Microsoft Corporation" if sym == "MSFT" else "Alphabet Inc."
        return {
            "items": [
                {
                    "symbol": sym,
                    "name": name,
                    "currency": "USD",
                    "dataSource": "YAHOO",
                    "assetClass": "EQUITY",
                    "assetSubClass": "STOCK",
                }
            ],
            "total": 1,
        }
    # Default: return one generic match so agent gets a result
    return {
        "items": [
            {
                "symbol": q[:6],
                "name": f"Security {q}",
                "currency": "USD",
                "dataSource": "YAHOO",
                "assetClass": "EQUITY",
                "assetSubClass": "STOCK",
            }
        ],
        "total": 1,
    }


# Create order response (POST /api/v1/order)
def get_mock_create_order_response(payload: dict) -> dict:
    """Return a success-shaped order object for create_order."""
    return {
        "id": "mock-order-" + (payload.get("date", "")[:10].replace("-", "")),
        "symbol": payload.get("symbol", ""),
        "type": payload.get("type", "BUY"),
        "date": payload.get("date", ""),
        "quantity": payload.get("quantity", 0),
        "unitPrice": payload.get("unitPrice", 0),
        "fee": payload.get("fee", 0),
        "currency": payload.get("currency", "USD"),
        "comment": payload.get("comment"),
    }
