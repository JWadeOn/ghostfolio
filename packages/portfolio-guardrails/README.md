# portfolio-guardrails

> Production-ready portfolio risk guardrails for LangChain financial agents

Drop-in LangChain tool that checks any portfolio against five standard risk rules. No API keys, no external services — pure Python with zero dependencies beyond `langchain-core`.

## Installation

```bash
pip install portfolio-guardrails
```

## Quick Start

```python
from portfolio_guardrails import portfolio_guardrails_check
from langgraph.prebuilt import create_react_agent

agent = create_react_agent(model, tools=[portfolio_guardrails_check])
```

That's it. Your agent can now answer questions like _"Is my portfolio too concentrated?"_ or _"Check my holdings for risk issues."_

## What It Checks

| #   | Rule                       | Violation                          | Warning               |
| --- | -------------------------- | ---------------------------------- | --------------------- |
| 1   | **Position concentration** | Single position > 20% of portfolio | > 15%                 |
| 2   | **Sector concentration**   | Single sector > 40% of portfolio   | > 30%                 |
| 3   | **Cash buffer**            | Cash < 3% of portfolio             | < 5%                  |
| 4   | **Diversification**        | Only 1 non-cash holding            | < 3 non-cash holdings |
| 5   | **Extreme concentration**  | Top position > 50%                 | Top 2 positions > 80% |

## Input Schema

```json
{
  "holdings": [
    { "symbol": "AAPL", "value": 15000, "sector": "Technology" },
    { "symbol": "JNJ", "value": 15000, "sector": "Healthcare" },
    { "symbol": "JPM", "value": 15000, "sector": "Financials" },
    { "symbol": "XOM", "value": 10000, "sector": "Energy" },
    { "symbol": "PG", "value": 10000, "sector": "Consumer Staples" },
    { "symbol": "CASH", "value": 5000, "sector": "Cash" }
  ]
}
```

Cash holdings are identified by symbol: `CASH`, `$CASH`, or `USD`.

## Output Schema

```json
{
  "violations": [],
  "warnings": [],
  "passed": true,
  "per_rule_breakdown": {
    "position_concentration": {
      "violation_threshold_pct": 20.0,
      "warning_threshold_pct": 15.0,
      "details": [{ "symbol": "AAPL", "pct": 21.43, "status": "ok" }]
    },
    "sector_concentration": { "...": "..." },
    "cash_buffer": { "cash_pct": 7.14, "status": "ok" },
    "diversification": { "non_cash_holdings": 5, "status": "ok" },
    "position_count": { "status": "ok", "details": [] }
  }
}
```

- **`passed`**: `true` when there are zero violations (warnings are informational).
- **`violations`**: List of human-readable strings — must-fix issues.
- **`warnings`**: List of human-readable strings — worth reviewing.
- **`per_rule_breakdown`**: Detailed per-rule result with thresholds and status.

## Example: Concentrated Portfolio

```python
result = portfolio_guardrails_check.invoke({"holdings": [
    {"symbol": "TSLA", "value": 90000, "sector": "Technology"},
    {"symbol": "CASH", "value": 1000,  "sector": "Cash"},
]})

# result:
# {
#   "passed": false,
#   "violations": [
#     "Position concentration: TSLA is 98.9% of portfolio (limit 20%)",
#     "Sector concentration: Technology is 98.9% of portfolio (limit 40%)",
#     "Cash buffer: cash is 1.1% of portfolio (minimum 3%)",
#     "Diversification: only 1 non-cash holding(s) (minimum 2 required)",
#     "Extreme concentration: top position (TSLA) is 98.9% of portfolio"
#   ],
#   "warnings": [],
#   ...
# }
```

## Customizing Thresholds

### Via environment variables

```bash
export GUARDRAILS_POSITION_VIOLATION_PCT=25
export GUARDRAILS_SECTOR_WARNING_PCT=35
```

### Via the internal `_check_impl` function

```python
from portfolio_guardrails.tool import _check_impl

result = _check_impl(
    holdings,
    position_violation_pct=25,
    cash_warning_pct=8,
)
```

| Environment Variable                         | Default | Description                 |
| -------------------------------------------- | ------- | --------------------------- |
| `GUARDRAILS_POSITION_VIOLATION_PCT`          | 20      | Single position violation % |
| `GUARDRAILS_POSITION_WARNING_PCT`            | 15      | Single position warning %   |
| `GUARDRAILS_SECTOR_VIOLATION_PCT`            | 40      | Single sector violation %   |
| `GUARDRAILS_SECTOR_WARNING_PCT`              | 30      | Single sector warning %     |
| `GUARDRAILS_CASH_VIOLATION_PCT`              | 3       | Minimum cash violation %    |
| `GUARDRAILS_CASH_WARNING_PCT`                | 5       | Minimum cash warning %      |
| `GUARDRAILS_DIVERSIFICATION_VIOLATION_COUNT` | 1       | Min holdings for violation  |
| `GUARDRAILS_DIVERSIFICATION_WARNING_COUNT`   | 3       | Min holdings for warning    |

## License

MIT
