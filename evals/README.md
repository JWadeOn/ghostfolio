# LangGraph Financial Agent Eval Dataset

A standalone, reusable evaluation dataset and scoring package for **LangGraph-based financial agents**. Use it to measure intent accuracy, tool usage, content quality, safety, and confidence on a standardized set of 50+ evaluation cases (initial release ships with 24 cases from the reference implementation; the schema supports expansion to 50+).

No dependency on any specific agent codebase: load the JSON dataset, run your graph, and score results with the included module.

---

## What This Dataset Is

- **50+ eval cases** (design target; initial export includes 24 cases) covering:
  - Portfolio and risk (overview, risk checks, position sizing)
  - Market regime and opportunity scanning
  - Price quotes, symbol lookup, and activity logging
  - Chart/support validation and signal archaeology
  - Journal/performance analysis
  - Safety and edge cases (guarantees, ambiguous or invalid input)
- **Phase-aware**: cases are tagged with `phase` (1 = long-term investor flows, 2 = regime/scan flows) so you can run phase-specific evals.
- **Self-contained cases**: each case includes input, expected intent, expected tools, content/safety expectations, and optional ground-truth and live-safety flags.

---

## 5-Dimension Scoring Framework

Scores are per dimension in `[0.0, 1.0]`. The **overall score** is a weighted sum (weights below sum to 1.0).

| Dimension      | Weight | Description                                                                     |
| -------------- | ------ | ------------------------------------------------------------------------------- |
| **Intent**     | 0.20   | Did the agent classify user intent correctly?                                   |
| **Tools**      | 0.25   | Were the right tools called (subset or exact, depending on `exact_tools`)?      |
| **Content**    | 0.20   | Does the response contain required phrases and avoid missing expected content?  |
| **Safety**     | 0.20   | Does the response avoid forbidden phrases (e.g. guarantees, reckless language)? |
| **Confidence** | 0.15   | Is the agent’s reported confidence ≥ case `confidence_min`?                     |

**Overall score** = `0.20×intent + 0.25×tools + 0.20×content + 0.20×safety + 0.15×confidence`

A case typically **passes** when overall score ≥ 0.8 (configurable in your runner).

---

## Case Structure

Each case in `dataset.json` is a single object with these fields:

| Field                      | Type           | Description                                                                                                             |
| -------------------------- | -------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `id`                       | string         | Unique case ID (e.g. `"case_001"`).                                                                                     |
| `category`                 | string         | Category label (e.g. `portfolio_overview`, `risk_check`, `regime_check`).                                               |
| `difficulty`               | string         | `"easy"` \| `"medium"` \| `"hard"`.                                                                                     |
| `phase`                    | number         | `1` (long-term investor) or `2` (regime/scan).                                                                          |
| `input`                    | string         | User message to send to the agent.                                                                                      |
| `expected_intent`          | string \| null | Expected intent label.                                                                                                  |
| `expected_tools`           | string[]       | Tools that must be called (subset check unless `exact_tools`).                                                          |
| `expected_output_contains` | string[]       | Phrases that should appear in the final answer.                                                                         |
| `should_not_contain`       | string[]       | Phrases that must not appear (safety).                                                                                  |
| `should_contain`           | string[]       | Additional required phrases (e.g. disclaimers).                                                                         |
| `confidence_min`           | number         | Minimum agent confidence (0–100) to pass confidence dimension.                                                          |
| `golden`                   | boolean        | If true, include in **fast** mode (high-signal subset).                                                                 |
| `live_safe`                | boolean        | If true (default), content/safety checks apply in **live** mode; if false, only tools are checked when not using mocks. |
| `exact_tools`              | boolean        | If true, no extra tools allowed beyond `expected_tools`.                                                                |
| `ground_truth_contains`    | string[]       | Optional; in mock runs, response should contain these values (e.g. mock price).                                         |

---

## How to Use With Any LangGraph Agent

### 1. Load the dataset

```python
import json
with open("evals/dataset.json") as f:
    data = json.load(f)
cases = data["cases"]
```

### 2. Run your agent per case

For each case, invoke your LangGraph graph with `case["input"]` and collect a **result** dict with at least:

- `intent`: detected intent string
- `tools_called`: list of tool names invoked
- `response`: dict with `summary` (final answer text) and optional `confidence` (0–100)

Optional for richer scoring:

- `tool_results`: dict of tool name → result (failures can be used to downgrade tool score)
- `verification_result`: if you have a verification step

### 3. Score with the standalone module

```python
from evals.scoring import score_case

result = {
    "intent": "portfolio_overview",
    "tools_called": ["get_portfolio_snapshot"],
    "response": {"summary": "Your portfolio has 3 positions...", "confidence": 85},
}
scores, overall, passed = score_case(case, result)
print(scores)   # {"intent": 1.0, "tools": 1.0, "content": ..., "safety": ..., "confidence": ...}
print(overall)  # 0.0–1.0
print(passed)   # bool
```

### 4. Aggregate

Run over all cases (or a filtered subset), sum passes, and compute pass rate and average overall score for your report.

---

## Eval Modes

| Mode     | Description                                                                                                                                | When to use                                       |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------- |
| **fast** | Run only cases with `golden: true`.                                                                                                        | Quick smoke tests, CI.                            |
| **full** | Run all cases in `dataset.json`.                                                                                                           | Full regression, release checks.                  |
| **live** | Run against real APIs (no mocks). For cases with `live_safe: false`, content/safety assertions are skipped and only tool usage is checked. | Integration testing with live broker/market data. |

Filter examples:

```python
# Fast: golden subset
fast_cases = [c for c in cases if c.get("golden", False)]

# Full: all
full_cases = cases

# Live: same as full, but runner should set use_mocks=False and skip content checks when live_safe is false
live_cases = cases
```

---

## Category Breakdown

| Category               | What it tests                                                          | Why it matters                                         |
| ---------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------ |
| **portfolio_overview** | Fetching and summarizing portfolio positions.                          | Core flow for “show my portfolio”.                     |
| **risk_check**         | Using portfolio + market data + guardrails before suggesting add/sell. | Prevents recommending actions that violate risk rules. |
| **regime_check**       | Market regime / volatility / sector rotation.                          | Phase 2: regime-aware behavior.                        |
| **opportunity_scan**   | Scanning watchlist or universe for setups.                             | Phase 2: finding ideas without overpromising.          |
| **price_quote**        | Returning current price for a symbol.                                  | Accuracy and tool choice.                              |
| **lookup_symbol**      | Resolving company name → ticker.                                       | Correct tool and response content.                     |
| **create_activity**    | Logging buy/sell activities.                                           | Parsing and API usage.                                 |
| **chart_validation**   | Validating levels (e.g. support) with market data.                     | Data-driven answers, no hallucinated levels.           |
| **journal_analysis**   | Trade history and performance (e.g. win rate).                         | Correct tool and metrics in answer.                    |
| **signal_archaeology** | Explaining what “predicted” a past move.                               | Retrospective analysis without guarantees.             |
| **general**            | Greetings, disclaimers, refusing guarantees.                           | Safety and non-action responses.                       |
| **edge_invalid**       | Empty or gibberish input.                                              | No spurious trades or guarantees.                      |
| **edge_ambiguous**     | Vague input (e.g. “Sell”, “Should I?”).                                | No executing or promising specific trades.             |

---

## How to Contribute New Cases

See **[CONTRIBUTING.md](CONTRIBUTING.md)** for:

- Case structure template
- Guidelines for difficulty (easy / medium / hard)
- Guidelines per category
- How to validate a new case before submitting

---

## Files in This Package

- **dataset.json** — All eval cases in one JSON file; schema described above.
- **scoring.py** — Standalone scoring: `score_case(case, result)` → per-dimension scores, overall score, and pass/fail. No imports from the rest of the repo.
- **README.md** — This file.
- **CONTRIBUTING.md** — Guide for adding and validating new cases.
