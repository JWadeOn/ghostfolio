# Eval Suite Architecture

> Last updated: 2026-02-28

## Overview

Three evaluation layers with distinct purposes:

```
Golden Set ─── "Does it work?"              (regression gate, all must pass)
Scenarios  ─── "Does it work for all types?" (coverage map, some failure OK)
Dataset    ─── "How well does it work?"      (weighted scoring, regression tracking)
```

---

## Layer 1: Golden Set

**File:** `tests/eval/golden_cases.py` (34 cases)
**Runner:** `tests/eval/run_golden.py`
**Purpose:** Binary pass/fail regression gate.

### Case Types

| Type        | Count | Description                                     |
| ----------- | ----- | ----------------------------------------------- |
| happy_path  | 17    | One per tool + duplicates for baseline coverage |
| edge_case   | 7     | Missing data, ambiguity, boundary conditions    |
| adversarial | 4     | Prompt injection, safety refusals               |
| multi_step  | 6     | Queries requiring 2+ tools                      |

### 7 Check Dimensions

1. **Tool Selection** — Are expected tools called?
2. **Tool Execution** — Do all tools succeed?
3. **Source Citation** — Do expected sources/authoritative refs appear?
4. **Content Validation** — Do required terms appear?
5. **Negative Validation** — No forbidden terms, no give-up phrases, non-empty?
6. **Ground Truth** — Do known mock-data values appear?
7. **Structural** — ReAct steps + latency within budget?

### Usage

```bash
python3 tests/eval/run_golden.py                 # Run all
python3 tests/eval/run_golden.py --verbose        # Show error details
python3 tests/eval/run_golden.py --id gs-001      # Single case
python3 tests/eval/run_golden.py --report         # Write JSON report
pytest tests/eval/test_golden.py -v               # Via pytest
```

---

## Layer 2: Labeled Scenarios

**File:** `tests/eval/scenarios.py` (47 cases)
**Runner:** `tests/eval/run_scenarios.py`
**Purpose:** Coverage mapping — visibility into which query types work.

### Structure

```
scenarios = {
    single_tool (15):   portfolio, market_data, history, tax, utility, edge
    multi_tool  (15):   portfolio_and_guardrails, investment_evaluation,
                        compliance_and_history, authoritative_sources, comprehensive
    no_tool     (17):   ambiguous, adversarial, tax, edge_case
}
```

### Difficulty Tiers

| Tier            | Description                                      |
| --------------- | ------------------------------------------------ |
| straightforward | Clear intent, one tool, no ambiguity             |
| moderate        | Requires inference or multi-tool coordination    |
| complex         | Multi-step reasoning, 3+ tools                   |
| ambiguous       | Missing info, agent should ask for clarification |
| adversarial     | Prompt injection, safety refusal, manipulation   |
| edge_case       | Empty input, gibberish, off-topic, boundaries    |

### 4 Check Dimensions

1. Tool Selection
2. Tool Execution
3. Content Validation
4. Negative Validation

### Coverage Matrix Output

```
                     | adversarial | ambiguous | complex | edge_case | moderate | straightforward |
          multi_tool |           - |         - |     3/3 |         - |      4/4 |             4/4 |
             no_tool |         5/5 |       5/5 |       - |       4/4 |      2/2 |             1/1 |
         single_tool |           - |         - |       - |       2/2 |      2/2 |           11/11 |
```

### Usage

```bash
python3 tests/eval/run_scenarios.py                        # All
python3 tests/eval/run_scenarios.py --category single_tool # Filter by category
python3 tests/eval/run_scenarios.py --difficulty moderate   # Filter by difficulty
python3 tests/eval/run_scenarios.py --report               # Write JSON report
```

---

## Layer 3: Dataset

**File:** `tests/eval/dataset.py` (30 cases)
**Runner:** `tests/eval/run_evals.py`
**Purpose:** Weighted scoring focused on intent classification and confidence scoring, LangSmith integration, regression detection. All queries are unique from golden set and scenarios.

### Case Types

| Type        | Count | Description                                                                     |
| ----------- | ----- | ------------------------------------------------------------------------------- |
| happy_path  | 12    | Risk checks, lookups, activity, watchlist, health, performance, tax, compliance |
| edge_case   | 4     | Ambiguous queries, portfolio worth, greeting                                    |
| adversarial | 7     | Prompt injection, safety refusals                                               |
| multi_step  | 7     | Queries requiring 2+ tools with cross-domain reasoning                          |

### 6 Weighted Scoring Dimensions

| Dimension    | Weight |
| ------------ | ------ |
| Intent       | 20%    |
| Tools        | 25%    |
| Content      | 15%    |
| Safety       | 15%    |
| Confidence   | 15%    |
| Verification | 10%    |

**Pass threshold:** overall_score >= 0.80 AND no hard errors

### Usage

```bash
python3 tests/eval/run_evals.py              # All 30 cases
```

---

## Shared Infrastructure

### Core Engine: `tests/eval/run_evals.py`

All runners share:

- `run_single_eval(case, agent_graph, case_id, use_mocks)` — runs one case through the agent
- `_apply_eval_mocks()` — patches GhostfolioClient, market data, sector lookup

### Check Functions: `tests/eval/golden_checks.py`

Pure functions (no LLM, no network):

- `check_tools()`, `check_tools_any()`, `check_tools_plus_any_of()`
- `check_must_contain()`, `check_contains_any()`
- `check_must_not_contain()` (includes give-up phrase detection)
- `check_sources()`, `check_authoritative_sources()`
- `check_ground_truth()`
- `check_structural()`
- `run_golden_checks()` — orchestrates all 7 dimensions

### Mock Infrastructure: `tests/mocks/`

| File                      | What It Provides                                                        |
| ------------------------- | ----------------------------------------------------------------------- |
| `ghostfolio_mock.py`      | `MockGhostfolioClient` — drop-in replacement with canned data           |
| `ghostfolio_responses.py` | `MOCK_HOLDINGS`, `MOCK_ORDERS`, `MOCK_ACCOUNTS`, `MOCK_PERFORMANCE`     |
| `market_data_mock.py`     | `mock_fetch_with_retry` — OHLCV DataFrames with pinned canonical prices |

### Canonical Mock Prices (for ground-truth checks)

```python
AAPL: $187.50    TSLA: $248.00    GOOG: $142.00
MSFT: $415.00    NVDA: $875.00    SPY:  $545.00    VIX: $16.50
```

---

## Relationship Diagram

```
golden_cases.py ──→ run_golden.py ───→ run_single_eval() ──→ agent.graph
                    test_golden.py ─/        ↑
                                             |
scenarios.py ─────→ run_scenarios.py ────────┘
                                             |
dataset.py ───────→ run_evals.py ────────────┘
                         |                   |
                         ↓                   ↓
                    reports/*.json       tests/mocks/
                    + LangSmith         (MockGhostfolioClient,
                                         mock_fetch_with_retry)
```

---

## Adding New Cases

### Golden Case Template

```python
{
    "id": "gs-NNN",
    "category": "portfolio_overview",      # used for grouping
    "case_type": "happy_path",             # happy_path|edge_case|adversarial|multi_step
    "input": "User query here",
    "expected_tools": ["tool_name"],       # OR expected_tools_any / expected_tools_plus_any_of
    "expected_output_contains": ["term"],   # must appear (case-insensitive substring)
    "expected_output_contains_any": [...],  # at least one must appear
    "ground_truth_contains": ["AAPL"],     # mock data values that must appear
    "should_not_contain": ["I don't know"],# forbidden terms
    "max_react_steps": 2,                  # structural budget
    "max_latency_seconds": 10,             # structural budget
    "phase": 1,
}
```

### Scenario Template

```python
{
    "id": "sc-XX-NNN",
    "query": "User query here",
    "expected_tools": ["tool_name"],       # OR expected_tools_any / expected_tools_plus_any_of
    "expected_output_contains": ["term"],
    "expected_output_contains_any": [...],
    "expected_authoritative_sources": [...],# optional: source IDs for compliance cases
    "should_not_contain": [...],
    "difficulty": "straightforward",       # tier from table above
}
```
