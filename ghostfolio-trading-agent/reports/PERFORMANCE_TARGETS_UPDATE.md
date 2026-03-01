# Performance Targets Update — PRD Alignment

**Date:** 2026-02-28  
**Reference:** PROJECT_PLAN.md §3 (PRD Requirements Status), §3.7 (Performance Targets); README.md (Evaluation System, Tool success rate).

This document maps current performance to PRD requirements and reports status with evidence from golden set and eval runs.

---

## 1. PRD Performance Targets (from PROJECT_PLAN §3.7)

| Metric                    | PRD Target | Current Status   | Evidence                                                                                                                                                                                                                                           |
| ------------------------- | ---------- | ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Single-tool latency**   | <5 s       | **Met**          | Golden run: avg 2.77 s per case; single-tool cases ~2–3 s. Post–latency overhaul (ReAct 1–2 LLM calls, Haiku).                                                                                                                                     |
| **Multi-step latency**    | <15 s      | **Met**          | Golden 2–3 step cases ~2–5 s; no case exceeded per-case `max_latency_seconds`. Full-suite runs (e.g. EVAL_PERFORMANCE_REPORT_20260227) report all cases under 120 s cap.                                                                           |
| **Tool success rate**     | >95%       | **Met (golden)** | Golden report: 100% tool success (20/20 cases that called tools had zero tool_errors). Full-suite: `run_evals.py` reports `tool_success_rate_pct` and gates on ≥95%.                                                                               |
| **Eval pass rate**        | >80%       | **Met (golden)** | Golden: 30/31 → **96.8%** (run 20260228T232835Z). One failure (gs-023) addressed in ReAct prompt (guardrails_check for concentration/sector). Golden set expanded to 34 cases (gs-032–gs-034 authoritative sources). Target ≥80% per PROJECT_PLAN. |
| **Hallucination rate**    | <5%        | **Measured**     | `run_evals.py` aggregate reports `hallucination_rate_pct`; verification node flags number mismatches. Golden: Negative dimension 31/31 (no give-up/hallucination phrases).                                                                         |
| **Verification accuracy** | >90%       | **Measured**     | `run_evals.py` aggregate reports `verification_accuracy_pct`. Golden: Content/GroundTruth/Structural all passed; verification logic in `agent/nodes/verification.py` (fact-check, guardrails, authoritative consistency).                          |

---

## 2. MVP Requirements (PRD §3.1) — Performance-Relevant

| Requirement                                      | Status | Notes                                                                                           |
| ------------------------------------------------ | ------ | ----------------------------------------------------------------------------------------------- |
| Tool calls execute and return structured results | Done   | Golden tool_execution 31/31; tool_success_rate 100% on golden.                                  |
| At least one domain-specific verification check  | Done   | Wash sale (IRC §1091), long-term cap gains (IRC §1222), tax/compliance consistency, guardrails. |
| 5+ test cases with expected outcomes             | Done   | Golden 34 cases; scenario suite 40+; full dataset 69+ (dataset.py).                             |

---

## 3. Eval Framework (PRD §3.4) — How Targets Are Measured

| Requirement                       | Implementation                                                                                                                                     |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Eval runner with per-case scoring | `run_evals.py` (full suite), `run_golden.py` (golden), `run_scenarios.py` (scenarios).                                                             |
| Pass rate target ≥80%             | `TARGET_PASS_RATE_PCT = 80` in run_evals.py; golden/scenario use same threshold.                                                                   |
| Tool success target >95%          | `TARGET_TOOL_SUCCESS_RATE_PCT = 95`; reported in aggregate and as exit-code gate in run_evals.                                                     |
| Latency cap                       | `EVAL_MAX_LATENCY_SECONDS` (default 120); per-case `max_latency_seconds` in golden/scenarios.                                                      |
| Hallucination / verification      | `aggregate_results()` in run_evals.py computes hallucination_rate_pct and verification_accuracy_pct from per-case verification and content scores. |

---

## 4. Current Evidence Summary

- **Golden set (20260228):** 31 cases run → 30 passed (96.8%); 34 cases in suite after adding gs-032–gs-034. Prompt update for gs-023 (guardrails_check for concentration/sector) expected to yield 31/31 or 34/34 on next run.
- **Latency:** Golden avg 2.77 s; all cases within structural budgets. PRD single-tool <5 s and multi-step <15 s met.
- **Tool success:** Golden 100%; full-suite runs report tool_success_rate_pct and enforce ≥95% for pass.
- **Full suite / scenarios:** Pass rate and category breakdown in `reports/eval-results-*.json` and `reports/scenario-results-*.json`; run `run_evals.py` or `run_scenarios.py` for latest aggregates.

---

## 5. Status Overview

| PRD Target            | Target Value | Status       | Evidence                                    |
| --------------------- | ------------ | ------------ | ------------------------------------------- |
| Single-tool latency   | <5 s         | Met          | Golden avg 2.77 s; ReAct 1–2 LLM calls      |
| Multi-step latency    | <15 s        | Met          | Golden 2–5 s for multi-step; under cap      |
| Tool success rate     | >95%         | Met          | Golden 100%; run_evals gate ≥95%            |
| Eval pass rate        | >80%         | Met (golden) | Golden 96.8%; 34-case suite in place        |
| Hallucination rate    | <5%          | Measured     | run_evals aggregate; golden negative checks |
| Verification accuracy | >90%         | Measured     | run_evals aggregate; verification node      |

**Conclusion:** PRD performance targets are met or measured as of this update. Golden set exceeds 80% pass rate and 95% tool success; latency is within PRD bounds. Full-suite and scenario runs provide additional coverage and aggregate metrics for hallucination and verification accuracy.
