# Ghostfolio Trading Intelligence Agent — Project Plan

_Where We Are, Where We Are Going, How We Get There_
_AgentForge Week 2 · Deadline: Sunday 10:59 PM CT_

| Tools Built | Tests Passing | Current Pass Rate | Deployment     |
| ----------- | ------------- | ----------------- | -------------- |
| 13 Tools    | 56 Tests      | TBD → 80%+ target | Railway ✓ Live |

---

## 1. Vision: Where We Are Going

The Ghostfolio Trading Intelligence Agent transforms a passive portfolio tracker into an active AI-powered decision-support system. This is a **brownfield integration** — extending an existing open-source wealth management platform with conversational AI capabilities.

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

Every natural language query flows through a 6-node LangGraph pipeline:

| #   | Node                | What It Does                                                                   | Type  | LLM?  |
| --- | ------------------- | ------------------------------------------------------------------------------ | ----- | ----- |
| 01  | **Classify Intent** | Understands what the user is asking; extracts symbol, amount, side             | Entry | ✓ Yes |
| 02  | **Check Context**   | Cache freshness check; preloads regime/portfolio if cached                     | Prep  | No    |
| 03  | **ReAct Loop**      | LLM reasons between tool calls; decides which tool next based on prior results | Core  | ✓ Yes |
| 04  | **Execute Tools**   | Deterministic tool execution; no LLM involvement                               | Core  | No    |
| 05  | **Verify**          | Fact-checks numbers, confidence scoring, guardrail enforcement                 | Gate  | No    |
| 06  | **Format Output**   | Structured JSON with citations, warnings, confidence, tools_used               | Exit  | No    |

> **Key design:** Claude is called exactly twice per request — intent classification and synthesis only. All tool execution is deterministic Python.

### 2.3 Tool Registry — 13 Tools Across 3 Levels

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

| Run                          | Cases   | Pass Rate | Avg Score | Key Change                                        |
| ---------------------------- | ------- | --------- | --------- | ------------------------------------------------- |
| Baseline (190639Z)           | 19      | 47.4%     | 0.840     | Initial framework                                 |
| Tool decomposition (204957Z) | 19      | 42.1%     | 0.811     | check_risk split; sectors bug introduced          |
| New tools added (212851Z)    | 23      | 26.1%     | 0.777     | +4 cases; sectors crash exposed                   |
| P0-P3 fixes (231954Z)        | 23      | 65.2%     | 0.858     | Bug fixed, verification relaxed, prompts improved |
| **Target (next run)**        | **23+** | **80%+**  | **0.88+** | Tool ordering + final assertion fixes             |

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

| Component                      | Implementation                                                | Status  |
| ------------------------------ | ------------------------------------------------------------- | ------- |
| Reasoning Engine               | Claude Sonnet, structured output, ReAct chain-of-thought      | ✅ Done |
| Tool Registry                  | 13 tools with schemas, descriptions, execution logic          | ✅ Done |
| Memory System (hot)            | LangGraph checkpointer — conversation history within session  | ✅ Done |
| **Memory System (persistent)** | **Redis 24hr TTL + Postgres cold storage**                    | 🔴 Todo |
| Orchestrator                   | ReAct node with `llm.bind_tools()`, multi-step reasoning loop | ✅ Done |
| Verification Layer             | `verification.py` — fact-check, confidence, domain checks     | ✅ Done |
| Output Formatter               | Structured JSON: summary, confidence, citations, warnings     | ✅ Done |

### 3.3 Required Tools — Finance Track (PRD Minimum 5)

| PRD Tool                                       | Our Implementation                                 | Status  |
| ---------------------------------------------- | -------------------------------------------------- | ------- |
| `portfolio_analysis(account_id)`               | Per-account holdings, allocation, performance      | ✅ Done |
| `transaction_categorize(transactions[])`       | Categories + DCA/dividend/spike patterns           | ✅ Done |
| `tax_estimate(income, deductions)`             | 2025 US federal brackets, filing status, breakdown | ✅ Done |
| `compliance_check(transaction, regulations[])` | wash_sale, capital_gains, tax_loss_harvesting      | ✅ Done |
| `market_data(symbols[], metrics[])`            | OHLCV + 20 indicators via yfinance                 | ✅ Done |

### 3.4 Evaluation Framework

| Requirement                            | Status         | Notes                                   |
| -------------------------------------- | -------------- | --------------------------------------- |
| Eval runner with per-case scoring      | ✅ Done        | `run_evals.py` with 5-dimension scoring |
| Per-case JSON storage with timestamps  | ✅ Done        | `reports/eval-results-{timestamp}.json` |
| Regression detection                   | ✅ Done        | Flags >5% drop vs previous run          |
| LangSmith Datasets + Experiments       | 🟡 In Progress | Wiring tonight                          |
| Mock layer for deterministic testing   | ✅ Done        | `tests/mocks/` — Ghostfolio + yfinance  |
| **50+ test cases**                     | 🔴 Todo        | Currently at 23; expanding Friday       |
| 20+ happy path scenarios               | 🔴 Todo        | Currently ~12                           |
| 10+ edge cases                         | 🔴 Todo        | Currently 4                             |
| 10+ adversarial inputs                 | 🔴 Todo        | Currently 1                             |
| 10+ multi-step reasoning               | 🔴 Todo        | Currently 3                             |
| ≥80% pass rate confirmed stable        | 🟡 In Progress | At 65%; targeting 80%+                  |
| Integration smoke test vs live Railway | 🔴 Todo        | Run after stable mock evals             |

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

| Metric                | PRD Target  | Current                     | Status         |
| --------------------- | ----------- | --------------------------- | -------------- |
| Single-tool latency   | <5 seconds  | 3-5s (real) / 11-15s (mock) | 🟡 Partial     |
| Multi-step latency    | <15 seconds | 45-80s observed             | 🔴 Gap         |
| Tool success rate     | >95%        | Not yet measured            | 🔴 Unmeasured  |
| Eval pass rate        | >80%        | 65.2% → targeting 80%+      | 🟡 In Progress |
| Hallucination rate    | <5%         | Not yet measured            | 🔴 Unmeasured  |
| Verification accuracy | >90%        | Not yet measured            | 🔴 Unmeasured  |

> **Note:** Multi-step latency is a known gap — flagged for post-submission optimization. Single-tool latency on real data meets the target.

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

| #   | Issue                                                | Fix                                                | Owner        |
| --- | ---------------------------------------------------- | -------------------------------------------------- | ------------ |
| 1   | Mock eval pass rate not yet confirmed stable at 80%+ | Run 3 consecutive times; fix remaining assertions  | You + Cursor |
| 2   | LangSmith Datasets and Experiments not wired         | Wire tonight using evaluate() + replay approach    | Cursor       |
| 3   | Session management not persistent                    | AsyncRedisSaver (24hr) + AsyncPostgresSaver (cold) | Cursor       |
| 4   | Eval suite only at 23 cases (need 50+)               | Expand Friday morning using coverage matrix above  | Cursor       |
| 5   | Integration smoke test not run                       | Run against live Railway after stable mock evals   | You          |

### Known Gaps — Documented, Not Blocking

| Gap                                          | Impact                                        | Plan                               |
| -------------------------------------------- | --------------------------------------------- | ---------------------------------- |
| Multi-step latency 45-80s (PRD target <15s)  | Performance metric not met                    | Post-submission optimization       |
| Sell evaluation logic applies buy-side rules | Occasional contradictory sell recommendations | Phase 2 fix                        |
| Regime detection unstable                    | Excluded from Phase 1 evals                   | Phase 2 stabilization              |
| Multi-user auth (single demo token)          | All users share one portfolio                 | Phase 2 per-request token passing  |
| Output validation schema checks              | Verification requirement partially met        | Saturday if time allows            |
| Human-in-the-loop escalation                 | Verification requirement partially met        | Phase 2                            |
| Tool success rate not measured               | Performance metric unmeasured                 | Extract from LangSmith traces      |
| Hallucination rate not measured              | Performance metric unmeasured                 | Compute from verification warnings |

### Phase 2 Backlog (Post-Sunday)

- ReAct pattern refinement — smarter adaptive tool selection
- Structured outputs with Pydantic validation at every LLM boundary
- Streaming responses — show agent working in real time
- Active trader use cases — technical analysis, strategy scanning, regime-aware responses
- Confidence-weighted synthesis language
- Multi-turn context building a trade thesis across turns
- Regime-aware responses — filter every answer through current market context

---

## 7. AI Cost Analysis

_To be completed Saturday using actual LangSmith token data._

### Assumptions

- 5 queries/user/day
- ~2,000 input tokens + 800 output tokens per query
- 2 LLM calls per request (intent + synthesis)
- Claude Sonnet pricing: $3/M input tokens, $15/M output tokens

### Production Cost Projections

| Cost Component     | 100 Users  | 1,000 Users | 10,000 Users | 100,000 Users |
| ------------------ | ---------- | ----------- | ------------ | ------------- |
| Queries / month    | 15,000     | 150,000     | 1,500,000    | 15,000,000    |
| Input tokens (M)   | 0.03M      | 0.30M       | 3.0M         | 30M           |
| Output tokens (M)  | 0.012M     | 0.12M       | 1.2M         | 12M           |
| Claude input cost  | $0.09      | $0.90       | $9.00        | $90           |
| Claude output cost | $0.18      | $1.80       | $18.00       | $180          |
| Railway infra      | $5         | $20         | $100         | $500          |
| **TOTAL / MONTH**  | **~$5.30** | **~$22.70** | **~$127**    | **~$770**     |

> **Cost is extremely low** due to the 2-LLM-call architecture. All tool execution is deterministic Python — no LLM costs for market data, portfolio fetching, risk rules, or verification. Fill in actual token counts from LangSmith on Saturday.

---

## 8. Master Submission Checklist

Use this as the final review before submitting Saturday noon.

### MVP Requirements

- [x] All 9 MVP requirements passing
- [x] Deployed and publicly accessible on Railway

### Eval Framework

- [ ] Mock evals stable at ≥80% (3 consecutive runs)
- [ ] LangSmith Datasets + Experiments wired and visible
- [ ] 50+ test cases (Phase 1 scope)
- [ ] Integration smoke test vs live Railway passing
- [ ] Eval pass rate ≥80% confirmed

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
