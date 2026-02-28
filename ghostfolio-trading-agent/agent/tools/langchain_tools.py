"""LangChain tool wrappers for the portfolio intelligence agent."""

from __future__ import annotations

from typing import Any, Optional

from langchain_core.tools import tool

from agent.tools.market_data import get_market_data as _get_market_data
from agent.tools.portfolio import get_portfolio_snapshot as _get_portfolio_snapshot
from agent.tools.regime import detect_regime as _detect_regime
from agent.tools.scanner import scan_strategies as _scan_strategies
from agent.tools.risk import guardrails_check as _guardrails_check
from agent.tools.history import get_trade_history as _get_trade_history
from agent.tools.symbols import lookup_symbol as _lookup_symbol
from agent.tools.activities import create_activity as _create_activity
from agent.tools.compliance_check import compliance_check as _compliance_check
from agent.tools.watchlist import add_to_watchlist as _add_to_watchlist


@tool
def get_market_data(
    symbols: list[str],
    period: str = "60d",
    interval: str = "1d",
    bypass_cache: bool = False,
) -> dict:
    """Fetch price history and market context for one or more ticker symbols. Returns OHLCV data and key indicators.
    Use for: current prices, historical performance, price before a hypothetical trade.
    NOT for: portfolio concentration, risk limits, or trade approval — use guardrails_check for those.
    Args:
        symbols: List of ticker symbols, e.g. ["AAPL", "MSFT"].
        period: Time period — e.g. "1d", "5d", "1mo", "3mo", "6mo", "1y", "60d". Use "1d" with interval="1h" for current price.
        interval: Data interval — "1d" for daily, "1h" for hourly.
        bypass_cache: Set True when freshest data is required (e.g. live price quotes).
    """
    return _get_market_data(symbols, period=period, interval=interval, bypass_cache=bypass_cache)


@tool
def get_portfolio_snapshot(account_id: Optional[str] = None) -> dict:
    """Fetch the investor's current portfolio: holdings, performance, accounts, allocation, and summary (total value, cash, P&L).

    Holdings include current market value and cost basis (investment). Market prices are refreshed from a live feed so values reflect current prices — use this for tax exposure / "if I sell" questions. Use when you need current holdings, cash balance, portfolio value, or allocation.

    Also returns allocation breakdown by symbol and asset class. Pass account_id to scope to a single account.

    Args:
        account_id: Optional Ghostfolio account ID to scope the snapshot to. Omit for full portfolio. Get available account IDs from the accounts list in a previous snapshot.
    """
    return _get_portfolio_snapshot(account_id=account_id)


@tool
def detect_regime(index: str = "SPY") -> dict:
    """Detect the current market regime across 5 dimensions: trend, volatility, correlation, breadth, and rotation.

    Returns a composite regime label (e.g. bullish_expansion, quiet_consolidation) with confidence score and dimension breakdown.

    Args:
        index: Base index symbol for analysis (default "SPY").
    """
    return _detect_regime(index=index)


@tool
def scan_strategies(
    symbols: Optional[list[str]] = None,
    strategy_names: Optional[list[str]] = None,
) -> dict:
    """Scan a universe of symbols for trade setups using technical strategies (VCP breakout, mean reversion, momentum).

    Returns ranked opportunities with entry, stop loss, target, risk/reward ratio, and signals.

    Args:
        symbols: Symbols to scan. If omitted, scans the default mega-cap universe (AAPL, MSFT, NVDA, etc.).
        strategy_names: Filter to specific strategies (e.g. ["vcp_breakout", "momentum"]). If omitted, uses all strategies.
    """
    return _scan_strategies(symbols=symbols, strategy_names=strategy_names)


@tool
def guardrails_check(
    symbol: Optional[str] = None,
    side: str = "buy",
    position_size_pct: Optional[float] = None,
    dollar_amount: Optional[float] = None,
) -> dict:
    """Check portfolio or trade risk guardrails. Two modes based on whether a symbol is provided:

    No symbol → Portfolio health check: position concentration, sector concentration, cash buffer, diversification.
    Use when: "concentrated?", "diversified?", "sector exposure?", "portfolio health", "over-concentrated?".

    With symbol → Trade evaluation: checks if a proposed buy or sell fits risk guidelines.
    Use when: "should I buy/sell X?", "can I buy $10k of X?", evaluating a specific trade.
    For buys: position size limit (max 5%), sector concentration (max 30%), cash availability.
    For sells: reasons to sell/hold, P&L, hold period, portfolio impact after sale.

    Args:
        symbol: Ticker symbol for trade evaluation (e.g. "AAPL"). Omit for portfolio-level health check.
        side: "buy" to evaluate adding a position, "sell" to evaluate reducing/exiting. Only used with symbol.
        position_size_pct: Proposed position as % of portfolio (alternative to dollar_amount). Only used with symbol.
        dollar_amount: Proposed dollar amount (alternative to position_size_pct). Only used with symbol.
    """
    return _guardrails_check(
        symbol=symbol,
        side=side,
        position_size_pct=position_size_pct,
        dollar_amount=dollar_amount,
    )


@tool
def get_trade_history(
    time_range: str = "90d",
    symbol: Optional[str] = None,
    include_patterns: bool = False,
) -> dict:
    """Fetch investment transaction history and compute performance metrics: returns, average gain/loss, hold periods, and open position P&L.

    When include_patterns=True, also categorizes transactions and detects patterns (recurring dividends, DCA, fee clusters).

    Args:
        time_range: Lookback period — e.g. "90d", "6m", "1y".
        symbol: Optional filter to a specific symbol.
        include_patterns: Set True to include transaction categories and pattern detection (dividends, DCA, fee clusters).
    """
    return _get_trade_history(time_range=time_range, symbol=symbol, include_patterns=include_patterns)


@tool
def lookup_symbol(query: str) -> dict:
    """Search for a ticker symbol by name or symbol string using Ghostfolio's symbol database.

    Args:
        query: Search query — e.g. "AAPL", "Apple", "Tesla".
    """
    return _lookup_symbol(query=query)


@tool
def create_activity(
    activity_type: str,
    symbol: str,
    quantity: float,
    unit_price: float,
    currency: str,
    date: str,
    account_id: Optional[str] = None,
    fee: float = 0,
    data_source: Optional[str] = None,
    comment: Optional[str] = None,
    **kwargs: Any,
) -> dict:
    """Record a portfolio activity in Ghostfolio (buy, sell, dividend, fee, etc.).

    Use when the investor asks to record a transaction, log an investment, add a buy/sell, or save an activity to their portfolio. If the user does not give all details (symbol, quantity, price, date, currency), ask for the missing details first, then call this tool. For BUY/SELL use activity_type "BUY" or "SELL". You may call get_portfolio_snapshot first to get account_id when the user has multiple accounts.

    Args:
        activity_type: One of BUY, SELL, DIVIDEND, FEE, INTEREST, LIABILITY.
        symbol: Ticker symbol (e.g. "AAPL").
        quantity: Number of shares/units (must be > 0 for BUY/SELL).
        unit_price: Price per unit (>= 0).
        currency: Currency code (e.g. "USD").
        date: Trade date as ISO8601 (e.g. "2025-02-26" or "2025-02-26T12:00:00Z").
        account_id: Optional; use when user has multiple accounts (from get_portfolio_snapshot).
        fee: Fee/commission (default 0).
        data_source: Optional; auto-resolved from Ghostfolio symbol lookup if not provided. Only set explicitly to override.
        comment: Optional note.
    """
    return _create_activity(
        activity_type=activity_type,
        symbol=symbol,
        quantity=quantity,
        unit_price=unit_price,
        currency=currency,
        date=date,
        account_id=account_id,
        fee=fee,
        data_source=data_source,
        comment=comment,
        client=kwargs.get("client"),
    )


@tool
def compliance_check(
    regulations: Optional[list[str]] = None,
    transaction: Optional[dict] = None,
) -> dict:
    """Check compliance rules: wash sale, capital gains classification, and tax-loss harvesting.

    Two modes:
    1. Portfolio scan (default): omit transaction → scans ALL current holdings for wash sale risk, capital gains classification, and harvesting opportunities. Use this for general questions like "any wash sale issues?", "compliance issues?", "complete review".
    2. Single transaction: provide transaction dict → checks that specific trade.

    Use when: "wash sale", "trigger wash sale", "wash sale rules", "do I have wash sale issues", "tax-loss harvesting", "short-term vs long-term", "holding period", "compliance issues", "complete review", "if I sold today". For portfolio-level risk limits use guardrails_check.

    Args:
        regulations: List of regulation IDs to check. Options: "wash_sale", "capital_gains", "tax_loss_harvesting". Defaults to all if omitted.
        transaction: Optional order-like dict with type, symbol, quantity, unitPrice, date. Omit to scan all holdings.
    """
    return _compliance_check(transaction=transaction, regulations=regulations)


@tool
def add_to_watchlist(
    symbol: str,
    data_source: Optional[str] = None,
    **kwargs: Any,
) -> dict:
    """Add a symbol to the user's Ghostfolio watchlist.

    Use when the user asks to add a stock, ticker, or symbol to their watchlist (e.g. "Add AAPL to my watchlist", "Put MSFT on my watchlist"). Symbol is resolved via Ghostfolio; data_source is optional and can be auto-resolved.

    Args:
        symbol: Ticker symbol to add (e.g. "AAPL", "MSFT").
        data_source: Optional; Ghostfolio data source (e.g. YAHOO, FINANCIAL_MODELING_PREP). Omit to auto-resolve.
    """
    return _add_to_watchlist(
        symbol=symbol,
        data_source=data_source,
        client=kwargs.get("client"),
    )


ALL_TOOLS = [
    get_market_data,
    get_portfolio_snapshot,
    detect_regime,
    scan_strategies,
    guardrails_check,
    get_trade_history,
    lookup_symbol,
    create_activity,
    add_to_watchlist,
    compliance_check,
]

PHASE1_TOOLS = [
    get_market_data,
    get_portfolio_snapshot,
    guardrails_check,
    get_trade_history,
    lookup_symbol,
    create_activity,
    add_to_watchlist,
    compliance_check,
]


def get_tools() -> list:
    """Return the Phase 1 tool set (8 core tools). Fewer tools = faster, more reliable selection."""
    return list(PHASE1_TOOLS)
