"""VCP (Volatility Contraction Pattern) Breakout Strategy.

Identifies stocks with contracting volatility near 52-week highs — a classic
breakout setup. Entry is on a volume expansion breakout.

Conditions:
- ATR percentile < 25 (volatility contracting)
- Price within 5% of 52-week high
- Volume declining for 5+ consecutive days (coiling)
"""

from __future__ import annotations

from typing import Any

from agent.strategies.base import Strategy


class VCPBreakoutStrategy(Strategy):
    @property
    def name(self) -> str:
        return "vcp_breakout"

    @property
    def description(self) -> str:
        return "Volatility Contraction Pattern — low ATR near 52wk high with declining volume"

    @property
    def favorable_regimes(self) -> list[str]:
        return ["bullish_expansion", "selective_bull", "quiet_consolidation"]

    def scan(self, symbol: str, market_data: list[dict]) -> dict | None:
        if not market_data or len(market_data) < 30:
            return None

        latest = market_data[-1]
        price = latest.get("close")
        atr = latest.get("atr_14")
        dist_52w_high = latest.get("dist_52w_high_pct")

        if price is None or atr is None or dist_52w_high is None:
            return None

        # ATR percentile over last 60 days
        atr_values = [d.get("atr_14") for d in market_data[-60:] if d.get("atr_14") is not None]
        if not atr_values:
            return None
        atr_percentile = sum(1 for a in atr_values if a <= atr) / len(atr_values) * 100

        # Check: ATR percentile < 25
        if atr_percentile >= 25:
            return None

        # Check: within 5% of 52-week high
        if dist_52w_high < -5:
            return None

        # Check: volume declining 5+ consecutive days
        recent_volumes = [d.get("volume") for d in market_data[-6:]]
        if any(v is None for v in recent_volumes):
            return None

        declining_days = 0
        for i in range(1, len(recent_volumes)):
            if recent_volumes[i] < recent_volumes[i - 1]:
                declining_days += 1
            else:
                declining_days = 0

        if declining_days < 4:  # Need at least 4 declining transitions in 5 days
            return None

        # Compute trade levels
        entry = price  # breakout entry at current
        stop = price - 2 * atr  # 2 ATR stop
        target = price + 3 * atr  # 3 ATR target (1.5:1 R:R)
        risk_reward = (target - entry) / (entry - stop) if entry > stop else 0

        # Score based on how tight the pattern is
        signals = []
        score = 50

        signals.append(f"ATR percentile: {atr_percentile:.0f}% (low volatility)")
        score += max(0, (25 - atr_percentile))  # up to +25

        signals.append(f"Distance from 52wk high: {dist_52w_high:.1f}%")
        score += max(0, int((5 + dist_52w_high) * 5))  # closer = higher score

        signals.append(f"Volume declining {declining_days} consecutive days")

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
