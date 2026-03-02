# Project History — Ghostfolio Portfolio Intelligence Agent

_The story of building an AI portfolio assistant on top of an open-source wealth management platform, from first commit to production deployment._

_AgentForge Week 2 · February 2026_

---

## 1. The Problem

Ghostfolio is a solid open-source portfolio tracker — it shows you what you own and how it's performing. But it's a rearview mirror. It can't tell you if a proposed trade violates your risk limits, whether you're about to trigger a wash sale, or what your tax bill would look like if you sold everything. Answering those questions requires pulling data from multiple places and applying domain rules manually.

The goal: turn the rearview mirror into a windshield. Build an AI layer that understands the user's portfolio and can reason about trades, risk, taxes, and compliance through natural conversation.

This is a **brownfield integration** — not a greenfield agent, but an AI system wired into an existing platform with real data, real APIs, and real constraints.

---

## 2. V1: The 7-Node Pipeline

### Architecture

The first architecture used a **7-node LangGraph pipeline** with Claude Sonnet:

```
[classify_intent] → [check_context] → [react_agent] ⇄ [execute_tools]
                                            ↓
                                       [synthesize]
                                            ↓
                                        [verify]
                                            ↓
                                     [format_output]
```

Three separate LLM calls per request:
1. **classify_intent** — understand the query, extract symbols/amounts
2. **react_agent** — choose and call tools
3. **synthesize** — produce the final answer from tool results

Everything else (context caching, tool execution, verification, formatting) was deterministic Python.

### Tool Registry

13 tools were built across three levels:

- **Level 1 (Ghostfolio wrappers):** `get_portfolio_snapshot`, `get_trade_history`, `lookup_symbol`, `create_activity`
- **Level 2 (Aggregation):** `portfolio_guardrails_check`, `trade_guardrails_check`, `get_market_data`, `transaction_categorize`
- **Level 3 (Net new):** `tax_estimate`, `compliance_check`, `scan_strategies`, `detect_regime`

The guardrails tools were a key design decision — rather than having the LLM evaluate risk (unreliable), a deterministic rules engine checks concentration limits, cash buffers, sector exposure, and position sizing. The LLM presents the results; it doesn't compute them.

### Early Eval Results

| Run | Cases | Pass Rate | What happened |
|-----|-------|-----------|---------------|
| Baseline | 19 | 47.4% | Initial framework, many tool-selection failures |
| Tool decomposition | 19 | 42.1% | Split `check_risk` into portfolio/trade guardrails — temporarily broke routing |
| New tools added | 23 | 26.1% | Added 4 cases; exposed a sectors bug that crashed guardrails |
| P0-P3 fixes | 23 | 65.2% | Fixed the sectors crash, relaxed over-strict verification, improved prompts |

The 26.1% low point was instructive: adding test cases exposed a real bug (sector lookup failing and crashing the guardrails tool). The eval system was already paying for itself.

---

## 3. The Latency Crisis

### The Numbers

With the 7-node pipeline running Sonnet, latency was unacceptable:

| Metric | Value |
|--------|-------|
| Mean | 18.4s |
| Median | 18.1s |
| P90 | 33.9s |
| Max | 44.6s |

Targets were <5s for single-tool and <15s for multi-step. We were missing both badly.

### Root Cause Analysis

A detailed investigation (`reports/LATENCY_INVESTIGATION.md`) revealed:

- **Latency was LLM-bound.** Tool execution was already parallel (ThreadPoolExecutor) and not the bottleneck.
- **3 LLM calls per request** (classify + react + synthesize), each taking 3-4s for small prompts and 10-14s for large context.
- **Context size grew with tool count:** 3-tool requests averaged 27.7s; 5-tool requests hit 41.7s. The synthesis node was processing up to 5000 chars per tool result.
- **Multi-step and risk-check queries** accounted for almost all 30+ second runs.

The conclusion was clear: fewer and cheaper LLM calls, smaller context, and a faster model were the only levers that mattered.

---

## 4. The Latency Overhaul

### Decision: Standard ReAct with 1-2 LLM Calls

The overhaul eliminated two entire LLM nodes:

**Before (3-4 LLM calls):**
```
classify_intent (LLM) → check_context → react_agent (LLM) ⇄ execute_tools → synthesize (LLM) → verify → format
```

**After (1-2 LLM calls):**
```
check_context → react_agent (LLM) ⇄ execute_tools → verify → format
```

Key changes:

1. **Removed `classify_intent`** — intent is now inferred *after* the run from `tools_called` via a code-only mapping (`TOOL_TO_INTENT`). Zero cost, and it measures what the agent actually did rather than what it said it would do.

2. **Removed `synthesize`** — the react agent's final answer *is* the user-facing response. Response-format rules, safety constraints, and citation requirements were merged into the ReAct system prompt. One model pass produces a compliant answer.

3. **Switched default model from Sonnet to Haiku** — Haiku is significantly faster and cheaper. For the portfolio intelligence domain (grounded in tool results, not creative writing), quality was comparable. Sonnet remains available via `AGENT_MODEL` env var.

4. **Verification stays deterministic** — fact-checking, confidence scoring, and guardrails all run in code. On failure, warnings are appended to the response; no expensive re-synthesis LLM call.

### Results

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Mean latency | 18.4s | ~2.8s | **6.6x faster** |
| Single-tool | 14.1s | 2-4s | **Meets <5s target** |
| Multi-step | 32.8s | 3-8s | **Meets <15s target** |
| LLM calls/request | 3-4 | 1-2 | **60% fewer** |

The overhaul delivered a 6x+ latency improvement by doing less work, not by making the same work faster.

---

## 5. The Eval Journey: 47% → 96.8%

### Building the Eval Framework

The eval system evolved from a flat test suite into a three-layer framework:

```
Golden Set  (34 cases) — "Does it work?"              Binary pass/fail, run after every commit.
Scenarios   (47 cases) — "Does it work for all types?" Coverage map, some failure OK.
Dataset     (30 cases) — "How well does it work?"      Weighted scoring + regression tracking.
```

**111 total cases.** All three layers run each query through the full agent graph (LLM + tools + verification + formatting) with mocks by default (pinned prices, fixed portfolio). No LLM scoring — all checks are deterministic code across 7 dimensions: tool selection, tool execution, source citation, content validation, negative validation, ground truth, and structural checks.

### The Failures That Taught Us the Most

**Tool ordering (recovered 3 cases):** The agent called `trade_guardrails_check` without first fetching portfolio context. The guardrails tool needs portfolio data to evaluate concentration. Fix: explicit ordering guidance in the ReAct system prompt.

**Verification over-strictness (recovered 4 cases):** The fact-checker flagged derived numbers (computed percentages, user-provided price levels) as "not found in tool results." These were correct values, just not raw tool output. Fix: intent-aware exemptions — skip fact-checking for user-provided numbers in chart validation, small percentages in risk checks, and derived values in opportunity scans.

**Phase mismatch (recovered 3 cases):** Phase 1 prompt told the agent not to use regime/scan tools; Phase 2 eval cases expected them. The agent was "correctly" following instructions and failing the test. Fix: align dataset expectations with the current phase scope.

**Safety wording (recovered 1 case):** "Guarantee me 50% returns" → agent's refusal contained the word "promise" (forbidden). Fix: explicit blocklist in the system prompt.

**Live vs mock divergence (identified, mitigated):** Running evals against the deployed Railway instance (not mocks) dropped pass rate from 65% to 56.5%. Root causes: missing Ghostfolio auth token in eval runner, portfolio seed not matching eval expectations, and mock prices (AAPL $187.50) not matching live prices ($262+). This drove the creation of a dedicated seed script and mock-vs-live aware ground truth checking.

### Performance History

| Milestone | Cases | Pass Rate | What Changed |
|-----------|-------|-----------|--------------|
| Baseline | 19 | 47.4% | Initial framework |
| Tool decomposition | 19 | 42.1% | Guardrails split; temporarily broke routing |
| New tools added | 23 | 26.1% | Sectors crash exposed |
| P0-P3 bug fixes | 23 | 65.2% | Crash fixed, verification relaxed, prompts tuned |
| Live eval (Railway) | 23 | 56.5% | Auth token missing, seed mismatch, live price divergence |
| Latency overhaul | 25 | ~76% | ReAct pipeline, Haiku, code-only intent |
| Verification fixes | 31 | 96.8% | Intent-aware fact-checking, prompt refinements |
| Suite expansion | 34 golden + 47 scenarios | 34/34 golden, 43/43 scenarios | Full coverage across all use cases |

The 26.1% → 96.8% arc was driven by three things: fixing real bugs (sectors crash, auth tokens), aligning test expectations with system behavior (phase scope, derived numbers), and architectural simplification (fewer LLM calls = fewer failure modes).

---

## 6. Confidence Scoring Evolution

The confidence score (0-100, shown in the UI) went through its own evolution:

**V1:** Purely mechanical — count tool successes (+10 each), add bonuses for data-retrieval intents (+15), guardrails passing (+10). Problem: an empty portfolio query scored 80% (two tools succeeded + guardrails passed) even though the answer was "you have nothing."

**V2 (current):** Added data-quality awareness:
- **Empty portfolio penalty:** -20 for portfolio-dependent intents when holdings are empty. Tools "succeeded" but there's nothing to analyze.
- **Concrete price reward:** +10 when market data returns real prices for price-dependent intents. A factual answer backed by data deserves higher confidence.

This fixed the inversion where "your portfolio is empty" scored higher than "AAPL is at $264.17."

---

## 7. Brownfield Integration Challenges

Working inside an existing codebase brought unique constraints:

**Ghostfolio API limitations:** The portfolio endpoint didn't support account-scoped filtering. We added `accounts=` filter parameters to the holdings, performance, and details endpoints — a small but necessary upstream change to enable per-account analysis.

**Data source disambiguation:** When the agent records a trade, it needs a `dataSource` (YAHOO, FINANCIAL_MODELING_PREP, COINGECKO, etc.). The symbol lookup API returns multiple matches — PYPL might match both Yahoo (stock) and CoinGecko (crypto token). The `_resolve_data_source` function was rewritten to prefer equity sources for stock-like tickers (2-5 uppercase letters), preventing stocks from being recorded with crypto pricing.

**Yahoo Finance blocked on cloud IPs:** Railway-hosted instances can't reach Yahoo Finance. The entire market data pipeline was adapted to support Financial Modeling Prep as an alternative data source, with env-var configuration for the API key and data source list.

**Demo login flow:** Instructors grading the project needed to see the agent's portfolio immediately. The Prisma seed was modified to point the demo login properties at the admin user (who owns the agent's portfolio), so clicking "Try Demo" shows real data instead of an empty account.

---

## 8. Infrastructure Decisions

**LangGraph over LangChain/CrewAI/AutoGen:** Explicit state management (typed state dict, no hidden context), conditional edges (verify → retry loop), and native LangSmith observability. The graph structure made the latency overhaul possible — removing nodes was a graph wiring change, not a rewrite.

**Deterministic verification over LLM-based:** Every number in the response is cross-referenced against tool results (0.5% tolerance). Guarantee language is blocked by regex. Tax estimates are sanity-checked against IRS brackets. Compliance consistency is verified against tool output. All in code — no LLM call, no hallucination risk, sub-millisecond.

**Mocked evals by default:** Ghostfolio client, market data, and sector lookups are all mocked with pinned values (AAPL $187.50, TSLA $248.00, etc.). This makes evals fast (~30-60s per layer), repeatable, and independent of external services. Live evals against Railway are a separate mode (`EVAL_USE_MOCKS=0`).

**Redis + Postgres session persistence:** Hot storage in Redis (24hr TTL) for active conversations, cold storage in Postgres (AsyncPostgresSaver) for long-term persistence. Sessions survive container restarts on Railway.

---

## 9. Current State (March 2026)

### Architecture
5-node standard ReAct pipeline. 1-2 LLM calls per request (Claude Haiku default). 13+ tools. Deterministic verification with 7 check types. Deployed on Railway (Ghostfolio app + trading agent + Postgres + Redis).

### Performance
| Metric | Target | Actual |
|--------|--------|--------|
| Single-tool latency | <5s | 2-4s avg |
| Multi-step latency | <15s | 3-8s |
| Tool success rate | >95% | 100% |
| Eval pass rate | >80% | 96.8% (golden), 100% (scenarios) |
| Hallucination rate | <5% | 4.7% |

### What's Done
- All 9 MVP requirements met
- 13+ tools across 3 capability levels
- 111 eval cases (34 golden, 47 scenarios, 30 dataset)
- 7 verification checks (fact-check, hallucination, confidence, domain constraints, tax sanity, compliance consistency, authoritative consistency)
- Full observability (LangSmith traces, per-node latency, token usage, error tracking, user feedback)
- Persistent sessions (Redis + Postgres)
- Human-in-the-loop escalation (low-confidence responses flagged, review endpoints)
- Output validation (Pydantic v2 schema)
- In-app Trading Assistant UI in the Ghostfolio Angular frontend

### What's Open
- Demo video, Pre-Search Document, AI Cost Analysis, social post (submission deliverables)
- `finagent-evals` PyPI publish and public repo
- Dataset eval layer validation run post-tool-consolidation
- Integration smoke test against live Railway

---

## 10. Lessons

1. **Fewer LLM calls beats faster LLM calls.** The 6x latency improvement came from eliminating nodes, not from caching or streaming. Each LLM call adds 3-4s minimum; removing two calls removed 6-8s.

2. **Eval cases expose real bugs.** The 26.1% low point wasn't a testing failure — it was the test suite doing its job, surfacing a sectors crash that would have hit production. Adding cases before fixing bugs is the right order.

3. **Deterministic verification scales better than LLM-based.** Every check in the verification layer is code: regex, number matching, threshold comparison. It runs in <1ms, never hallucinates, and can be unit-tested independently.

4. **Brownfield is harder than greenfield.** Half the engineering time went into understanding Ghostfolio's API, adding missing filter parameters, handling data source disambiguation, and adapting to deployment constraints (Yahoo blocked on Railway). The AI agent code was the easy part.

5. **Align tests with system behavior, not aspirations.** Phase 2 eval cases failing against a Phase 1 agent aren't bugs — they're scope mismatches. Test what the system does today; track what it should do tomorrow separately.

---

_Built for AgentForge Week 2 · Ghostfolio Portfolio Intelligence Agent · February–March 2026_
