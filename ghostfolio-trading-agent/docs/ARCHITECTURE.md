# Ghostfolio Trading Intelligence Agent — Architecture

> AI-powered decision support for long-term investors, built on Ghostfolio

**Deployment:** [Railway](https://ghostfolio-app-production-9ea6.up.railway.app/en/trading-agent)
**Repository:** [GitHub](https://github.com/your-repo)
**Stack:** LangGraph · Claude Sonnet · FastAPI · Ghostfolio · Railway

---

## 1. Domain and Use Cases

### The Problem

Long-term investors face fragmented tooling. Portfolio data lives in one
place, market data in another, risk rules in a spreadsheet, tax implications
in a separate calculator. Ghostfolio solves the portfolio tracking problem
well — it is a rearview mirror. This agent turns it into a windshield.

### Primary User: Long-Term Investor

The agent is scoped to Phase 1: the long-term investor who asks
conversational, portfolio-level questions:

- "Am I too concentrated anywhere?"
- "How have my investments performed this year?"
- "Should I rebalance?"
- "What would my tax bill look like if I sold everything?"
- "Does this trade violate wash sale rules?"

### The Six Core Use Cases

| #   | Use Case               | Core Question                            |
| --- | ---------------------- | ---------------------------------------- |
| 1   | Portfolio Health       | Am I within my guardrails?               |
| 2   | Trade Evaluation       | Should I buy or sell this position?      |
| 3   | Performance Review     | How have my investments performed?       |
| 4   | Tax Implications       | What are the tax consequences?           |
| 5   | Opportunity Assessment | Is this a good addition to my portfolio? |
| 6   | Compliance Check       | Does this trade follow the rules?        |

### Brownfield Integration

This is a brownfield project — an AI layer added to an existing
open-source platform. What existed in Ghostfolio vs what we added:

| Existed                     | Added                                 |
| --------------------------- | ------------------------------------- |
| Portfolio holdings endpoint | `accounts=` filter parameter          |
| Performance endpoint (v2)   | Account-scoped filtering              |
| Angular frontend            | Trading Assistant UI component        |
| No AI layer                 | Full Python FastAPI + LangGraph agent |
| No compliance tooling       | Wash sale, capital gains, TLH rules   |
| No tax tooling              | US federal bracket calculation        |

---

## 2. Agent Architecture

### Framework: LangGraph

LangGraph was chosen over LangChain, CrewAI, and AutoGen for three reasons:

1. **Explicit state management** — every node receives and returns a typed
   state dict. No hidden context, no magic.
2. **Conditional edges** — the verify → re-synthesize retry loop requires
   a graph structure, not a linear chain.
3. **Native observability** — LangSmith integration provides full trace
   visibility per node out of the box.

### The 7-Node Pipeline

Every natural language query flows through this pipeline:

```
[classify_intent] → [check_context] → [react_agent] ⇄ [execute_tools]
                                           ↓
                                      [synthesize]
                                           ↓
                                      [verify]
                                           ↓
                                    [format_output]
```

| Node              | Type  | LLM | Responsibility                                      |
| ----------------- | ----- | --- | --------------------------------------------------- |
| `classify_intent` | Entry | ✓   | Understand query, extract symbol/amount/side        |
| `check_context`   | Prep  | —   | Cache freshness, preload portfolio/regime           |
| `react_agent`     | Core  | ✓   | Reason between tool calls, decide next tool         |
| `execute_tools`   | Core  | —   | Deterministic tool execution                        |
| `synthesize`      | Core  | ✓   | Produce final answer from tool results (LLM call 2) |
| `verify`          | Gate  | —   | Fact-check, confidence scoring, guardrails          |
| `format_output`   | Exit  | —   | Structured JSON response                            |

**Key design decision:** Claude is called exactly twice per request —
intent classification and synthesis only. All tool execution, math, and
verification is deterministic Python. This makes the system fast, auditable,
and cost-efficient.

### ReAct Orchestration

The agent uses a ReAct (Reason + Act) loop between `react_agent` and
`execute_tools`. The LLM sees tool results after each call and decides
whether to call another tool or synthesize a response.

```
User query
    → classify_intent (LLM call 1)
    → check_context (cache read)
    → react_agent: "I need portfolio data first" (LLM reasoning)
    → execute_tools: get_portfolio_snapshot
    → react_agent: "Now I need to check the trade" (LLM reasoning)
    → execute_tools: trade_guardrails_check
    → react_agent: "I have enough to answer" → synthesize (LLM call 2)
    → verify (deterministic)
    → format_output (deterministic)
```

---

## 3. Tool Registry

13 tools organized across three levels of capability:

### Level 1 — Deterministic (Ghostfolio API wrappers)

Actions that already existed in Ghostfolio, exposed as agent tools:

| Tool                     | Returns                                       |
| ------------------------ | --------------------------------------------- |
| `get_portfolio_snapshot` | Holdings, cash, allocation, performance       |
| `get_trade_history`      | Order history, P&L, win rate, hold time       |
| `lookup_symbol`          | Ticker resolution from company name           |
| `create_activity`        | Record a trade in Ghostfolio                  |
| `portfolio_analysis`     | Per-account holdings, allocation, performance |

### Level 2 — Aggregation (combines sources + rules)

Multiple actions combined into new capabilities:

| Tool                         | Combines                                 |
| ---------------------------- | ---------------------------------------- |
| `portfolio_guardrails_check` | Ghostfolio holdings + 5 risk rules       |
| `trade_guardrails_check`     | Ghostfolio + market data + rules engine  |
| `transaction_categorize`     | Ghostfolio orders + pattern detection    |
| `get_market_data`            | yfinance OHLCV + 20 technical indicators |

### Level 3 — Net New (did not exist in Ghostfolio)

Capabilities with no equivalent in the original platform:

| Tool               | Description                                               |
| ------------------ | --------------------------------------------------------- |
| `tax_estimate`     | 2025 US federal brackets, filing status, breakdown        |
| `compliance_check` | Wash sale (IRC §1091), capital gains, tax loss harvesting |
| `scan_strategies`  | VCP, momentum, mean reversion _(Phase 2)_                 |
| `detect_regime`    | 5-dimension market classification _(Phase 2)_             |

---

## 4. Verification Strategy

The verification layer runs after synthesis and before formatting.
It performs domain-specific checks in deterministic Python — no LLM.

### What Gets Verified

**Fact checking:** Every number in the synthesis text must appear in
tool results (within 0.5% relative tolerance). If a number can't be sourced,
it's flagged as a potential hallucination and synthesis retries.

**Hallucination detection:** Unsourced claims reduce the confidence
score and trigger re-synthesis (up to 1 retry: 2 total synthesis runs). After max retries,
the response is returned with a warning.

**Confidence scoring:** 0-100 score computed from tool success rate,
verification pass rate, and domain-specific signals. Surfaced in every
response.

**Domain constraints:**

- Trade suggestions must include a stop loss level
- Guarantee language ("guaranteed", "promise", "certain") is blocked
- Tax estimates flagged as informational only, not professional advice
- Compliance violations must be explicitly stated, not summarized away

**Tax estimate sanity:** `estimated_liability` must be non-negative.
`effective_rate` must be between 0-60%.

**Compliance consistency:** If synthesis says "no violations" but
`compliance_check` returned violations, verification flags the
inconsistency and forces re-synthesis.

### Verification Flow

```
synthesize
    → extract numbers from text
    → cross-reference against tool_results
    → check domain constraints
    → compute confidence score
    → pass: format_output
    → fail: re-synthesize (up to 1 retry)
    → max retries: format_output with warnings
```

---

## 5. Eval Results

### Framework

The eval framework uses 6-dimension scoring per case (agent runner in `tests/eval/run_evals.py`):

| Dimension    | Weight | What It Measures                                           |
| ------------ | ------ | ---------------------------------------------------------- |
| Intent       | 20%    | Did the agent understand the query correctly?              |
| Tools        | 25%    | Did it call the right tools?                               |
| Content      | 15%    | Does the response contain required information?            |
| Safety       | 15%    | Does it avoid forbidden language?                          |
| Confidence   | 15%    | Is the agent confidence above the minimum threshold?       |
| Verification | 10%    | Did verification pass (no fact-check or guardrail issues)? |

A case passes if the weighted overall score ≥ 0.8.

### Performance History

| Run                       | Cases | Pass Rate | Key Change                                                    |
| ------------------------- | ----- | --------- | ------------------------------------------------------------- |
| Baseline                  | 19    | 47.4%     | Initial framework                                             |
| Tool decomposition        | 19    | 42.1%     | check_risk split                                              |
| New tools added           | 23    | 26.1%     | Sectors bug exposed                                           |
| P0-P3 fixes               | 23    | 65.2%     | Bug fixed, prompts improved                                   |
| Phase 1 scoped            | 23    | 80%+      | Phase 2 cases excluded                                        |
| Phase 1 only (2026-02-27) | 18    | 77.8%     | Phase 1 filter; target 80% not met (tool selection + content) |

### Failure Analysis

The most instructive failures were system-level, not individual bugs:

**Tool ordering** — The agent called `trade_guardrails_check` without
first fetching portfolio context. Fix: explicit ordering rules in
`REACT_SYSTEM_PROMPT`. Recovered 3 cases.

**Verification over-strictness** — Derived numbers (percentages,
computed totals) failed fact-checking even when correct. Fix:
whitelist derived values and user-provided numbers. Recovered 4 cases.

**Phase mismatch** — Phase 1 prompt told agent not to use regime tools;
Phase 2 evals expected them. Fix: `--phase` flag separates eval scopes.
Recovered 3 cases.

---

## 6. Observability

### LangSmith Integration

Every request is fully traced via LangSmith:

- **Traces:** Complete pipeline trace per request with per-node latency
- **Token usage:** Input/output tokens tracked per LLM call
- **Eval experiments:** Each eval run creates a named experiment in
  LangSmith Datasets & Experiments with score trends across runs
- **Regression detection:** Pass rate vs previous run is tracked in JSON reports
  (e.g. `reports/eval-results-*.json`); alerting can be added in CI or manual review

### Session Management

Session state is kept in process memory (`_thread_states` in `app.py`): active conversations persist within the same process (e.g. across requests in a long-lived container). There is no Redis or Postgres persistence implemented; container restart clears session state.

### What We Track

| Signal                 | Tool                                             | Purpose              |
| ---------------------- | ------------------------------------------------ | -------------------- |
| Full pipeline traces   | LangSmith                                        | Debug and optimize   |
| Per-node latency       | LangSmith                                        | Identify bottlenecks |
| Token usage            | LangSmith                                        | Cost tracking        |
| Eval pass rate history | LangSmith + JSON (`reports/eval-results-*.json`) | Regression detection |
| User feedback          | POST /api/feedback                               | Quality signal       |

### Key API Endpoints

| Endpoint                  | Purpose                                                                       |
| ------------------------- | ----------------------------------------------------------------------------- |
| POST /api/chat            | Main entry: natural language query → agent response (thread_id, access_token) |
| GET /api/health           | Health check (Ghostfolio, LangSmith, Anthropic config)                        |
| POST /api/feedback        | Submit thumbs up/down and optional correction for a thread                    |
| GET /api/feedback/summary | Aggregate feedback counts                                                     |
| GET /api/regime           | Shortcut: current market regime (no full agent loop)                          |
| GET /api/scan             | Shortcut: strategy scan (no full agent loop)                                  |

---

## 7. Open Source Contributions

### 1. Eval Dataset

**Location:** `evals/` (repo root); agent runner and case definitions in `ghostfolio-trading-agent/tests/eval/`

A standalone, reusable eval framework for LangGraph financial agents.
Includes 23+ test cases (design target 50+) across multiple categories, 5–6 dimension scoring,
and a drop-in runner that works with any LangGraph agent.

### 2. Portfolio Guardrails Package

**Location:** `packages/portfolio-guardrails/`
**Install:** `pip install portfolio-guardrails`

A pip-installable package exposing `check_portfolio_guardrails` —
pure Python, zero external dependencies. Five rules: position
concentration, sector concentration, cash buffer, diversification,
position count. Works with any portfolio data source.

---

## 8. What's Next (Phase 2)

Phase 2 extends the agent to active retail traders:

- **Regime-aware responses** — every answer filtered through current
  market context (bull/bear/sideways, volatility regime)
- **Strategy scanning** — VCP, momentum, mean reversion setup detection
- **Technical analysis** — deeper indicator usage, chart validation
- **Contextual risk tools** — `portfolio_sector_risk`,
  `portfolio_market_risk`, `trade_sector_risk`, `trade_market_risk`
- **Streaming responses** — real-time agent reasoning visible to user
- **ReAct refinement** — adaptive tool selection within constrained menu

---

## 9. Key Files and State

- **State:** `agent/state.py` defines `AgentState` (messages, intent, extracted_params, regime/portfolio cache, tool_results, tools_called, react_step, synthesis, verification_result, response, token_usage, node_latencies, error_log, trace_log).
- **Graph:** `agent/graph.py` — node wiring and conditional edges.
- **Config:** `agent/config.py` — settings (Anthropic, Ghostfolio URL, LangSmith, etc.); see README for required env vars.

---

_Built for AgentForge Week 2 · February 2026_
