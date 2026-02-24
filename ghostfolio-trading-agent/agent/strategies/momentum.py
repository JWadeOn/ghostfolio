"""Momentum Continuation Strategy.

Identifies stocks with healthy momentum — riding the trend.

Conditions:
- RSI(14) between 55-75 (strong but not overbought)
- Price > rising EMA(20) (trend confirmation)
- Relative volume > 1.0 (institutional interest)
"""

from __future__ import annotations

from typing import Any

from agent.strategies.base import Strategy


class MomentumStrategy(Strategy):
    @property
    def name(self) -> str:
        return "momentum"

    @property
    def description(self) -> str:
        return "Momentum Continuation — RSI 55-75, price above rising EMA(20), above-average volume"

    @property
    def favorable_regimes(self) -> list[str]:
        return ["bullish_expansion", "selective_bull"]

    def scan(self, symbol: str, market_data: list[dict]) -> dict | None:
        if not market_data or len(market_data) < 25:
            return None

        latest = market_data[-1]
        price = latest.get("close")
        rsi = latest.get("rsi_14")
        ema_21 = latest.get("ema_21")
        rel_vol = latest.get("relative_volume")
        atr = latest.get("atr_14")

        if any(v is None for v in [price, rsi, ema_21]):
            return None

        # Check: RSI between 55-75
        if rsi < 55 or rsi > 75:
            return None

        # Check: price > EMA(21)
        if price <= ema_21:
            return None

        # Check: EMA(21) is rising (compare current to 5 days ago)
        ema_5ago = None
        if len(market_data) >= 6:
            ema_5ago = market_data[-6].get("ema_21")

        if ema_5ago is not None and ema_21 <= ema_5ago:
            return None

        # Check: relative volume > 1.0
        if rel_vol is not None and rel_vol <= 1.0:
            return None

        # Compute trade levels
        entry = price
        stop = ema_21 - (0.5 * atr) if atr else ema_21 * 0.98
        target = price + 3 * (price - stop)  # 3:1 R:R target
        risk_reward = (target - entry) / (entry - stop) if entry > stop else 0

        signals = []
        score = 55

        signals.append(f"RSI(14): {rsi:.1f} (healthy momentum)")
        # Closer to 65 (sweet spot) gets more points
        score += max(0, 15 - abs(rsi - 65))

        signals.append(f"Price ${price:.2f} > EMA(21) ${ema_21:.2f}")

        if ema_5ago:
            ema_change = (ema_21 - ema_5ago) / ema_5ago * 100
            signals.append(f"EMA(21) rising {ema_change:.2f}% over 5 days")
            score += min(10, max(0, int(ema_change * 5)))

        if rel_vol:
            signals.append(f"Relative volume: {rel_vol:.1f}x")
            score += min(10, int((rel_vol - 1.0) * 10))

        # MACD confirmation bonus
        macd_hist = latest.get("macd_histogram")
        if macd_hist and macd_hist > 0:
            signals.append("MACD histogram positive (confirmation)")
            score += 5

        return {
            "strategy": self.name,
            "symbol": symbol,
            "score": min(100, int(score)),
            "signals": signals,
            "entry": round(entry, 2),
            "stop": round(stop, 2),
            "target": round(target, 2),
            "risk_reward": round(risk_reward, 2),
        }
