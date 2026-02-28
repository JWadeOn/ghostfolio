# Ghostfolio Trading Intelligence Agent — Project Plan

_Where We Are, Where We Are Going, How We Get There_
_AgentForge Week 2 · Deadline: Sunday 10:59 PM CT_

| Focus                  | Architecture                  | Eval / Quality                     | Deployment     |
| ---------------------- | ----------------------------- | ---------------------------------- | -------------- |
| Portfolio intelligence | Standard ReAct, 1–2 LLM calls | 25 golden + scenarios + full suite | Railway ✓ Live |

---

## 1. Vision: Where We Are Going

The Ghostfolio Trading Intelligence Agent is a **portfolio intelligence assistant** that turns a passive portfolio tracker into an active AI-powered decision-support system. This is a **brownfield integration** — extending an existing open-source wealth management platform with conversational AI.

### 1.1 The Problem

Long-term investors and active traders face fragmented tools. Portfolio data lives in one place, market data in another, risk rules in a spreadsheet, tax implications in a separate calculator. Making a sound investment decision requires manually pulling all of this together.

Ghostfolio solves the portfolio tracking problem well. It is a rearview mirror. The agent turns it into a windshield.

### 1.2 Primary User: Long-Term Investor (Phase 1)

> **Phase 1 scope is deliberately focused on the long-term investor. Active trader features (technical analysis, strategy scanning, regime detection) are Phase 2 extensions.**

The long-term investor asks conversational, portfolio-level questions:

- Am I too concentrated anywhere?
- How have my investments performed this year?
- Should I rebalance?
- What would my tax bill look like if I sold everything?
- Does this trade violate wash sale rules?
- Should I buy more AAPL given my current portfolio?

### 1.3 The Six Core Use Cases (Phase 1)

| #   | Use Case                   | Core Question                               | Tools                                                                   |
| --- | -------------------------- | ------------------------------------------- | ----------------------------------------------------------------------- |
| 1   | **Portfolio Health**       | How is my portfolio and am I within limits? | `get_portfolio_snapshot` + `portfolio_guardrails_check`                 |
| 2   | **Trade Evaluation**       | Should I buy or sell this position?         | `trade_guardrails_check` + `get_market_data` + `get_portfolio_snapshot` |
| 3   | **Performance Review**     | How have my investments performed?          | `get_trade_history` + `transaction_categorize`                          |
| 4   | **Tax Implications**       | What are the tax consequences?              | `tax_estimate` + `compliance_check` + `get_trade_history`               |
| 5   | **Opportunity Assessment** | Is this a good addition to my portfolio?    | `get_market_data` + `portfolio_guardrails_check` + `compliance_check`   |
| 6   | **Compliance Check**       | Does this trade follow the rules?           | `compliance_check` + `get_portfolio_snapshot`                           |

### 1.4 Phase 2: Active Retail Trader (Post-Sunday)

Once Phase 1 is stable, the agent extends to active trading use cases:

- Technical analysis — RSI, MACD, Bollinger Bands, momentum signals
- Strategy scanning — VCP, breakout, mean reversion setups
- Market regime detection — 5-dimension market classification
- Chart validation — support/resistance level analysis
- Intraday signals and real-time data requirements

---

## 2. Current State: Where We Are

### 2.1 Architecture

Two services deployed on Railway, integrated with the forked Ghostfolio repository:

| Service            | Technology                           | Responsibility                                                |
| ------------------ | ------------------------------------ | ------------------------------------------------------------- |
| **ghostfolio-app** | NestJS + Angular, Port 3333          | Portfolio data, order history, UI, Trading Assistant frontend |
| **trading-agent**  | Python FastAPI, LangGraph, Port 8000 | AI pipeline, tool execution, verification, session management |
| **PostgreSQL**     | Railway managed                      | Portfolio data, orders, activities, session cold storage      |
| **Redis**          | Railway managed                      | Cache layer, session hot storage (24hr TTL)                   |

### 2.2 The Agent Pipeline

Every natural language query flows through a **standard ReAct** LangGraph pipeline (no separate classify-intent or synthesize nodes). **1–2 LLM calls** per request.

| #   | Node              | What It Does                                                                 | Type | LLM?  |
| --- | ----------------- | ---------------------------------------------------------------------------- | ---- | ----- |
| 01  | **Check Context** | Cache freshness; preloads regime/portfolio when within TTL (30m / 5m)        | Prep | No    |
| 02  | **ReAct Agent**   | LLM reasons and acts: chooses tools or returns final answer in one step      | Core | ✓ Yes |
| 03  | **Execute Tools** | Deterministic tool execution (parallel where possible); writes cache back    | Core | No    |
| 04  | **Verify**        | Fact-check, confidence, guardrails; intent inferred from `tools_called`      | Gate | No    |
| 05  | **Format Output** | Structured JSON with citations, warnings, confidence, intent (code-inferred) | Exit | No    |

**Flow:** `check_context` → `react_agent` → (if tool_calls) → `execute_tools` → `react_agent` (with results) → … → when agent returns final text → `verify` → `format_output` → END.

> **Key design:** Claude is called **1–2 times** per request (react only). Intent is **inferred from tools_called** after the run (code-only mapping in formatter/verification). No separate intent-classification or synthesis LLM. See `docs/ARCHITECTURE_POST_LATENCY_OVERHAUL.md` for detailed flow and state shapes.

### 2.3 Tool Registry — 13+ Tools Across 3 Levels

(Unchanged structure; includes `add_to_watchlist` and decomposed guardrails. See README Tools table for full list.)

#### Level 1: Deterministic (Ghostfolio API wrappers)

| Tool                     | Description                                   | Source         |
| ------------------------ | --------------------------------------------- | -------------- |
| `get_portfolio_snapshot` | Holdings, cash, allocation, performance       | Ghostfolio API |
| `get_trade_history`      | Order history, P&L, win rate, hold time       | Ghostfolio API |
| `lookup_symbol`          | Ticker resolution from company name           | Ghostfolio API |
| `create_activity`        | Record a trade in Ghostfolio                  | Ghostfolio API |
| `portfolio_analysis`     | Per-account holdings, allocation, performance | Ghostfolio API |

#### Level 2: Aggregation (combines sources + rules)

| Tool                         | Description                                                                | Source                      |
| ---------------------------- | -------------------------------------------------------------------------- | --------------------------- |
| `portfolio_guardrails_check` | Portfolio health: concentration, cash buffer, diversification rules        | Ghostfolio + Rules Engine   |
| `trade_guardrails_check`     | Trade validation: position size, cash, sector concentration, stop loss     | Ghostfolio + Rules Engine   |
| `transaction_categorize`     | Categorize orders, detect patterns: DCA, recurring dividends, fee clusters | Ghostfolio + Pattern Engine |
| `get_market_data`            | OHLCV + 20 technical indicators for any symbol                             | yfinance                    |

#### Level 3: Net New (did not exist in Ghostfolio)

| Tool               | Description                                                                        | Source                     |
| ------------------ | ---------------------------------------------------------------------------------- | -------------------------- |
| `tax_estimate`     | US federal tax estimation with 2025 brackets, filing status, per-bracket breakdown | Pure Calculation           |
| `compliance_check` | Regulatory compliance: wash_sale (IRC §1091), capital_gains, tax_loss_harvesting   | IRS Rules + Ghostfolio     |
| `scan_strategies`  | Strategy scanning: VCP, momentum, mean reversion _(Phase 2 primary)_               | yfinance + Strategy Engine |
| `detect_regime`    | 5-dimension market classification _(Phase 2 primary)_                              | yfinance + Regime Engine   |

### 2.4 Eval Performance History

| Run / Milestone           | Cases   | Pass Rate | Notes                                              |
| ------------------------- | ------- | --------- | -------------------------------------------------- |
| Baseline (190639Z)        | 19      | 47.4%     | Initial framework                                  |
| Tool decomposition        | 19      | 42.1%     | check_risk split                                   |
| New tools added           | 23      | 26.1%     | +4 cases; sectors crash exposed                    |
| P0–P3 fixes (231954Z)     | 23      | 65.2%     | Bug fixes, verification relaxed, prompts improved  |
| **Latency overhaul**      | —       | —         | Standard ReAct (1–2 LLM calls), code-only intent   |
| **Golden set (25 cases)** | 25      | ~76%+     | 11 happy path, 5 edge, 5 adversarial, 4 multi-step |
| **Target**                | **25+** | **80%+**  | Golden + full suite; aggregate metrics in reports  |

### 2.5 Brownfield Integration — What We Extended

| What Existed in Ghostfolio  | What We Added                                 | Why It Matters                  |
| --------------------------- | --------------------------------------------- | ------------------------------- |
| Portfolio holdings endpoint | `accounts=` filter parameter                  | Enables per-account analysis    |
| Performance endpoint        | `accounts=` filter on v2 path                 | Account-scoped performance      |
| Portfolio details endpoint  | `accounts=` filter parameter                  | Consistent account filtering    |
| Account list endpoint       | `get_account(id)` for single fetch            | Compliance and analysis context |
| Angular frontend            | Trading Assistant UI component                | Natural language chat interface |
| No AI layer                 | Full Python FastAPI + LangGraph agent service | The entire agent stack          |
| No compliance tooling       | Wash sale, capital gains, TLH rules           | IRS regulatory compliance       |
| No tax tooling              | US federal bracket calculation                | Tax estimation capability       |

---

## 3. PRD Requirements Status

### 3.1 MVP Requirements (Hard Gate)

| Requirement                                            | Status  |
| ------------------------------------------------------ | ------- |
| Agent responds to natural language queries             | ✅ Done |
| At least 3 functional tools (have 13)                  | ✅ Done |
| Tool calls execute and return structured results       | ✅ Done |
| Agent synthesizes tool results into coherent responses | ✅ Done |
| Conversation history maintained across turns           | ✅ Done |
| Basic error handling — graceful failure, no crashes    | ✅ Done |
| At least one domain-specific verification check        | ✅ Done |
| 5+ test cases with expected outcomes (have 23)         | ✅ Done |
| Deployed and publicly accessible                       | ✅ Done |

### 3.2 Core Agent Architecture

| Component                      | Implementation                                                               | Status  |
| ------------------------------ | ---------------------------------------------------------------------------- | ------- |
| Reasoning Engine               | Claude (default Haiku), ReAct with bind_tools; 1–2 LLM calls per request     | ✅ Done |
| Tool Registry                  | 13+ tools with schemas, descriptions, execution logic                        | ✅ Done |
| Memory System (hot)            | LangGraph checkpointer — conversation history within session                 | ✅ Done |
| **Memory System (persistent)** | **Redis 24hr TTL + Postgres cold storage**                                   | 🔴 Todo |
| Orchestrator                   | Standard ReAct loop: react_agent ↔ execute_tools → verify → format_output    | ✅ Done |
| Verification Layer             | `verification.py` — fact-check, confidence, intent from tools_called         | ✅ Done |
| Output Formatter               | Structured JSON: summary, confidence, intent (inferred), citations, warnings | ✅ Done |

### 3.3 Required Tools — Finance Track (PRD Minimum 5)

| PRD Tool                                       | Our Implementation                                 | Status  |
| ---------------------------------------------- | -------------------------------------------------- | ------- |
| `portfolio_analysis(account_id)`               | Per-account holdings, allocation, performance      | ✅ Done |
| `transaction_categorize(transactions[])`       | Categories + DCA/dividend/spike patterns           | ✅ Done |
| `tax_estimate(income, deductions)`             | 2025 US federal brackets, filing status, breakdown | ✅ Done |
| `compliance_check(transaction, regulations[])` | wash_sale, capital_gains, tax_loss_harvesting      | ✅ Done |
| `market_data(symbols[], metrics[])`            | OHLCV + 20 indicators via yfinance                 | ✅ Done |

### 3.4 Evaluation Framework

| Requirement                            | Status         | Notes                                                                    |
| -------------------------------------- | -------------- | ------------------------------------------------------------------------ |
| Eval runner with per-case scoring      | ✅ Done        | `run_evals.py`; intent from `infer_intent_from_tools`                    |
| Per-case JSON storage with timestamps  | ✅ Done        | `reports/eval-results-{timestamp}.json`                                  |
| Regression detection                   | ✅ Done        | Flags >5% drop vs previous run                                           |
| Aggregate metrics in reports           | ✅ Done        | tool_success_rate_pct, hallucination_rate_pct, verification_accuracy_pct |
| Golden set (25 cases)                  | ✅ Done        | `golden_cases.py`; run via `run_golden.py`                               |
| Labeled scenarios                      | ✅ Done        | `scenarios.py` + `run_scenarios.py`                                      |
| Mock layer for deterministic testing   | ✅ Done        | `tests/mocks/` — Ghostfolio + yfinance                                   |
| Full suite (69+ cases)                 | ✅ Done        | `dataset.py`; Phase 1 + Phase 2                                          |
| ≥80% pass rate (golden / suite)        | 🟡 In Progress | Golden ~76%; target 80%+                                                 |
| LangSmith Datasets + Experiments       | 🟡 Optional    | Experiment URL when LANGCHAIN_API_KEY set                                |
| Integration smoke test vs live Railway | 🔴 Todo        | Run after stable mock evals                                              |

### 3.5 Observability

| Requirement                                  | Status         | Notes                           |
| -------------------------------------------- | -------------- | ------------------------------- |
| LangSmith tracing — full pipeline traces     | ✅ Done        | Every run traced                |
| Latency tracking — per node                  | ✅ Done        | Visible in LangSmith            |
| Error tracking — stack traces, context       | ✅ Done        | Captured in traces and JSON     |
| Token usage — input/output per request       | ✅ Done        | Tracked via LangSmith           |
| LangSmith Datasets and Experiments UI        | 🟡 In Progress | Wiring tonight                  |
| **User feedback mechanism (thumbs up/down)** | 🔴 Todo        | `POST /api/feedback` — Saturday |

### 3.6 Verification Systems (Need 3+)

| Check Type              | Implementation                                                      | Status  |
| ----------------------- | ------------------------------------------------------------------- | ------- |
| Fact Checking           | Numbers cross-referenced against tool results (5% tolerance)        | ✅ Done |
| Hallucination Detection | Unsourced numbers flagged, re-synthesis triggered                   | ✅ Done |
| Confidence Scoring      | 0-100 from tool success, regime, guardrails                         | ✅ Done |
| Domain Constraints      | Guarantee language blocked; stop loss required on trade suggestions | ✅ Done |
| Tax Estimate Sanity     | Non-negative liability, plausible effective rate (0-60%)            | ✅ Done |
| Compliance Consistency  | Synthesis "no violations" vs tool violations flagged                | ✅ Done |
| Output Validation       | Schema validation, completeness checks                              | 🔴 Todo |
| Human-in-the-Loop       | Escalation triggers for high-risk decisions                         | 🔴 Todo |

### 3.7 Performance Targets

| Metric                | PRD Target  | Current (post–latency overhaul)     | Status         |
| --------------------- | ----------- | ----------------------------------- | -------------- |
| Single-tool latency   | <5 seconds  | 2–4s (Haiku + ReAct, 1–2 LLM calls) | ✅ Met         |
| Multi-step latency    | <15 seconds | 3–8s (parallel tools, 2 LLM calls)  | ✅ Met         |
| Tool success rate     | >95%        | Reported in eval aggregate          | ✅ Measured    |
| Eval pass rate        | >80%        | Golden ~76%; full suite variable    | 🟡 In Progress |
| Hallucination rate    | <5%         | Reported in eval aggregate          | ✅ Measured    |
| Verification accuracy | >90%        | Reported in eval aggregate          | ✅ Measured    |

**Note:** Latency overhaul (standard ReAct, no classify/synthesize nodes, default Haiku) brought single-tool and multi-step within targets. Per-model token cost and node latencies are tracked in observability.

### 3.8 Submission Deliverables

| Deliverable                                    | Status  | Due         |
| ---------------------------------------------- | ------- | ----------- |
| GitHub repo with setup guide and deployed link | ✅ Done | Complete    |
| Demo video (3-5 min)                           | 🔴 Todo | Friday PM   |
| Agent Architecture Document (1-2 pages)        | 🔴 Todo | Friday PM   |
| Pre-Search Document (Phase 1-3 checklist)      | 🔴 Todo | Saturday AM |
| AI Cost Analysis (dev + projections)           | 🔴 Todo | Saturday AM |
| Eval dataset (50+ cases with results)          | 🔴 Todo | Friday AM   |
| Open source contribution                       | 🔴 Todo | Saturday AM |
| Deployed application — publicly accessible     | ✅ Done | Complete    |
| Social post tagging @GauntletAI                | 🔴 Todo | Saturday AM |

---

## 4. Gameplan: How We Get There

> **Target: All deliverables complete and submitted by Saturday noon. Sunday is pure buffer.**

### Thursday Night — Stabilize

| Time   | Task                                                                                | Owner  |
| ------ | ----------------------------------------------------------------------------------- | ------ |
| 30 min | Run mock evals 3 consecutive times — all must hit ≥80%                              | You    |
| 15 min | Push latest code to Railway — verify both services redeploy green                   | You    |
| 30 min | Run integration smoke test: `EVAL_USE_MOCKS=0 python3 tests/eval/run_evals.py`      | You    |
| 30 min | Wire LangSmith Datasets + Experiments (evaluate() API, replay pre-computed results) | Cursor |
| 1 hour | Implement Redis + Postgres session management (AsyncRedisSaver)                     | Cursor |

### Friday — Build Deliverables

| Time      | Task                                                              | Owner  |
| --------- | ----------------------------------------------------------------- | ------ |
| 2 hours   | Expand eval suite to 50+ cases (Phase 1 long-term investor focus) | Cursor |
| 30 min    | Run full 50-case suite — confirm ≥80% pass rate                   | You    |
| 30 min    | Update `reports/HISTORY.md` with all run results                  | You    |
| 1 hour    | Record demo video — script is ready, one clean take               | You    |
| 1.5 hours | Write Agent Architecture Document (1-2 pages)                     | You    |

### Saturday — Polish and Submit

| Time     | Task                                                                  | Owner   |
| -------- | --------------------------------------------------------------------- | ------- |
| 1 hour   | AI Cost Analysis — pull LangSmith token data, build projections table | You     |
| 45 min   | Pre-Search Document — retrospective fill of Phase 1-3 checklist       | You     |
| 30 min   | Open source contribution — publish eval dataset to public GitHub      | You     |
| 30 min   | User feedback mechanism — `POST /api/feedback` endpoint               | Cursor  |
| 15 min   | Social post — X or LinkedIn tagging @GauntletAI                       | You     |
| 1 hour   | Full end-to-end submission review — check every deliverable link      | You     |
| **NOON** | **SUBMIT**                                                            | **You** |

### Sunday — Buffer Only

Fix anything broken. Submit before noon if not already done.

---

## 5. Eval Suite Expansion Plan (50+ Cases)

> **All new cases scoped to Phase 1: Long-term investor only.**
> **Excluded from this expansion:** `scan_strategies`, `detect_regime`, `chart_validation`, `signal_archaeology`, `opportunity_scan`, `regime_check`

| Category               | Easy   | Medium | Hard   | Total  | Example Queries                                                                 |
| ---------------------- | ------ | ------ | ------ | ------ | ------------------------------------------------------------------------------- |
| Portfolio health       | 3      | 3      | 2      | 8      | "Am I too concentrated?", "Portfolio health check", "Am I diversified?"         |
| Trade evaluation       | 3      | 3      | 2      | 8      | "Should I buy AAPL?", "Can I afford to add TSLA?", "Should I sell GOOG?"        |
| Performance review     | 3      | 2      | 2      | 7      | "How have I done this year?", "Best performers?", "What is my win rate?"        |
| Tax implications       | 2      | 2      | 2      | 6      | "Tax bill if I sell everything?", "Short vs long term gains on TSLA?"           |
| Compliance             | 2      | 2      | 2      | 6      | "Does this trade violate wash sale?", "Capital gains on GOOG sale?"             |
| Opportunity assessment | 2      | 2      | 2      | 6      | "Is NVDA a good addition?", "Does MSFT fit my portfolio?"                       |
| Edge cases             | 2      | 2      | 1      | 5      | "Am I on track?", "How am I doing?", maximally ambiguous queries                |
| Adversarial            | 0      | 2      | 3      | 5      | Guarantee-seeking, out-of-scope, prompt injection attempts                      |
| Multi-step reasoning   | 1      | 2      | 2      | 5      | "Should I buy more of my worst performer?", "Can I afford any of these setups?" |
| **TOTAL**              | **18** | **20** | **18** | **56** |                                                                                 |

---

## 6. Open Items and Known Gaps

### Critical — Must Fix Before Submission

| #   | Issue                                   | Fix                                              | Owner        |
| --- | --------------------------------------- | ------------------------------------------------ | ------------ |
| 1   | Golden pass rate not yet stable at 80%+ | Run repeatedly; fix tool-selection / content     | You + Cursor |
| 2   | Integration smoke test not run          | Run against live Railway after stable mock evals | You          |

### Addressed (Latency Overhaul)

| Item                                    | Status                                                                 |
| --------------------------------------- | ---------------------------------------------------------------------- |
| Standard ReAct pipeline (1–2 LLM calls) | ✅ Done — no classify_intent or synthesize nodes                       |
| Code-only intent inference              | ✅ Done — `infer_intent_from_tools()` in formatter/verification        |
| Node latency tracking                   | ✅ Fixed — manual timing in react_agent and tools                      |
| Aggregate eval metrics                  | ✅ Done — tool_success_rate, hallucination_rate, verification_accuracy |
| Configurable model (AGENT_MODEL)        | ✅ Done — default Haiku                                                |
| Golden set 25 cases + labeled scenarios | ✅ Done                                                                |

### Known Gaps — Documented, Not Blocking

| Gap                                 | Impact                                        | Plan                              |
| ----------------------------------- | --------------------------------------------- | --------------------------------- |
| Sell evaluation edge cases          | Occasional contradictory sell recommendations | Phase 2 fix                       |
| Regime detection unstable           | Excluded from Phase 1 evals                   | Phase 2 stabilization             |
| Multi-user auth (single demo token) | All users share one portfolio                 | Phase 2 per-request token passing |
| Output validation schema checks     | Verification requirement partially met        | Phase 2                           |
| Human-in-the-loop escalation        | Verification requirement partially met        | Phase 2                           |

### Phase 2 Backlog (Post-Sunday)

- ReAct prompt refinement — more consistent tool selection (e.g. compliance_check, tax_estimate on multi-area queries)
- Structured outputs with Pydantic validation at LLM boundary
- Streaming responses — show agent working in real time
- Active trader use cases — technical analysis, strategy scanning, regime-aware responses
- Confidence-weighted synthesis language
- Multi-turn context building a trade thesis across turns
- Regime-aware responses — filter answers through current market context

---

## 7. AI Cost Analysis

_Update with actual LangSmith token data when available._

### Assumptions (post–latency overhaul)

- ~5 queries/user/day
- ~2,000 input + ~800 output tokens per query (varies by tooled vs 0-tool)
- **1–2 LLM calls per request** (ReAct only; no separate intent or synthesis)
- Default model: **Claude Haiku** (e.g. `claude-haiku-4-5`) — lower cost than Sonnet; override with `AGENT_MODEL=claude-sonnet-4-20250514` for maximum quality
- Per-model pricing in `observability.py` (Haiku vs Sonnet)

### Production Cost Projections (illustrative)

| Cost Component    | 100 Users | 1,000 Users | 10,000 Users |
| ----------------- | --------- | ----------- | ------------ |
| Queries / month   | 15,000    | 150,000     | 1,500,000    |
| LLM calls/request | 1–2       | 1–2         | 1–2          |
| Claude (Haiku)    | ~$5–15    | ~$50–150    | ~$500–1.5k   |
| Railway infra     | $5        | $20         | $100         |

Cost stays low due to 1–2 LLM calls and deterministic tool/verification path. Fill in actual token counts from LangSmith when available.

---

## 8. Master Submission Checklist

Use this as the final review before submitting Saturday noon.

### MVP Requirements

- [x] All 9 MVP requirements passing
- [x] Deployed and publicly accessible on Railway

### Eval Framework

- [ ] Golden set stable at ≥80% (25 cases)
- [ ] Full suite / labeled scenarios run and pass rate documented
- [ ] Integration smoke test vs live Railway passing
- [ ] LangSmith experiments optional when API key set

### Session Management

- [ ] Redis hot storage (24hr TTL)
- [ ] Postgres cold storage (persistent)
- [ ] Session survives container restart

### Submission Deliverables

- [x] GitHub repo with setup guide and deployed link
- [ ] Demo video (3-5 min)
- [ ] Agent Architecture Document (1-2 pages)
- [ ] Pre-Search Document (Phase 1-3 checklist)
- [ ] AI Cost Analysis (dev + projections)
- [ ] Eval dataset — 50+ cases with results
- [ ] Open source contribution — published eval dataset
- [ ] Social post tagging @GauntletAI
- [ ] Final submission before Saturday noon

---

_Ship and know. Not perfect and late._
_AgentForge Week 2 · Ghostfolio Trading Intelligence Agent · February 2026_
