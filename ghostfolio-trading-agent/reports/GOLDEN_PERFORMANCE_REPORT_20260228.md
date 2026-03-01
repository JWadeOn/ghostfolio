# Golden Set Performance Report — 2026-02-28

**Run:** `python3 tests/eval/run_golden.py --report`  
**Report file:** `golden-results-20260228T232835Z.json`  
**Total time:** 97.3 s

---

## Summary

| Metric                    | Value                                       |
| ------------------------- | ------------------------------------------- |
| **Total cases**           | 31                                          |
| **Passed**                | 30                                          |
| **Pass rate**             | **96.8%**                                   |
| **Target (PROJECT_PLAN)** | ≥80%                                        |
| **Target met**            | Yes                                         |
| **Tool success rate**     | 100% (20 cases called tools; 0 tool_errors) |
| **Avg latency per case**  | 2.77 s                                      |
| **All dimensions passed** | No — 1 failure on tool selection            |

---

## Single failure

| Case       | Input                                                              | Dimension          | Error                                 |
| ---------- | ------------------------------------------------------------------ | ------------------ | ------------------------------------- |
| **gs-023** | "Would buying more NVDA over-concentrate my tech sector exposure?" | **Tool selection** | Missing tools: `['guardrails_check']` |

The agent called `get_portfolio_snapshot` and `get_market_data` but did **not** call `guardrails_check`. The golden case expects `["get_portfolio_snapshot", "guardrails_check"]` for this concentration/sector question. So the model treated it as a market/portfolio lookup only and did not run the guardrails (sector concentration) check.

**Suggested fix:** Strengthen the ReAct prompt for “over-concentrate”, “sector exposure”, “sector imbalance” to explicitly require `guardrails_check()` (no symbol) for portfolio-level concentration/sector questions, distinct from a specific buy-size evaluation.

---

## Dimension breakdown (all 31 cases)

- **Tools:** 30/31 passed (gs-023 missing `guardrails_check`)
- **ToolExec:** 31/31 (no tool execution errors)
- **Sources:** 31/31
- **Content:** 31/31
- **Negative:** 31/31 (no hallucination/give-up)
- **GroundTruth:** 31/31
- **Structural:** 31/31 (react steps and latency within budget)

---

## Latency

- **Mean:** 2.77 s per case
- **Pattern:** 1-step (0-tool) cases ~1–2 s; 2-step (1–3 tools) cases ~2–4 s; 3-step (gs-022) ~4–5 s
- All within structural budgets (`max_latency_seconds` / `max_react_steps` per case)

---

## Conclusion

Golden set is **96.8%** with one repeatable failure: gs-023 (sector concentration question) does not invoke `guardrails_check`. Fixing that routing in the system prompt should bring the suite to **31/31 (100%)** while keeping latency and tool success within targets.
