"""LangChain tool wrappers for binding to the ReAct agent LLM."""

from __future__ import annotations

from typing import Any, Optional

from langchain_core.tools import tool

from agent.tools.market_data import get_market_data as _get_market_data
from agent.tools.portfolio import get_portfolio_snapshot as _get_portfolio_snapshot
from agent.tools.regime import detect_regime as _detect_regime
from agent.tools.scanner import scan_strategies as _scan_strategies
from agent.tools.risk import portfolio_guardrails_check as _portfolio_guardrails_check
from agent.tools.risk import trade_guardrails_check as _trade_guardrails_check
from agent.tools.history import get_trade_history as _get_trade_history
from agent.tools.symbols import lookup_symbol as _lookup_symbol
from agent.tools.activities import create_activity as _create_activity
from agent.tools.portfolio_analysis import portfolio_analysis as _portfolio_analysis
from agent.tools.transaction_categorize import transaction_categorize as _transaction_categorize
from agent.tools.tax_estimate import tax_estimate as _tax_estimate


@tool
def get_market_data(
    symbols: list[str],
    period: str = "60d",
    interval: str = "1d",
    bypass_cache: bool = False,
) -> dict:
    """Fetch OHLCV price data and technical indicators (RSI, SMA, EMA, MACD, Bollinger Bands, ATR) for one or more ticker symbols.

    Use this when you need current or historical price data, chart analysis, or technical indicator values.

    Args:
        symbols: List of ticker symbols, e.g. ["AAPL", "MSFT"].
        period: Time period — e.g. "1d", "5d", "1mo", "3mo", "6mo", "1y", "60d". Use "1d" with interval "1h" for intraday/current prices.
        interval: Data interval — "1d" for daily, "1h" for hourly.
        bypass_cache: Set True when you need the freshest data (e.g. current price quotes).
    """
    return _get_market_data(symbols, period=period, interval=interval, bypass_cache=bypass_cache)


@tool
def get_portfolio_snapshot() -> dict:
    """Fetch the trader's current portfolio: holdings, performance, accounts, and summary (total value, cash, P&L).

    Use this when you need to see what the trader currently holds, their cash balance, portfolio value, or allocation breakdown.
    """
    return _get_portfolio_snapshot()


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
def portfolio_guardrails_check() -> dict:
    """Assess portfolio-level risk: position concentration, sector concentration, cash buffer, diversification.

    Use when the user asks about portfolio risk, health check, or whether they are within their limits.
    No symbol or trade amount needed — this checks the portfolio itself.
    """
    return _portfolio_guardrails_check()


@tool
def trade_guardrails_check(
    symbol: str,
    side: str = "buy",
    position_size_pct: Optional[float] = None,
    dollar_amount: Optional[float] = None,
) -> dict:
    """Check if a proposed buy or sell fits portfolio guardrails.

    For buys: checks position size (max 5%), sector concentration (max 30%), correlation, cash availability.
    Returns violations, warnings, suggested position size, and stop loss level.
    For sells: evaluates reasons to sell/hold, P&L, hold period, stop loss, and portfolio after sale.

    Args:
        symbol: Ticker symbol to evaluate (e.g. "AAPL").
        side: "buy" to evaluate adding a position, "sell" to evaluate selling.
        position_size_pct: Proposed position as percentage of portfolio (alternative to dollar_amount).
        dollar_amount: Proposed dollar amount (alternative to position_size_pct).
    """
    return _trade_guardrails_check(
        symbol=symbol,
        side=side,
        position_size_pct=position_size_pct,
        dollar_amount=dollar_amount,
    )


@tool
def get_trade_history(
    time_range: str = "90d",
    symbol: Optional[str] = None,
) -> dict:
    """Fetch trade history and compute P&L outcomes: win rate, average win/loss, profit factor, hold times.

    Args:
        time_range: Lookback period — e.g. "90d", "6m", "1y".
        symbol: Optional filter to a specific symbol.
    """
    return _get_trade_history(time_range=time_range, symbol=symbol)


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
    """Record a transaction or portfolio activity in Ghostfolio (buy, sell, dividend, fee, etc.).

    You HAVE this tool. Use it when the user asks to record a transaction, log a trade, add a buy/sell, record an activity, or save a transaction to their portfolio. If the user does not give all details (symbol, quantity, price, date, currency), ask for the missing details first, then call this tool. For BUY/SELL use activity_type "BUY" or "SELL". For recording a trade you may first run check_risk and optionally get_portfolio_snapshot to get account_id when the user has multiple accounts.

    Args:
        activity_type: One of BUY, SELL, DIVIDEND, FEE, INTEREST, LIABILITY.
        symbol: Ticker symbol (e.g. "AAPL").
        quantity: Number of shares/units (must be > 0 for BUY/SELL).
        unit_price: Price per unit (>= 0).
        currency: Currency code (e.g. "USD").
        date: Trade date as ISO8601 (e.g. "2025-02-26" or "2025-02-26T12:00:00Z").
        account_id: Optional; use when user has multiple accounts (from get_portfolio_snapshot).
        fee: Fee/commission (default 0).
        data_source: Optional; for stocks use "YAHOO" if not specified.
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
def portfolio_analysis(account_id: Optional[str] = None) -> dict:
    """Analyze portfolio holdings, allocation breakdown, and performance for a specific account or all accounts.

    Use when the user asks for analysis of a specific account, allocation breakdown, or detailed per-account performance.
    Omit account_id for the full portfolio. Get available account IDs from get_portfolio_snapshot → accounts[].id.

    Args:
        account_id: Ghostfolio account ID to scope the analysis to. Omit for full portfolio.
    """
    return _portfolio_analysis(account_id=account_id)


@tool
def transaction_categorize(
    transactions: Optional[list] = None,
    time_range: Optional[str] = "1y",
    account_id: Optional[str] = None,
) -> dict:
    """Categorize transactions by type and tags; detect patterns (recurring dividends, DCA, fee clusters).

    Pass transactions from trade history, or leave blank to fetch from Ghostfolio.

    Args:
        transactions: Pre-fetched list of transactions. If omitted, fetches from Ghostfolio.
        time_range: Lookback period when fetching (e.g. "1y", "90d", "6m").
        account_id: Optional account filter when fetching.
    """
    return _transaction_categorize(
        transactions=transactions,
        time_range=time_range,
        account_id=account_id,
    )


@tool
def tax_estimate(
    income: float,
    deductions: float = 0,
    filing_status: str = "single",
) -> dict:
    """Estimate US federal income tax from income and deductions. Informational only; not professional tax advice.

    Args:
        income: Gross income in USD.
        deductions: Total deductions (standard or itemized, default 0).
        filing_status: One of "single", "married_filing_jointly", "head_of_household".
    """
    return _tax_estimate(income=income, deductions=deductions, filing_status=filing_status)


ALL_TOOLS = [
    get_market_data,
    get_portfolio_snapshot,
    detect_regime,
    scan_strategies,
    portfolio_guardrails_check,
    trade_guardrails_check,
    get_trade_history,
    lookup_symbol,
    create_activity,
    portfolio_analysis,
    transaction_categorize,
    tax_estimate,
]


def get_tools() -> list:
    """Return the list of LangChain tools available to the ReAct agent."""
    return list(ALL_TOOLS)
