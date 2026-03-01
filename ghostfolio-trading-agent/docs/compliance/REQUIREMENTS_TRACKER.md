# Requirements Compliance Tracker

> Last updated: 2026-02-28
> Branch: feat/react-pipeline

This document tracks our system's compliance against the three required specification areas:
Evaluation Framework, Observability, and Verification Systems.

Status key: `[x]` = met, `[~]` = partial/exists but needs work, `[ ]` = not implemented

---

## 1. Evaluation Framework

### 1.1 Eval Types (7 required)

| #   | Eval Type      | Status | Implementation                                                                           | Notes                                                                        |
| --- | -------------- | ------ | ---------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| 1   | Correctness    | `[x]`  | `ground_truth_contains` in golden cases; `_check_facts()` in verification.py             | Fact-checks numbers against tool results with 0.5% tolerance                 |
| 2   | Tool Selection | `[x]`  | `expected_tools`, `expected_tools_any`, `expected_tools_plus_any_of` in golden_checks.py | Supports exact, any-of, and required+any-of matching                         |
| 3   | Tool Execution | `[x]`  | `tool_exec_ok` dimension in all 3 runners                                                | Checks tool results for error keys                                           |
| 4   | Safety         | `[x]`  | `should_not_contain`, negative validation, guarantee-language flagging                   | 19 adversarial cases across eval layers                                      |
| 5   | Consistency    | `[~]`  | `run_consistency_check()` in run_evals.py (lines 451-502)                                | **Gap**: Not wired into golden/scenario runners; not reported in eval output |
| 6   | Edge Cases     | `[x]`  | 25 edge cases across all layers                                                          | Covers gibberish, empty input, off-topic, boundary conditions                |
| 7   | Latency        | `[x]`  | `max_latency_seconds` + `max_react_steps` in golden cases; structural check              | Budget per case; avg 2.8s, max 8.6s                                          |

### 1.2 Eval Dataset Requirements

| Requirement                                         | Target | Actual                                          | Status |
| --------------------------------------------------- | ------ | ----------------------------------------------- | ------ |
| Total test cases                                    | 50+    | **111** (34 golden + 47 scenarios + 30 dataset) | `[x]`  |
| Happy path scenarios                                | 20+    | **45**                                          | `[x]`  |
| Edge cases                                          | 10+    | **17**                                          | `[x]`  |
| Adversarial inputs                                  | 10+    | **16**                                          | `[x]`  |
| Multi-step reasoning                                | 10+    | **28**                                          | `[x]`  |
| Each case includes: query, tools, output, pass/fail | Yes    | Yes                                             | `[x]`  |

### 1.3 Eval Layers

| Layer      | File                         | Cases | Purpose                         | Last Run                 | Pass Rate            |
| ---------- | ---------------------------- | ----- | ------------------------------- | ------------------------ | -------------------- |
| Golden Set | `tests/eval/golden_cases.py` | 34    | Regression gate (all must pass) | 2026-02-28               | 30-31/31 (96.8-100%) |
| Scenarios  | `tests/eval/scenarios.py`    | 47    | Coverage map (some failure OK)  | 2026-02-28               | 43/43 (100%)         |
| Dataset    | `tests/eval/dataset.py`      | 30    | Weighted scoring + LangSmith    | **Not run post-cleanup** | Unknown              |

### 1.4 Check Dimensions

**Golden Set (7 dimensions):**

1. Tool Selection — required tools present
2. Tool Execution — no tool errors
3. Source Citation — expected references in response
4. Content Validation — must_contain + contains_any terms
5. Negative Validation — no forbidden terms or give-up phrases
6. Ground Truth — mock data values appear in output
7. Structural — ReAct steps + latency within budget

**Scenarios (4 dimensions):**

1. Tool Selection
2. Tool Execution
3. Content Validation
4. Negative Validation

**Dataset (6 weighted dimensions):**

1. Intent (20%) — correct intent classification
2. Tools (25%) — right tools selected
3. Content (15%) — relevant content in response
4. Safety (15%) — no harmful content
5. Confidence (15%) — appropriate confidence score
6. Verification (10%) — verification checks pass

---

## 2. Observability Requirements

| #   | Capability       | Status | Implementation                                                                                 | Files                                                                      |
| --- | ---------------- | ------ | ---------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| 1   | Trace Logging    | `[x]`  | `make_trace_entry()` in every node; captures input→reasoning→tools→output                      | `agent/observability.py`, state field `trace_log`                          |
| 2   | Latency Tracking | `[x]`  | Per-node + per-tool `time.perf_counter()`; aggregated in formatter                             | `agent/observability.py` (`track_latency()`), state field `node_latencies` |
| 3   | Error Tracking   | `[x]`  | `ErrorCategory` (6 types: LLM, TOOL, VALIDATION, PARSE, NETWORK, UNKNOWN); 3-frame stacktraces | `agent/observability.py` (`make_error_entry()`), state field `error_log`   |
| 4   | Token Usage      | `[x]`  | `extract_token_usage()` per LLM call; `aggregate_token_usage()` with cost estimation           | `agent/observability.py`, state field `token_usage`                        |
| 5   | Eval Results     | `[x]`  | JSON reports in `reports/`; `check_regression()` compares against previous run                 | `tests/eval/run_evals.py` (lines 608-631)                                  |
| 6   | User Feedback    | `[x]`  | `POST /api/feedback` — thumbs up/down, corrections, comments; summary endpoint                 | `agent/app.py` (lines 263-318)                                             |

### Observability Data Flow

```
Captured during execution (AgentState dicts)
  → Formatted at output (response.observability)
  → Stored in persistence (conversation history)
  → Reported via evals (reports/*.json)
  → Exported to LangSmith (optional, if API key set)
```

---

## 3. Verification Systems

### 3.1 Required Verification (3+ of 6)

| #   | Verification Type       | Status | Implementation                                                                                                                                                                       | Files                                                                            |
| --- | ----------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------- |
| 1   | Fact Checking           | `[~]`  | Numerical claims checked against tool results (0.5% tolerance); authoritative source refs for tax/compliance                                                                         | `verification.py` (`_check_facts`, lines 97-178); `agent/authoritative_sources/` |
| 2   | Hallucination Detection | `[~]`  | Unsupported number flagging; guarantee-language detection; source attribution required in synthesis prompt                                                                           | `verification.py` (lines 327-331, 382-441); `synthesis.py` (line 26)             |
| 3   | Confidence Scoring      | `[x]`  | 0-100 multi-factor score (base 50 + tool/regime/guardrails/compliance boosters); surfaced in response                                                                                | `verification.py` (`_compute_confidence`, lines 229-276)                         |
| 4   | Domain Constraints      | `[x]`  | Price freshness (<3 days); tax sanity (rate 0-100%); compliance consistency; trade guardrails (stop loss + target); authoritative rule validation (wash sale 30-day, long-term >1yr) | `verification.py` (lines 181-441)                                                |
| 5   | Output Validation       | `[~]`  | Response schema with mandatory fields; JSON serialization; intent-specific data extraction                                                                                           | `formatter.py` (lines 187-247)                                                   |
| 6   | Human-in-the-Loop       | `[ ]`  | Not implemented. No escalation triggers, approval workflow, or review queue.                                                                                                         | —                                                                                |

**Count: 5 of 6 implemented (2 full, 3 partial). Meets the "3+" requirement.**

### 3.2 Performance Targets

| Metric                           | Target | Current                      | Status | Evidence                                                |
| -------------------------------- | ------ | ---------------------------- | ------ | ------------------------------------------------------- |
| End-to-end latency (single-tool) | <5s    | Avg 2.8s                     | `[x]`  | Scenario runner stats                                   |
| Multi-step latency (3+ tools)    | <15s   | Max 8.6s                     | `[x]`  | Scenario runner stats                                   |
| Tool success rate                | >95%   | 100%                         | `[x]`  | Golden: 100%, Scenarios: 100%                           |
| Eval pass rate                   | >80%   | Golden 96.8%, Scenarios 100% | `[x]`  | Last run 2026-02-28                                     |
| Hallucination rate               | <5%    | **Not explicitly tracked**   | `[~]`  | Fact-checking exists but no aggregate metric in reports |
| Verification accuracy            | >90%   | **Not explicitly tracked**   | `[~]`  | Verification runs but no precision/recall measurement   |

---

## 4. Gaps and Action Items

### Must Fix (spec compliance gaps)

| #   | Gap                           | Severity | What's Missing                                                                | Suggested Fix                                                              |
| --- | ----------------------------- | -------- | ----------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| G-1 | Consistency eval not reported | Medium   | `run_consistency_check()` exists but isn't wired into golden/scenario runners | Add consistency run to golden runner; report determinism %                 |
| G-2 | Hallucination rate metric     | Medium   | No aggregate "X% of responses had unsupported claims" in eval reports         | Add hallucination counter to `run_golden_checks()` and aggregate in report |
| G-3 | Verification accuracy metric  | Medium   | No measurement of verification precision (correct flags vs false positives)   | Create verification accuracy eval cases; track in report                   |

### Should Fix (strengthen existing implementations)

| #   | Gap                                            | What to do                                                                                           |
| --- | ---------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| G-4 | Dataset layer not validated post-consolidation | Run `python3 tests/eval/run_evals.py` and record pass rate                                           |
| G-5 | New authoritative source cases untested        | Run golden (gs-032 to gs-034) and scenarios (sc-as-001 to sc-as-004)                                 |
| G-6 | Fact checking limited to numerical claims      | Add semantic fact checking for non-numeric claims (regime classification, holding period assertions) |
| G-7 | Output validation has no schema library        | Consider Pydantic validation for response dict                                                       |
| G-8 | Confidence scoring doesn't trigger escalation  | Add threshold-based warnings (e.g., confidence < 40 = low-confidence warning)                        |

### Nice to Have (beyond spec)

| #    | Enhancement                                                                 |
| ---- | --------------------------------------------------------------------------- |
| G-9  | Human-in-the-loop escalation for high-risk decisions                        |
| G-10 | OpenTelemetry export for production monitoring                              |
| G-11 | Per-tool SLO tracking and alerting                                          |
| G-12 | Feedback-to-eval correlation (link thumbs-down to specific eval dimensions) |

---

## 5. File Reference Map

### Evaluation Infrastructure

```
tests/eval/
├── golden_cases.py          # 34 golden eval cases (regression gate)
├── scenarios.py             # 47 labeled scenarios (coverage map)
├── dataset.py               # 30 dataset cases (weighted scoring)
├── golden_checks.py         # 7 deterministic check functions
├── run_golden.py            # Golden set CLI runner
├── run_scenarios.py         # Scenario CLI runner
├── run_evals.py             # Core eval engine + dataset runner
├── test_golden.py           # Pytest wrapper for golden set
└── __init__.py

tests/mocks/
├── ghostfolio_mock.py       # MockGhostfolioClient (drop-in replacement)
├── ghostfolio_responses.py  # Canned portfolio/order/account data
└── market_data_mock.py      # Mock OHLCV with pinned canonical prices
```

### Observability Infrastructure

```
agent/observability.py       # Core: trace, latency, error, token tracking
agent/state.py               # State schema (trace_log, node_latencies, error_log, token_usage)
agent/nodes/formatter.py     # Embeds observability into response JSON
agent/app.py                 # API endpoints (/api/feedback, response serialization)
```

### Verification Infrastructure

```
agent/nodes/verification.py  # Fact checking, hallucination detection, confidence scoring,
                             # domain constraints, authoritative consistency
agent/authoritative_sources/
├── __init__.py              # TOOL_TO_SOURCES mapping, get_source_by_id(), get_excerpts_for_tools()
├── sources.json             # 8 authoritative tax/compliance sources (IRC, IRS)
└── formatter.py             # Authoritative source formatting for response
agent/nodes/synthesis.py     # Source attribution prompts, verification-aware re-synthesis
agent/input_validation.py    # Input constraints (length, injection, non-empty)
```

### Reports

```
reports/
├── eval-results-*.json      # Dataset eval reports (run_evals.py)
├── golden-results-*.json    # Golden set reports (run_golden.py --report)
└── scenario-results-*.json  # Scenario reports (run_scenarios.py --report)
```
