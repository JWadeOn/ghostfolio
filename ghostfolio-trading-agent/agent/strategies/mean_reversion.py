"""Mean Reversion Strategy.

Identifies oversold stocks in uptrends — buy the dip in quality names.

Conditions:
- RSI(14) < 30 (oversold)
- Price > SMA(200) (long-term uptrend intact)
- Price touched or dipped below lower Bollinger Band
"""

from __future__ import annotations

from typing import Any

from agent.strategies.base import Strategy


class MeanReversionStrategy(Strategy):
    @property
    def name(self) -> str:
        return "mean_reversion"

    @property
    def description(self) -> str:
        return "Mean Reversion — RSI oversold + uptrend + lower Bollinger Band touch"

    @property
    def favorable_regimes(self) -> list[str]:
        return ["bullish_expansion", "quiet_consolidation", "selective_bull"]

    def scan(self, symbol: str, market_data: list[dict]) -> dict | None:
        if not market_data or len(market_data) < 30:
            return None

        latest = market_data[-1]
        price = latest.get("close")
        rsi = latest.get("rsi_14")
        sma_200 = latest.get("sma_200")
        bb_lower = latest.get("bb_lower")
        bb_middle = latest.get("bb_middle")
        atr = latest.get("atr_14")

        if any(v is None for v in [price, rsi, bb_lower]):
            return None

        # Check: RSI < 30
        if rsi >= 30:
            return None

        # Check: price > SMA(200) — uptrend intact
        if sma_200 is not None and price <= sma_200:
            return None

        # Check: touched or below lower Bollinger Band (within last 3 days)
        touched_bb = False
        for d in market_data[-3:]:
            low = d.get("low")
            bb_low = d.get("bb_lower")
            if low is not None and bb_low is not None and low <= bb_low:
                touched_bb = True
                break

        if not touched_bb:
            return None

        # Compute trade levels
        entry = price
        stop = price - (2 * atr) if atr else price * 0.97  # 2 ATR or 3%
        target = bb_middle if bb_middle else price * 1.05  # target mean (middle BB)
        risk_reward = (target - entry) / (entry - stop) if entry > stop else 0

        signals = []
        score = 60

        signals.append(f"RSI(14): {rsi:.1f} (oversold)")
        score += max(0, int((30 - rsi) * 1.5))  # deeper oversold = higher

        if sma_200:
            signals.append(f"Price ${price:.2f} > SMA(200) ${sma_200:.2f} (uptrend)")

        signals.append("Touched lower Bollinger Band")

        # Bonus for volume spike (potential capitulation)
        rel_vol = latest.get("relative_volume")
        if rel_vol and rel_vol > 1.5:
            signals.append(f"Relative volume: {rel_vol:.1f}x (potential capitulation)")
            score += 10

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
