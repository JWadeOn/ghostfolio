"""HTTP client for Ghostfolio API calls."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from agent.config import get_settings

logger = logging.getLogger(__name__)

_TIMEOUT = 10.0  # seconds


def _is_jwt(token: str) -> bool:
    """JWTs from Ghostfolio start with eyJ (base64 of {")."""
    return bool(token and token.strip().startswith("eyJ"))


class GhostfolioClient:
    """Simple HTTP client for the Ghostfolio REST API."""

    def __init__(self, base_url: str | None = None, access_token: str | None = None):
        settings = get_settings()
        self.base_url = (base_url or settings.ghostfolio_api_url).rstrip("/")
        raw_token = (access_token or settings.ghostfolio_access_token or "").strip()
        # Ghostfolio portfolio/account routes require a JWT. The value in .env is the
        # "security token" (access token); we must exchange it for a JWT via auth/anonymous.
        if raw_token and not _is_jwt(raw_token):
            self.access_token = self._exchange_for_jwt(raw_token)
        else:
            self.access_token = raw_token or None
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=_TIMEOUT,
            headers=self._auth_headers(),
        )

    def _exchange_for_jwt(self, security_token: str) -> str | None:
        """Exchange the Ghostfolio security token for a JWT. Returns None on failure."""
        url = f"{self.base_url}/api/v1/auth/anonymous"
        body = {"accessToken": security_token}
        try:
            resp = httpx.post(url, json=body, timeout=_TIMEOUT)
            if resp.status_code == 403:
                logger.warning(
                    "Ghostfolio returned 403 Forbidden on auth/anonymous. "
                    "The security token in GHOSTFOLIO_ACCESS_TOKEN does not match Ghostfolio's stored hash. "
                    "Ensure the token is the one currently in Ghostfolio (generate a new one in Settings → Account if needed) "
                    "and that Ghostfolio's ACCESS_TOKEN_SALT has not changed since the token was created."
                )
                return None
            resp.raise_for_status()
            data = resp.json()
            jwt = data.get("authToken")
            if jwt:
                logger.info("Exchanged security token for JWT successfully")
                return jwt
        except Exception as e:
            logger.warning("Failed to exchange security token for JWT: %s", e)
        return None

    def _auth_headers(self) -> dict[str, str]:
        if not self.access_token:
            return {}
        return {"Authorization": f"Bearer {self.access_token}"}

    def _get(self, path: str, params: dict | None = None) -> Any:
        """Make a GET request and return JSON response."""
        try:
            resp = self._client.get(path, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError:
            logger.error(f"Ghostfolio unreachable at {self.base_url}")
            return {"error": "Ghostfolio is unreachable. Is it running?"}
        except httpx.HTTPStatusError as e:
            logger.error(f"Ghostfolio API error: {e.response.status_code}")
            return {"error": f"API returned {e.response.status_code}: {e.response.text}"}
        except Exception as e:
            logger.error(f"Ghostfolio request failed: {e}")
            return {"error": str(e)}

    def _post(self, path: str, json_body: dict | None = None) -> Any:
        try:
            resp = self._client.post(path, json=json_body)
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError:
            return {"error": "Ghostfolio is unreachable. Is it running?"}
        except httpx.HTTPStatusError as e:
            return {"error": f"API returned {e.response.status_code}: {e.response.text}"}
        except Exception as e:
            return {"error": str(e)}

    # --- Portfolio ---

    def get_holdings(self, range_: str = "max") -> Any:
        return self._get("/api/v1/portfolio/holdings", params={"range": range_})

    def get_performance(self, range_: str = "1d") -> Any:
        # Ghostfolio exposes performance under API v2 only
        return self._get("/api/v2/portfolio/performance", params={"range": range_})

    def get_portfolio_details(self, range_: str = "max") -> Any:
        return self._get("/api/v1/portfolio/details", params={"range": range_})

    # --- Accounts ---

    def get_accounts(self) -> Any:
        return self._get("/api/v1/account")

    # --- Orders ---

    def get_orders(self, **filters) -> Any:
        return self._get("/api/v1/order", params=filters)

    def create_order(self, payload: dict) -> Any:
        """Create a portfolio activity (order) via POST /api/v1/order.

        Payload must match CreateOrderDto: currency, date (ISO8601), fee, quantity,
        symbol, type (BUY, SELL, DIVIDEND, FEE, INTEREST, LIABILITY), unitPrice;
        optional: accountId, comment, dataSource, tags, updateAccountBalance.
        """
        return self._post("/api/v1/order", json_body=payload)

    # --- Watchlist ---

    def get_watchlist(self) -> Any:
        return self._get("/api/v1/watchlist")

    # --- Symbols ---

    def lookup_symbol(self, query: str) -> Any:
        return self._get("/api/v1/symbol/lookup", params={"query": query})

    def get_symbol(self, data_source: str, symbol: str) -> Any:
        return self._get(f"/api/v1/symbol/{data_source}/{symbol}")

    # --- Health ---

    def health_check(self) -> bool:
        """Return True if Ghostfolio is reachable."""
        try:
            resp = self._client.get("/api/v1/info")
            return resp.status_code == 200
        except Exception:
            return False

    def close(self):
        self._client.close()
