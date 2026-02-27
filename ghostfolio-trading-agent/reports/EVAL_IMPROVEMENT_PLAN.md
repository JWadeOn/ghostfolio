# Eval System Improvement Plan — Meet 80% Pass Target

**Current state (20260226T231954Z):** 65.2% pass (15/23), avg score 0.858  
**Target:** ≥80% pass rate, pass threshold 0.8, no regressions on previously passing categories

This plan covers **eval system** changes (harness, dataset, scoring, reporting) and the **agent changes** the evals will validate, ordered so the eval system improvements support measuring and gating on the target.

---

## 1. Targets and Success Criteria

| Metric            | Target                           | Current              | Gap                |
| ----------------- | -------------------------------- | -------------------- | ------------------ |
| **Pass rate**     | ≥ 80% (≥19/23)                   | 65.2% (15/23)        | +4 cases must pass |
| **Per-case pass** | overall ≥ 0.8 and no errors      | —                    | —                  |
| **Regression**    | No drop in pass rate vs baseline | baseline = 15 passed | 0 fewer passes     |
| **Latency**       | All &lt; 120s                    | All pass             | —                  |

**Definition of “pass” (today):** `overall_score >= PASS_THRESHOLD (0.8)` **and** `errors == []`. A case fails if it has any error, even when score ≥ 0.8.

**Success:** After implementing this plan, a full eval run must report pass_rate_pct ≥ 80 and aggregate regression_delta_pct ≥ 0 (or null baseline).

---

## 2. Eval System Improvements

These changes make the eval harness more robust, interpretable, and aligned with the 80% goal.

### 2.1 Regression baseline and reporting (run_evals.py + reports)

- **Auto-baseline:** When writing `eval-results-{timestamp}.json`, compute `regression_delta_pct` against the **latest** previous report in `reports/` (same `total_cases`), e.g. `pass_rate_pct - baseline_pass_rate_pct`. If no suitable baseline, keep `null`.
- **Target in report:** Add to `run_metadata`: `"target_pass_rate_pct": 80` and a boolean `"target_met": aggregate["pass_rate_pct"] >= 80`.
- **Artifact:** One canonical “latest” baseline file (e.g. `reports/eval-baseline.json` or the most recent `eval-results-*.json` with 23 cases) so CI or local runs can compare consistently.

_Files:_ `tests/eval/run_evals.py` (`write_eval_report`, aggregation), optionally a small script or env to set baseline path.

### 2.2 Per-dimension and category gates (optional, for debugging)

- **Per-dimension breakdown in aggregate:** In `aggregate_results()` (or in the written report), add `by_category[c]["avg_&lt;dim&gt;"]` for intent, tools, content, safety, confidence, verification so we can see which dimension pulls down a category.
- **Category-level targets (informal):** Document expected minimums per category (e.g. “regime*check: 2/3 pass”) in `EVAL_ASSESSMENT*\*`or in`dataset.py` as comments, and in this plan’s “Agent work” section so the eval system is the single source of truth for “did we fix the 8 failures?”

No code change required for “gates” beyond the existing per-case `passed` and aggregate `pass_rate_pct`.

### 2.3 Dataset and scoring alignment with product intent

- **Tool expectations:** Keep `expected_tools` as-is for regime_check, opportunity_scan, risk_check (get_market_data / get_portfolio_snapshot where defined). If product decides “sell GOOG” can be answered with only `trade_guardrails_check`, then relax that one case and document in `dataset.py` and in this plan.
- **Synonyms:** Extend `CONTENT_SYNONYMS` in `run_evals.py` only when a phrase is truly equivalent (e.g. “take profit” ↔ “target” for content or for a future “required_phrases” list). Prefer fixing synthesis to match existing terms before adding synonyms.
- **Safety and should_not_contain:** Keep “promise” and “guarantee” blocklist; add “promised” to the guarantee case if not already covered (dataset already has “will return”, “guaranteed”, “promise”).

_Files:_ `tests/eval/dataset.py`, `tests/eval/run_evals.py` (CONTENT_SYNONYMS, safety term list if centralized).

### 2.4 Pass definition (strict vs score-only)

- **Current:** Pass = (overall ≥ 0.8 and errors == []). One error fails the case.
- **Option A (recommended for now):** Keep this. Fix the 8 failing cases by fixing agent behavior and verification so they have no errors and score ≥ 0.8.
- **Option B (only if needed):** Add a “soft pass” for reporting: e.g. `passed_strict` (current) and `passed_soft = (overall >= 0.8)` and report both. Use `passed_strict` for the 80% target and use `passed_soft` for trend. Do not lower the bar for “target met” to soft pass without explicit product sign-off.

_Files:_ `run_single_eval` in `tests/eval/run_evals.py` if Option B is adopted.

### 2.5 Reproducibility and CI

- **Seed / temperature:** Evals already use temperature 0 in EVAL_MODE; document in README or run_evals that EVAL_MODE=1 (or true) is required for reproducible evals.
- **CI (optional):** Add a job that runs `run_evals` with mocks, saves the artifact, and fails if `target_met` is false or `regression_delta_pct < 0` when baseline exists. Baseline could be the previous main-branch artifact or a committed `reports/eval-baseline.json`.

_Files:_ CI config, `tests/eval/run_evals.py` (ensure EVAL_MODE documented), `README` or `tests/eval/README.md`.

---

## 3. Agent and Verification Changes (to be validated by evals)

These address the 8 failing cases. The eval system will measure success; implement in agent (and optionally small dataset/scoring tweaks) so that 4+ of the 8 start passing and no current pass regresses.

### 3.1 Tool usage (ReAct) — 4 cases

**Goal:** For the four failures where “expected tool X was not called,” the agent consistently calls the expected tools.

| Case                       | Missing tools                           | Change                                                                                                                                                           |
| -------------------------- | --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| regime_check (id 1)        | get_market_data                         | ReAct: for regime_check always call get_market_data (e.g. SPY or user symbols) in addition to detect_regime. Optionally add intent→tool hint in graph or prompt. |
| opportunity_scan (id 2, 7) | get_market_data                         | ReAct: for opportunity_scan require or strongly encourage get_market_data for symbols from scan or regime.                                                       |
| risk_check (id 3)          | get_portfolio_snapshot, get_market_data | ReAct: for “can I buy $X” / “add position” require get_portfolio_snapshot and get_market_data before trade_guardrails_check.                                     |
| risk_check (id 10)         | get_portfolio_snapshot, get_market_data | Same as above for “should I sell &lt;symbol&gt;” or relax dataset expected_tools for sell-only if product agrees.                                                |

_Files:_ `agent/nodes/react_agent.py` (REACT_SYSTEM_PROMPT, possibly intent in context), optionally routing or tool hints by intent in the graph.

### 3.2 Verification and guardrails — 4 cases

**Goal:** No verification or guardrail failures for: opportunity_scan (derived numbers), chart_validation (user level 320), risk_check (small %, target/take profit), and no “promise” in general (guarantee case).

| Case                       | Issue                                            | Change                                                                                                                                                                                                                                                                                                                                                                                    |
| -------------------------- | ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| opportunity_scan (id 2, 7) | Numbers 21.96, 21.0 not in tool results          | verification: for opportunity_scan skip or relax fact-check for derived numbers (e.g. reward per share, EMA(21), or any \|value\| &lt; 25 when context suggests scan_strategies output).                                                                                                                                                                                                  |
| chart_validation (id 5)    | 320.0 not found; missing stop loss               | (a) verification: for chart_validation, skip fact-check for numbers that appear in the **user message** (e.g. from extracted price_levels or simple regex). (b) Guardrail: for chart_validation either require synthesis to include stop (and optionally target) when suggesting an action, or relax guardrail when the reply is strictly “valid / not valid” without a trade suggestion. |
| risk_check (id 3, 9)       | Missing target/take profit; (id 9) 0.1 not found | (a) verification: for risk_check skip very small percentages (e.g. \|v\| &lt; 1) in “%” context. (b) Synthesis/verification: for risk_check when suggesting add/sell/hold, require “target” or “take profit” or “no target suggested” so guardrail passes, or relax guardrail when the reply is only “add more / sell portion / hold” with no levels.                                     |
| general (id 4)             | Output contains “promise”                        | Synthesis/safety: add explicit “Never use the word ‘promise’ or ‘promised’” for guarantee-style queries; optionally add a small post-check that rewrites or flags “promise” in response when intent is general and user asked for guarantee.                                                                                                                                              |

_Files:_ `agent/nodes/verification.py` (\_check_facts intent-specific skips, \_check_guardrails), `agent/nodes/synthesis.py` (general/guarantee prompt, optional blocklist), dataset `should_not_contain` if adding “promised”.

### 3.2.1 Verification logic summary (code-level)

- **verification.py**
  - `_check_facts(..., intent` already has create_activity and regime_check/opportunity_scan/price_quote/chart_validation skips. Extend:
    - **opportunity_scan:** Skip numbers with |value| &lt; 25 or context containing “reward”, “EMA(”, “per share” (or a small allowlist of scan_strategies-like patterns).
    - **chart_validation:** Skip numbers that appear in `state["extracted_params"]` (e.g. price_levels) or in the last user message (e.g. regex for $320 or 320).
    - **risk_check:** Skip when |value| &lt; 1 and “%” in context (already near that with current “small-magnitude” skip; ensure 0.1 and -0.1 included, e.g. skip |v| &lt; 1).
  - **\_check_guardrails:** For chart_validation, optionally: if synthesis does not contain strong trade verbs (e.g. “buy”/“sell”/“add”) or is clearly “valid/not valid” only, do not require stop/target. Prefer tightening synthesis over over-relaxing guardrails.

- **synthesis.py**
  - General intent: one line “Never use the word ‘promise’ or ‘promised’ in any form. For guarantee-style requests, say ‘cannot guarantee’ or ‘not financial advice’ only.”

_Files:_ `agent/nodes/verification.py`, `agent/nodes/synthesis.py`.

### 3.3 Dataset / eval-scoring tweaks (only if product agrees)

- **risk_check “Should I sell GOOG?”:** If the product accepts “sell evaluation with trade_guardrails_check only,” set `expected_tools` to `["trade_guardrails_check"]` (and optionally get_portfolio_snapshot for context) and document. Otherwise keep current expected_tools and fix ReAct (3.1).
- **Synonym “promised”:** Add to the guarantee case `should_not_contain`: `"promised"` if not already there.

_Files:_ `tests/eval/dataset.py`.

---

## 4. Implementation Order

1. **Eval system (no agent change)**
   - Add `target_pass_rate_pct` and `target_met` to report; optionally regression_delta vs latest previous run and `eval-baseline` usage.
   - Optionally add per-dimension averages by category for debugging.
   - Document EVAL_MODE and, if desired, CI and baseline.

2. **Agent: verification (3.2)**
   - Implement opportunity_scan and risk_check number skips and chart_validation user-level skip in `verification.py`.
   - Adjust guardrails for chart_validation and risk_check (synthesis requirement or guardrail relaxation).
   - Add “promise”/“promised” rule and dataset tweak.
   - Run evals; expect to recover ~3–4 of the 8 (e.g. opportunity_scan 2, risk_check 9, chart_validation 5, general 4).

3. **Agent: ReAct tool usage (3.1)**
   - Strengthen ReAct (and optional intent→tool hints) so regime_check, opportunity_scan, and risk_check call get_market_data (and risk_check also get_portfolio_snapshot where expected).
   - Run evals; expect to recover regime 1, risk_check 3 and 10, and to hold the gains from step 2.

4. **Re-run and lock baseline**
   - Full run with EVAL_MODE=1; confirm pass_rate_pct ≥ 80 and no regressions.
   - Save or tag the run as the new baseline for future regression_delta_pct.

5. **CI (optional)**
   - Add job: run evals, artifact report, fail if not target_met or regression_delta_pct &lt; 0.

---

## 5. Out of Scope (for this plan)

- Changing pass threshold below 0.8 or moving to “soft pass” as the official target without product agreement.
- Adding new eval cases or new categories (can be a follow-up).
- Non-mock evals (live API) or human evals.
- Changing model or tool set; plan assumes current agent surface.

---

## 6. Checklist to “Meet target”

- [ ] Eval report includes `target_met` and (optional) `regression_delta_pct` vs baseline.
- [ ] Verification: opportunity_scan + chart_validation + risk_check number/guardrail changes merged; general “promise” rule and dataset “promised” if needed.
- [ ] ReAct: regime_check, opportunity_scan, risk_check tool-ordering updates merged.
- [ ] Full eval run (EVAL_MODE=1) shows pass_rate_pct ≥ 80% and 0 regressions.
- [ ] Baseline updated and, if applicable, CI gates evals on target and regression.

Once these are done, the eval system is in place to measure and guard the 80% target; the remaining work is agent/verification implementation and re-running the suite to confirm.
