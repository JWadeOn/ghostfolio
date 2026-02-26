"""LangChain tool wrappers for binding to the ReAct agent LLM."""

from __future__ import annotations

from typing import Any, Optional

from langchain_core.tools import tool

from agent.tools.market_data import get_market_data as _get_market_data
from agent.tools.portfolio import get_portfolio_snapshot as _get_portfolio_snapshot
from agent.tools.regime import detect_regime as _detect_regime
from agent.tools.scanner import scan_strategies as _scan_strategies
from agent.tools.risk import check_risk as _check_risk
from agent.tools.history import get_trade_history as _get_trade_history
from agent.tools.symbols import lookup_symbol as _lookup_symbol
from agent.tools.activities import create_activity as _create_activity


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
def check_risk(
    symbol: Optional[str] = None,
    direction: str = "LONG",
    action: str = "buy",
    position_size_pct: Optional[float] = None,
    dollar_amount: Optional[float] = None,
) -> dict:
    """Evaluate whether a proposed trade fits portfolio risk parameters, or assess portfolio-level risk.

    Checks position size limits (max 5%), sector concentration (max 30%), correlation with existing holdings, and cash availability.
    When action="sell", evaluates whether selling an existing position is advisable.
    When symbol is omitted, runs a portfolio-level risk assessment.

    Args:
        symbol: Ticker symbol to evaluate. Omit for portfolio-level assessment.
        direction: "LONG" or "SHORT".
        action: "buy" to evaluate adding a position, "sell" to evaluate selling.
        position_size_pct: Proposed position as percentage of portfolio (alternative to dollar_amount).
        dollar_amount: Proposed dollar amount (alternative to position_size_pct).
    """
    return _check_risk(
        symbol=symbol,
        direction=direction,
        action=action,
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


ALL_TOOLS = [
    get_market_data,
    get_portfolio_snapshot,
    detect_regime,
    scan_strategies,
    check_risk,
    get_trade_history,
    lookup_symbol,
    create_activity,
]


def get_tools() -> list:
    """Return the list of LangChain tools available to the ReAct agent."""
    return list(ALL_TOOLS)
