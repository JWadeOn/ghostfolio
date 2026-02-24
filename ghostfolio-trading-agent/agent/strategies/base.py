"""Base strategy interface for all trading strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Strategy(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        ...

    @property
    @abstractmethod
    def favorable_regimes(self) -> list[str]:
        ...

    @abstractmethod
    def scan(self, symbol: str, market_data: list[dict]) -> dict | None:
        """
        Scan a symbol's market data for strategy signals.

        Args:
            symbol: Ticker symbol
            market_data: List of dated records with OHLCV + indicators

        Returns:
            None if no match.
            Dict with: score (0-100), signals (list of str),
            entry, stop, target (computed from data), risk_reward
        """
        ...
