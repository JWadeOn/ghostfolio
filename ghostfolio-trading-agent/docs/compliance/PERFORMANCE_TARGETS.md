# Performance Targets

> Last updated: 2026-02-28

## Current Measurements

| Metric                           | Target | Current                | Status | Source                                       |
| -------------------------------- | ------ | ---------------------- | ------ | -------------------------------------------- |
| End-to-end latency (single-tool) | <5s    | **Avg 2.8s**           | MET    | Scenario runner (43 cases)                   |
| Multi-step latency (3+ tools)    | <15s   | **Max 8.6s**           | MET    | Scenario runner (multi_tool cases)           |
| Tool success rate                | >95%   | **100%** (67/67 calls) | MET    | Golden + Scenario runners                    |
| Eval pass rate                   | >80%   | **96.8-100%**          | MET    | Golden: 30-31/31, Scenarios: 43/43           |
| Hallucination rate               | <5%    | **Not measured**       | GAP    | Fact-checking exists but no aggregate metric |
| Verification accuracy            | >90%   | **Not measured**       | GAP    | Verification runs but no precision metric    |

## Unit Test Health

| Suite         | Pass | Fail | Skip | Notes                                                  |
| ------------- | ---- | ---- | ---- | ------------------------------------------------------ |
| Unit tests    | 131  | 0    | 2    | 2 pre-existing verification test failures (deselected) |
| test_graph.py | —    | All  | —    | Pre-existing: intent mock not working                  |

## Eval Layer Results

### Golden Set (regression gate)

```
Last run: 2026-02-28
Result:   30-31/31 (96.8-100%)
Flaky:    gs-009 (tax keyword), gs-011 (marginal latency)

Per-dimension:
  Tool Selection:  31/31 (100%)
  Tool Execution:  31/31 (100%)
  Source Citation:  31/31 (100%)
  Content:          30-31/31 (96.8-100%)
  Negative:         31/31 (100%)
  Ground Truth:     31/31 (100%)
  Structural:       30-31/31 (96.8-100%)
```

### Labeled Scenarios (coverage map)

```
Last run: 2026-02-28
Result:   43/43 (100%)

Per-dimension:
  Tool Selection:   43/43 (100%)
  Tool Execution:   43/43 (100%)
  Content:          43/43 (100%)
  Negative:         43/43 (100%)

Tool success rate:  24/24 (100%)
Avg latency:        2.8s
Max latency:        8.6s
```

### Dataset (weighted scoring)

```
Last run: Not run post-tool-consolidation
Action:   Needs validation run
```

## Gaps to Close

### G-2: Hallucination Rate Metric

The fact-checking infrastructure exists (`_check_facts()` in verification.py) but doesn't aggregate
into a percentage metric. To close this gap:

- Count fact-check failures across golden/scenario runs
- Compute: `hallucination_rate = fact_check_failures / total_responses_with_numbers`
- Add to eval report output

### G-3: Verification Accuracy Metric

Verification runs on every response but we don't measure its precision. To close this gap:

- Create test cases with known-correct and known-incorrect synthesis
- Measure: true positives (correctly flagged) / total flags = precision
- Measure: true positives / (true positives + false negatives) = recall
- Add to eval report output
