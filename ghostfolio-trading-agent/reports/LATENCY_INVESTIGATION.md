# Latency Investigation Report

**Data source:** `eval-results-20260227T202547Z` (55 cases, mocked I/O).  
**Goal:** Identify where time is spent and recommend further improvements.

---

## 1. Current latency profile

| Metric     | Value                         |
| ---------- | ----------------------------- |
| **Mean**   | 18.4 s                        |
| **Median** | 18.1 s                        |
| **P90**    | 33.9 s                        |
| **Max**    | 44.6 s                        |
| **Min**    | 2.9 s (edge_invalid, 0 tools) |

All 55 cases are under the 120 s cap. The long tail is 30–45 s for multi-step and 3+ tool cases.

---

## 2. Where time is spent (pipeline)

The agent pipeline and LLM usage:

| Step                | LLM?        | Notes                                                                                                                                           |
| ------------------- | ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| **classify_intent** | 1× LLM      | Claude Sonnet 4, max_tokens=512, single round.                                                                                                  |
| **check_context**   | No          | In-memory TTL only; negligible.                                                                                                                 |
| **react_agent**     | 1–N× LLM    | 1 if tools batched, N if multi-step; max_tokens=2048, tool-calling.                                                                             |
| **execute_tools**   | No LLM      | I/O only; already parallel (ThreadPoolExecutor + parallel Ghostfolio/yfinance batching).                                                        |
| **synthesize**      | 0 or 1× LLM | Skipped for simple intents (general, lookup_symbol, edge_invalid) when ReAct returns text. Otherwise 1× Sonnet, max_tokens=2048, large context. |
| **verify**          | No          | Code-only fact/guardrail checks.                                                                                                                |
| **format_output**   | No          | Code-only.                                                                                                                                      |

So **total LLM calls per request:**

- **0-tool path (e.g. greeting, gibberish):** 2 calls (intent + ReAct, then → verify). Observed ~6.4 s mean for 0-tool cases → **~3.2 s per LLM** for small prompts.
- **1-tool path:** 3 calls (intent + ReAct + synthesize) + tool I/O. Observed ~14.1 s → ~3.7 s per LLM + I/O.
- **3–6 tool path:** Still 3 LLM calls when tools are batched in one ReAct step, but **context size grows** (many tool results). Observed 27–44 s → **synthesis and ReAct with 4–6 tool results dominate** (~10–14 s per LLM for heavy context).

Conclusion: **Latency is LLM-bound.** Tool execution is already parallel and not the bottleneck. The main levers are **number of LLM rounds**, **prompt/context size**, and **model choice per stage**.

---

## 3. Latency vs. tool count and category

### 3.1 By number of tools called

| # tools | Mean latency | N cases |
| ------- | ------------ | ------- |
| 0       | **6.4 s**    | 18      |
| 1       | **14.1 s**   | 12      |
| 2       | **24.6 s**   | 8       |
| 3       | **27.7 s**   | 11      |
| 4       | **33.9 s**   | 3       |
| 5       | **41.7 s**   | 2       |
| 6       | **42.0 s**   | 1       |

Roughly **+6–8 s per extra tool** from 0→1→2→3; 4–6 tools sit in the 34–42 s band. Parallel tool execution keeps 6 tools from being 2× the cost of 3; the growth is from **larger tool-result context** in ReAct and especially **synthesis**, not from more tool I/O.

### 3.2 Slowest categories (by mean)

| Category                         | Avg (s)     | N   | Notes                                        |
| -------------------------------- | ----------- | --- | -------------------------------------------- |
| signal_archaeology               | **33.3**    | 1   | 4 tools, complex.                            |
| **multi_step**                   | **32.8**    | 10  | 2–6 tools; main driver of P90.               |
| **risk_check**                   | **31.6**    | 4   | 3 tools (snapshot, market_data, guardrails). |
| journal_analysis                 | 26.3        | 1   | 2 tools.                                     |
| compliance                       | 26.1        | 2   | 3 tools.                                     |
| portfolio_health                 | 25.1        | 2   | 2 tools.                                     |
| …                                | …           | …   | …                                            |
| general / adversarial / edge\_\* | **3.8–6.6** | 14  | 0 tools; intent + ReAct only.                |

Multi_step and risk_check are the main targets for further latency work.

### 3.3 Top 10 slowest single cases

| Latency   | # tools | Category                | Example input (truncated)                               |
| --------- | ------- | ----------------------- | ------------------------------------------------------- |
| 44.6      | 5       | multi_step              | "Give me a complete investment review — portfolio h..." |
| 42.0      | 6       | multi_step              | "If I sell AAPL to buy MSFT, tax impli..."              |
| 38.7      | 5       | multi_step              | "Should I sell my worst performer and use the proce..." |
| 38.0      | 3       | risk_check              | "Should I sell GOOG?"                                   |
| 34.7      | 4       | multi_step              | "Show me my portfolio health, my recent performance"    |
| 33.9      | 3       | risk_check              | "Should I sell AAPL?"                                   |
| 33.6      | 4       | multi_step              | "Is my portfolio positioned well given my current g..." |
| 33.3      | 4       | signal_archaeology      | "What predicted the AAPL crash last quarter?"           |
| 30.5      | 2       | multi_step              | "I want to add $10,000 — which exis..."                 |
| 27.5–27.8 | 3       | risk_check / multi_step | NVDA position; tax loss; wash sale; etc.                |

So: **multi_step (4–6 tools) and 3-tool risk_check** account for almost all 30+ s runs.

---

## 4. Gaps in current observability

- **Eval reports do not store per-node latency.** The graph state includes `node_latencies` (classify_intent, react_agent_0, execute_tools_0, synthesize_0, verify_0, etc.), but `run_evals.py` only writes **total** `latency_seconds` per case. So we cannot see, from the JSON, how much time went to intent vs. ReAct vs. tools vs. synthesis.
- **No A/B breakdown by model or prompt size** (e.g. intent vs. synthesis) without adding instrumentation.

**Recommendation:** When writing the eval report, include `node_latencies` (or a summary, e.g. `classify_intent_s`, `react_s`, `execute_tools_s`, `synthesize_s`, `verify_s`) in each `per_case` entry. That will validate which node(s) to optimize first after changes.

---

## 5. Improvements already in place (reference)

Already done in this codebase:

- **Intent:** Single Sonnet call, 512 max_tokens.
- **ReAct:** Efficiency prompt to batch tools in one step; skip_synthesis for general/lookup_symbol/edge_invalid when ReAct returns final text.
- **Tools:** Parallel execution (ThreadPoolExecutor); shared portfolio_data/market_data to avoid duplicate fetches; batch yfinance; parallel Ghostfolio (holdings/performance/accounts); \_get_sector lru_cache.

So the remaining gains are mostly from **fewer or cheaper LLM calls** and **smaller context**.

---

## 6. Recommended improvements (in priority order)

### 6.1 Instrument eval with per-node latency (high value, low risk)

- In `run_evals.py`, when building each `per_case` for the report, add something like:
  - `node_latencies: result.get("node_latencies") or {}`  
    or a flattened subset:
  - `classify_intent_s`, `react_agent_s`, `execute_tools_s`, `synthesize_s`, `verify_s` (sum per node from `node_latencies` by prefix).
- Re-run evals and inspect, e.g. `synthesize_0` vs `react_agent_0` for 4–6 tool cases to confirm synthesis is a top cost before changing models or prompts.

### 6.2 Reduce synthesis context size (high value, medium risk)

- Synthesis currently injects up to **5000 chars per tool** (`synthesis.py` ~line 196). For multi_step or many tools, total context becomes very large → long synthesis latency.
- **Options:**
  - Lower per-tool cap to **3000** for “secondary” tools (e.g. everything except the 1–2 primary for the intent), or
  - For **multi_step**, build a short “summary” block per tool (e.g. 1–2 lines) instead of full JSON for non-primary tools, and keep full result only for the main tool(s).
- Validate with a few slow multi_step and risk_check evals to ensure key numbers are still present (no regressions on content/safety).

### 6.3 Try faster model for synthesis only (high value, quality risk)

- **Idea:** Use **Claude 3 Haiku** (or a smaller/faster Sonnet variant) **only for the synthesis node**, keeping Sonnet for intent and ReAct.
- **Rationale:** Synthesis is “draft a short, grounded reply from structured tool results”; it may tolerate a cheaper model better than intent/ReAct.
- **Process:** Run the 55-case eval with synthesis on Haiku; compare pass rate and safety/content scores. If regressions are limited and acceptable, keep it; otherwise revert synthesis to Sonnet and rely on 6.2 and 6.4.

### 6.4 Lower max_tokens where safe (medium value, low risk)

- **ReAct:** First turn is usually “tool_calls” with small text. **max_tokens=2048** is large; try **1024** for the ReAct node to cap completion time on tool-only turns.
- **Synthesis:** Many answers are &lt; 800 chars. Try **synthesis max_tokens=1024** and monitor for truncation on long multi_step answers; increase slightly if needed (e.g. 1536).

### 6.5 Intent caching (medium value, medium risk)

- **Idea:** Cache `(normalized_user_message_hash) → (intent, extracted_params)` with a small TTL (e.g. 60 s) or per-request session only, to avoid a second intent call for exact duplicate questions (e.g. retries, duplicate tabs).
- **Risks:** Stale cache if user edits and resubmits; cache key design (e.g. strip whitespace, limit length). Best as an optional feature behind a flag and metrics to measure hit rate and impact.

### 6.6 Streaming synthesis (TTFB / perceived latency only)

- Use `llm.stream()` in the synthesis node and stream tokens to the client. **Total time to last token** is largely unchanged; **time to first token (TTFB)** improves, which helps UX.
- Only relevant when the UI can consume a stream; no change in eval total latency unless evals are changed to measure TTFB.

### 6.7 Multi_step-specific synthesis prompt (lower priority)

- For **intent=multi_step**, use a synthesis system prompt that (a) stresses “one short paragraph per area” and (b) uses **summarized** tool results (see 6.2) to shrink context. This targets the 32.8 s multi_step average and the 41–45 s tail.

---

## 7. Summary table

| Action                                      | Expected latency impact                          | Risk                                  | Effort               |
| ------------------------------------------- | ------------------------------------------------ | ------------------------------------- | -------------------- |
| Add node_latencies to eval report           | No direct reduction; unblocks data-driven tuning | None                                  | Low                  |
| Reduce synthesis context (cap or summaries) | −2–5 s on 4–6 tool cases                         | Content regressions if over-truncated | Medium               |
| Haiku for synthesis only                    | −2–4 s on all tooled cases                       | Quality/safety regressions            | Medium + eval        |
| ReAct/synthesis max_tokens 1024             | −0.5–2 s on large completions                    | Truncation on long answers            | Low                  |
| Intent cache (optional)                     | −3 s on cache hit only                           | Stale responses if misused            | Medium               |
| Streaming synthesis                         | Better TTFB only                                 | None for total latency                | Low (if UI supports) |
| Multi_step-specific synthesis + summaries   | −3–6 s on multi_step                             | Content on complex answers            | Medium               |

**Suggested order:** (1) Add **node_latencies** to the eval report and confirm synthesis/ReAct dominance on slow cases; (2) **Reduce synthesis context** and/or **lower max_tokens**; (3) **Try Haiku for synthesis** with full 55-case eval and roll back if quality drops; (4) Consider **intent cache** and **streaming** as follow-ups.

---

## 8. Files to change (concrete)

- **Per-node latency in evals:** `tests/eval/run_evals.py` — in `write_eval_report`, add to each `per_case` item:  
  `"node_latencies": r.get("node_latencies"),`  
  (and ensure `run_single_eval` passes through `result.get("node_latencies")` from the graph state into `r`; today the graph returns state that becomes `result`, and `format_output` puts `node_latencies` inside `response.observability`. So either expose `result.get("node_latencies")` from the final state in `run_single_eval` or copy from `response["observability"]["node_latencies"]` into `r` and then into the report.)
- **Synthesis context:** `agent/nodes/synthesis.py` — reduce per-tool truncation (e.g. 5000 → 3000) or add summarization for non-primary tools.
- **max_tokens:** `agent/nodes/react_agent.py` (e.g. 2048 → 1024), `agent/nodes/synthesis.py` (e.g. 2048 → 1024 or 1536).
- **Synthesis model:** `agent/nodes/synthesis.py` — add a config or env to switch synthesis to Haiku and run evals.

This gives a clear path to the next latency gains with measurable, low-risk steps first and optional higher-impact, quality-gated steps (Haiku, aggressive truncation) second.
