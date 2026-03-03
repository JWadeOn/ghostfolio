"""Node 2: Passive context preloader — reads cache, never fetches or routes."""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from agent.state import AgentState

logger = logging.getLogger(__name__)

REGIME_TTL = timedelta(minutes=30)
PORTFOLIO_TTL = timedelta(minutes=5)


def _is_fresh(timestamp_str: str | None, ttl: timedelta) -> bool:
    """Check if a cached value is still fresh."""
    if not timestamp_str:
        return False
    try:
        ts = datetime.fromisoformat(timestamp_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - ts < ttl
    except (ValueError, TypeError):
        return False


def check_context_node(state: AgentState) -> dict[str, Any]:
    """Passively preload cached regime/portfolio into state when fresh.

    If cache is stale or missing, passes nothing and lets the ReAct loop
    fetch it naturally on the first tool call. Never blocks, fetches, or routes.
    """
    updates: dict[str, Any] = {}

    regime = state.get("regime")
    regime_ts = state.get("regime_timestamp")
    if regime and _is_fresh(regime_ts, REGIME_TTL):
        logger.info("Regime cache is fresh, preloading into state")
        updates["regime"] = regime
        updates["regime_timestamp"] = regime_ts
    else:
        logger.info("Regime cache stale or missing; ReAct loop will fetch if needed")
        updates["regime"] = None
        updates["regime_timestamp"] = None

    portfolio = state.get("portfolio")
    portfolio_ts = state.get("portfolio_timestamp")
    portfolio_is_empty = (
        isinstance(portfolio, dict)
        and isinstance(portfolio.get("holdings"), list)
        and len(portfolio.get("holdings", [])) == 0
    )
    if portfolio and _is_fresh(portfolio_ts, PORTFOLIO_TTL) and not portfolio_is_empty:
        logger.info("Portfolio cache is fresh, preloading into state")
        updates["portfolio"] = portfolio
        updates["portfolio_timestamp"] = portfolio_ts
    else:
        logger.info("Portfolio cache stale or missing; ReAct loop will fetch if needed")
        updates["portfolio"] = None
        updates["portfolio_timestamp"] = None

    return updates
