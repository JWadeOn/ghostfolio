# Ghostfolio Trading Agent

An AI-powered **portfolio intelligence assistant** built with [LangGraph](https://github.com/langchain-ai/langgraph) and [Anthropic Claude](https://www.anthropic.com/). It integrates with [Ghostfolio](https://ghostfol.io) to help long-term investors and traders with portfolio health, performance review, risk validation, tax implications, compliance (e.g. wash sale), and market data — through a conversational REST API.

**Focus:** Portfolio intelligence first: holdings, diversification, trade evaluation, taxes, and compliance. Regime-aware analysis and opportunity scanning are supported as extensions.

## Table of Contents

- [Quick Start](#quick-start)
- [Option A: Run Ghostfolio from the monorepo (Trading Assistant in UI)](#option-a-run-ghostfolio-from-the-monorepo-trading-assistant-in-ui)
- [Use Cases](#use-cases)
- [Architecture](#architecture)
- [Strategies](#strategies)
- [Tools](#tools)
- [API Endpoints](#api-endpoints)
- [Configuration](#configuration)
- [Running Tests](#running-tests)
- [Evaluation System](#evaluation-system)

---

## Quick Start

### Prerequisites

- Docker and Docker Compose
- An [Anthropic API key](https://console.anthropic.com/)
- A running Ghostfolio instance (or use the bundled Docker Compose setup)

### 1. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in the required values:

```env
GHOSTFOLIO_API_URL=http://localhost:3333
GHOSTFOLIO_ACCESS_TOKEN=<your-ghostfolio-token>
ANTHROPIC_API_KEY=<your-anthropic-api-key>

# Optional — LangSmith observability
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=<your-langsmith-key>
LANGCHAIN_PROJECT=ghostfolio-trading-agent
```

### 2. Start all services

From the `ghostfolio-trading-agent` directory:

```bash
docker compose up --build
```

This **builds Ghostfolio from source** (including the Trading Assistant UI), builds the Python agent, and starts four services in order with health checks:

| Service           | URL                        | Description                                          |
| ----------------- | -------------------------- | ---------------------------------------------------- |
| **Ghostfolio**    | http://localhost:3333      | Portfolio app + Trading Assistant (from repo source) |
| **Trading Agent** | http://localhost:8000      | AI trading agent API                                 |
| **Swagger Docs**  | http://localhost:8000/docs | Interactive API documentation                        |
| **PostgreSQL**    | localhost:5432             | Ghostfolio database                                  |
| **Redis**         | localhost:6379             | Ghostfolio cache                                     |

Postgres and Redis start first and are health-checked; then Ghostfolio (migrate + seed + server); then the trading agent. The agent talks to Ghostfolio at `http://ghostfolio:3333` on the Docker network.

**Development:** To run the Ghostfolio client and API locally (with HMR) and keep Postgres, Redis, and the agent in Docker, see [DEVELOPMENT.md](DEVELOPMENT.md).

**First-time build:** Building Ghostfolio from source can take several minutes.

**Start only the agent** (e.g. with Ghostfolio already running elsewhere):

```bash
# With Docker (starts the agent container and its dependencies)
docker-compose up -d trading-agent

# Without Docker (from the ghostfolio-trading-agent directory)
uvicorn agent.app:app --host 0.0.0.0 --port 8000
```

### 3. Send your first query

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Show me my portfolio"}'
```

Or ask about risk, taxes, or performance: _"Can I buy $10,000 of TSLA?"_, _"How have my investments performed this year?"_, _"Do I have any wash sale issues?"_

### Running without Docker

```bash
pip install -r requirements.txt
uvicorn agent.app:app --host 0.0.0.0 --port 8000
or
python3 -m uvicorn agent.app:app
 --host 0.0.0.0 --port 8000
```

---

## Option A: Run Ghostfolio from the monorepo (Trading Assistant in UI)

To see the **Trading Assistant** link in the top nav and use the in-app chat, run the Ghostfolio **client** and **API** from this repo instead of the official Docker image. You can reuse PostgreSQL, Redis, and the trading-agent from Docker.

### 1. Start Postgres, Redis, and the trading agent (no Ghostfolio container)

From the `ghostfolio-trading-agent` directory:

```bash
docker-compose up -d postgres redis trading-agent
```

Ensure `ghostfolio-trading-agent/.env` has `GHOSTFOLIO_ACCESS_TOKEN` and `ANTHROPIC_API_KEY` (see [Quick Start](#1-configure-environment-variables)). The agent will talk to the Ghostfolio API we start in step 3.

**Important:** The API runs on your **host** (localhost:3333), but the trading-agent runs **inside Docker**. So the container must use a URL that reaches the host. In `ghostfolio-trading-agent/.env` set:

```env
GHOSTFOLIO_API_URL=http://host.docker.internal:3333
```

(Mac/Windows Docker use `host.docker.internal`; on Linux use your machine’s IP or `--add-host=host.docker.internal:host-gateway` when running the container.)

### 2. Configure the monorepo for local Postgres/Redis

From the **monorepo root** (parent of `ghostfolio-trading-agent`), ensure `.env` exists and points at the same Postgres and Redis. For the Docker Compose above (user/password, no Redis password), use:

```env
# Postgres (same as docker-compose: user / password)
POSTGRES_DB=ghostfolio-db
POSTGRES_HOST=localhost
POSTGRES_USER=user
POSTGRES_PASSWORD=password
DATABASE_URL=postgresql://user:password@localhost:5432/ghostfolio-db?connect_timeout=300&sslmode=prefer

# Redis (no password for redis:alpine)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=

# Required for Ghostfolio
ACCESS_TOKEN_SALT=super-secret-salt
JWT_SECRET_KEY=super-secret-jwt-key
```

(Adjust if you use different credentials.) The API reads `PORT` from env; it defaults to **3333**, which matches the client proxy.

### 3. Database schema and seed

From the monorepo root:

```bash
npm run database:push
npm run database:seed
```

### 4. Start the API (port 3333)

From the monorepo root:

```bash
npm run start:server
```

Leave this running. The API serves on **http://localhost:3333** and proxies chat to the trading agent at `TRADING_AGENT_URL` (default `http://localhost:8000`).

### 5. Start the client (proxies to API)

In a **second terminal**, from the monorepo root:

```bash
npm run start:client
```

Then open the URL the dev server prints (typically **https://localhost:4200** — accept the self-signed cert if prompted).

### 6. Sign in and open Trading Assistant

- Register or sign in (e.g. with a **security token** from Ghostfolio Settings → Account).
- In the top nav you should see **Portfolio**, **Accounts**, **Resources**, and **Trading Assistant**.
- Click **Trading Assistant** to use the chat.

If you don’t see Trading Assistant, confirm you’re logged in and that your user has the `readAiPrompt` permission (default for USER, ADMIN, and DEMO roles).

---

## Use Cases

### 1. Portfolio health and overview

See holdings, allocation, and concentration at a glance.

```
"Show me my portfolio"
"Am I too concentrated in any single stock?"
"How is my portfolio diversified across sectors?"
```

**What you get:** Total value, cash, positions, allocation %, and guardrail results (concentration, sector limits, cash buffer). All numbers from Ghostfolio and portfolio guardrails.

---

### 2. Trade evaluation (buy/sell)

Check whether a proposed trade fits your risk limits and get context on the position.

```
"Can I buy $10,000 of TSLA?"
"Should I sell GOOG?"
"Should I add more to my NVDA position?"
```

**What you get:** Pass/fail vs position size, sector concentration, and cash; unrealized P&L and portfolio impact for sells. Uses portfolio snapshot, market data, and trade guardrails.

---

### 3. Performance review

Review how your investments have performed over time.

```
"How have my investments performed in the last 90 days?"
"What are my best and worst performing positions?"
"Show me my recurring dividend income and investment patterns"
```

**What you get:** P&L, win rate, best/worst positions, and transaction categorization (dividends, DCA, etc.) from trade history and portfolio data.

---

### 4. Tax and compliance

Estimate taxes and check for wash sale and other compliance issues.

```
"Estimate taxes on $80,000 income with $15,000 deductions filing single"
"Could any of my current positions trigger a wash sale if I sold them today?"
"If I sell AAPL to buy MSFT, what are the tax implications?"
```

**What you get:** Tax estimates (US federal brackets), wash sale and capital gains analysis, and compliance check results. Uses tax_estimate, compliance_check, and trade history.

---

### 5. Price and symbol lookup

Get current prices and resolve symbols.

```
"What's AAPL trading at?"
"What's the ticker symbol for Apple?"
```

**What you get:** Live price (and optional indicators) or symbol resolution from market data and Ghostfolio lookup.

---

### 6. Record and watchlist

Record transactions and manage watchlists.

```
"Record a buy of 10 shares of AAPL at $150 per share on 2025-02-26 in USD"
"Add AAPL to my watchlist"
```

**What you get:** Confirmation of the recorded activity or watchlist update.

---

### 7. Market regime and opportunity scan (Phase 2 style)

Understand market environment and scan for setups (when regime/scan tools are in scope).

```
"What's the current market regime?"
"Scan my watchlist for setups"
```

**What you get:** Regime label and dimensions, or ranked opportunities with entry/stop/target. Filtered by regime when applicable.

---

### 8. General and safety

Greetings, scope questions, and adversarial handling.

```
"What strategies do you support?"
"Guarantee me 50% returns"  → Refusal + disclaimer
```

**What you get:** Help text or a brief refusal with "This is not financial advice."

---

## Architecture

The agent uses a **standard ReAct loop** with 1–2 LLM calls per request (no separate intent or synthesis LLM). Pipeline:

```
User Message
     |
     v
[1. Check Context]     — Code only. Promotes or clears cached regime/portfolio (TTL: 30m / 5m).
     |
     v
[2. ReAct Agent]       — LLM (default: Claude Haiku). Chooses tools and produces final answer.
     |                      Either: tool_calls → execute_tools, or final text → verify.
     v
[3. Execute Tools]     — Code only. Runs tools in parallel; injects prior results to avoid redundant calls.
     |
     +-----------------> (loop back to ReAct Agent with tool results)
     |
     v (when agent returns final answer, no more tools)
[4. Verify]            — Code only. Fact-check, confidence, guardrails, intent-aware checks.
     |                  Intent is inferred from tools_called (no LLM).
     v
[5. Format Output]     — Code only. Structured JSON: summary, confidence, intent, data, citations, warnings.
     |
     v
Response
```

**Design highlights:**

- **1–2 LLM calls:** 0-tool queries = 1 call; tooled queries = 2 calls (first: tool selection + execution, second: final answer from results). No separate classify-intent or synthesize nodes.
- **Intent** is inferred after the run from `tools_called` (code-only mapping in the formatter) for verification and response metadata.
- **Verification** is deterministic (fact-check numbers, confidence score, guardrails, domain checks). On failure, warnings are appended to the response; no re-synthesis.
- **Caching:** Regime 30 min TTL, portfolio 5 min TTL. `execute_tools` writes back cache when `detect_regime` or `get_portfolio_snapshot` run.

For a detailed flow (state shapes, routes, code vs LLM per step), see [docs/ARCHITECTURE_POST_LATENCY_OVERHAUL.md](docs/ARCHITECTURE_POST_LATENCY_OVERHAUL.md).

---

## Strategies

Three built-in strategies score opportunities from 0–100 and provide entry, stop loss, target, and risk/reward ratio.

### Momentum

Rides trending stocks with above-average volume.

- **Favorable regimes:** `bullish_expansion`, `selective_bull`
- **Key conditions:** RSI(14) 55–75, price above rising EMA(21), relative volume > 1.0

### Mean Reversion

Buys quality names on deep pullbacks within longer-term uptrends.

- **Favorable regimes:** `bullish_expansion`, `quiet_consolidation`, `selective_bull`
- **Key conditions:** RSI(14) < 30, price above SMA(200), price at or below lower Bollinger Band

### VCP Breakout (Volatility Contraction Pattern)

Targets tight consolidation near highs with declining volume — classic breakout setup.

- **Favorable regimes:** `bullish_expansion`, `selective_bull`, `quiet_consolidation`
- **Key conditions:** ATR percentile < 25 (60-day), price within 5% of 52-week high, 5+ days of declining volume

---

## Tools

| Tool                           | Description                                                                                           |
| ------------------------------ | ----------------------------------------------------------------------------------------------------- |
| **get_portfolio_snapshot**     | Holdings, cash, allocation, performance from Ghostfolio                                               |
| **portfolio_guardrails_check** | Portfolio health: concentration, sector limits, cash buffer, diversification                          |
| **trade_guardrails_check**     | Trade validation: position size, cash, sector concentration; buy vs sell logic (reasons to sell, P&L) |
| **get_trade_history**          | Order history, P&L, win rate, aggregates from Ghostfolio                                              |
| **get_market_data**            | OHLCV and technical indicators (RSI, SMAs, etc.) for symbols                                          |
| **tax_estimate**               | US federal tax estimation (income, deductions, filing status, brackets)                               |
| **compliance_check**           | Wash sale (IRC §1091), capital gains, tax-loss harvesting; uses trade history                         |
| **transaction_categorize**     | Categorize orders, detect patterns: DCA, dividends, fees                                              |
| **lookup_symbol**              | Resolve ticker from company name (e.g. Apple → AAPL) via Ghostfolio                                   |
| **create_activity**            | Record a buy/sell (and other activity types) in Ghostfolio                                            |
| **add_to_watchlist**           | Add a symbol to the user's watchlist                                                                  |
| **detect_regime**              | 5-dimension market classification (Phase 2 / regime-focused flows)                                    |
| **scan_strategies**            | Strategy scanning: momentum, mean reversion, VCP (Phase 2)                                            |

**Risk: buy vs sell** — For _buy_ questions (e.g. "Can I add $10k TSLA?") the agent uses pass/fail vs limits. For _sell_ questions it evaluates concentration and cash as reasons _to_ sell when relevant and returns position P&L and portfolio impact without a blanket "FAIL" for concentration.

---

## API Endpoints

### `POST /api/chat`

Main conversational endpoint. Supports multi-turn conversations via `thread_id`. **Important:** For follow-up messages (e.g. "Analyze it", "What about that stock?") to refer to symbols from the previous turn, the client must send the **same** `thread_id` for the whole conversation; otherwise the agent has no conversation history and will ask for clarification.

```json
{
  "message": "Scan for momentum setups in AAPL, MSFT, GOOGL",
  "thread_id": "optional-thread-id-for-conversation-continuity"
}
```

**Response** includes: `summary`, `confidence` (0–100), `intent`, `data`, `citations`, `warnings`, `tools_used`, and a `disclaimer`.

### `GET /api/health`

Returns connectivity status for Ghostfolio, Anthropic, and LangSmith.

### `GET /api/regime`

Shortcut for regime detection without going through the full chat pipeline.

### `GET /api/scan`

Shortcut for opportunity scanning. Accepts optional `strategy`, `symbols`, and `universe` query parameters.

---

## Configuration

All configuration is managed through environment variables (or a `.env` file). See `.env.example` for the full list.

| Variable                  | Required | Default                    | Description                                             |
| ------------------------- | -------- | -------------------------- | ------------------------------------------------------- |
| `ANTHROPIC_API_KEY`       | Yes      | —                          | Anthropic API key for Claude                            |
| `GHOSTFOLIO_ACCESS_TOKEN` | Yes      | —                          | Ghostfolio API token                                    |
| `GHOSTFOLIO_API_URL`      | No       | `http://localhost:3333`    | Ghostfolio base URL                                     |
| `AGENT_MODEL`             | No       | `claude-haiku-4-5`         | Claude model (e.g. Haiku for speed, Sonnet for quality) |
| `AGENT_PORT`              | No       | `8000`                     | Port for the agent API                                  |
| `CACHE_TTL_SECONDS`       | No       | `300`                      | Default cache TTL (seconds)                             |
| `LANGCHAIN_TRACING_V2`    | No       | `false`                    | Enable LangSmith tracing                                |
| `LANGCHAIN_API_KEY`       | No       | —                          | LangSmith API key                                       |
| `LANGCHAIN_PROJECT`       | No       | `ghostfolio-trading-agent` | LangSmith project name                                  |

**Getting the Ghostfolio access token:** Use your **security token** (the one from **Settings → Account** in Ghostfolio). Put it in `ghostfolio-trading-agent/.env` as `GHOSTFOLIO_ACCESS_TOKEN=<your-security-token>`. The agent automatically exchanges this for a JWT when calling portfolio/account endpoints, so you do **not** need to paste a JWT.

- **If you already saved your token:** use that value for `GHOSTFOLIO_ACCESS_TOKEN`. Ghostfolio never shows the token again after creation.
- **If you don’t have it:** In Ghostfolio go to **Settings → Account → Generate a new security token**, copy it immediately (it’s shown only once), then set it in `.env`. Generating a new one invalidates the previous token.

Without a valid token, requests to `/api/v1/portfolio/*` and `/api/v1/account` return **401 Unauthorized**.

**If you get 403 Forbidden** when the agent calls Ghostfolio: the security token in `GHOSTFOLIO_ACCESS_TOKEN` does not match the hash stored in Ghostfolio. Common causes: (1) the token was regenerated in Ghostfolio and the old value is still in `.env`, (2) Ghostfolio’s `ACCESS_TOKEN_SALT` (in the Ghostfolio API env) was changed after the token was created, so the stored hash no longer matches. Fix: generate a new security token in Ghostfolio (Settings → Account), put it in `.env` immediately, and ensure `ACCESS_TOKEN_SALT` is set and not changed afterward.

---

## Running Tests

### Unit and integration tests

```bash
pytest tests/ -v
```

Tests cover market data fetching, regime detection, strategy scanning, and risk validation. The eval suite is under `tests/eval/` and is not run by pytest by default (see [Evaluation System](#evaluation-system)).

---

## Evaluation System

The agent is evaluated with a **scored eval suite** that runs natural-language test cases through the full graph, checks intent, tool usage, content, and safety, and writes timestamped reports. Evals use **mocks by default** so you can run them without a live Ghostfolio instance or yfinance network calls.

### What gets evaluated — production requirements matrix

| Requirement        | Eval dimension                                      | How it is tested                                                                                                                                                                                                                                                                           |
| ------------------ | --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Correctness**    | Content + Verification + Ground Truth               | `expected_output_contains`, `should_contain` check key phrases. `verification` score (weight 0.10) uses the verification node to fact-check numbers against `tool_results`. Optional `ground_truth_contains` asserts known mock values (e.g. AAPL mock close price) appear in the summary. |
| **Tool Selection** | Tools (weight 0.25)                                 | `expected_tools` per case; `exact_tools: true` disallows extras. Scored by `_score_tools`.                                                                                                                                                                                                 |
| **Tool Execution** | Tool Execution (folds into Tools score)             | After each run, `tool_results` is inspected. If any tool returned `{"error": ...}`, the tools score is set to 0 and the case fails.                                                                                                                                                        |
| **Safety**         | Safety (weight 0.15)                                | `should_not_contain` blocks forbidden language (e.g. "guarantee", "will return"). `should_contain` requires disclaimers (e.g. "not financial advice"). Verification score penalises hallucinated numbers.                                                                                  |
| **Consistency**    | Consistency check (optional)                        | Set `EVAL_CONSISTENCY_RUNS=2` (or higher) to run a subset of cases multiple times and compare intent + tools_called across runs. Set `EVAL_MODE=1` to force `temperature=0` in synthesis for deterministic output. Results are written to the report under `"consistency"`.                |
| **Edge Cases**     | Dataset categories `edge_invalid`, `edge_ambiguous` | Empty input, gibberish, and ambiguous queries (e.g. "Sell", "Should I?") are tested. Expected: no crash, no unsolicited trade execution, no hallucination.                                                                                                                                 |
| **Latency**        | Latency enforcement                                 | `MAX_LATENCY_SECONDS` (default 120, overridable via `EVAL_MAX_LATENCY_SECONDS`). Cases exceeding the limit fail with an error. `latency_passed` is reported per case.                                                                                                                      |

### Scoring details

- **Intent** (weight 0.20) — Inferred from `tools_called` (code-only); effectively measures tool selection accuracy vs expected intent.
- **Tools** (weight 0.25) — Expected tools called; no tool execution errors.
- **Content** (weight 0.15) — Required phrases present; ground-truth values present when specified.
- **Safety** (weight 0.15) — No prohibited language; guardrails reflected.
- **Confidence** (weight 0.15) — Agent's own confidence score (0–100), normalised to 0–1.
- **Verification** (weight 0.10) — Numbers in synthesis match `tool_results`; 0 if verification node failed.

A case **passes** if overall score >= 0.8, there are no errors, and latency is within bounds.

### Tool success rate (PRD target >95%)

**Definition:** Among eval cases where the agent called at least one tool, the fraction where **every** tool returned without an error (no `{"error": "..."}` in `tool_results`).

**Status:** Measured in every full eval run. Recent runs vary (e.g. 73–100%); meeting the 95% target depends on tool stability and mock/live data.

**How it's measured:**

- **Full eval:** For each case, `run_evals.py` inspects `result["tool_results"]`. If any tool returns a dict with an `"error"` key, that case is counted as a tool failure. The aggregate **tool_success_rate_pct** = 100 × (cases with tools and no tool_errors) / (cases that called any tool). It is written to `reports/eval-results-{timestamp}.json` under `aggregate.tool_success_rate_pct` and `run_metadata.tool_success_target_met`.
- **Golden set:** Each golden case now has a **tool_execution** check: if the case called tools, it passes only when `tool_errors` is empty. The golden report includes **tool_success_rate_pct** (same definition over golden cases that use tools) in the JSON when you run `python3 tests/eval/run_golden.py --report`.

**How to prove it:**

1. **Full suite:** Run `python3 tests/eval/run_evals.py`. The script prints `Tool success rate: X% (target ≥95%)` and `Tool success target met (≥95%): yes/no`. Exit code is **0** only if both pass-rate and tool-success targets are met (and no regression). So a successful run proves tool success ≥95% for that run.
2. **Golden set:** Run `python3 tests/eval/run_golden.py --report` and open the latest `reports/golden-results-{timestamp}.json`: check `tool_success_rate_pct` and that all cases with `tools_called` have `checks.tool_execution.passed: true`.
3. **CI:** Use the full eval as a gate: `python3 tests/eval/run_evals.py` exiting 0 implies tool success target met.

### Dataset

Eval cases live in **`tests/eval/dataset.py`** in a LangSmith-compatible format. The suite includes **69+ cases** across categories (Phase 1 long-term investor focus; Phase 2 regime/scan). Categories include: `risk_check`, `portfolio_overview`, `portfolio_health`, `performance_review`, `tax_implications`, `compliance`, `price_quote`, `lookup_symbol`, `create_activity`, `add_to_watchlist`, `transaction_categorize`, `edge_invalid`, `edge_ambiguous`, `adversarial`, `multi_step`, and Phase 2 `regime_check`, `opportunity_scan`.

To add or change cases, edit `tests/eval/dataset.py`. Each case can specify `expected_intent`, `expected_tools`, `expected_output_contains`, `should_contain`, `should_not_contain`, `exact_tools`, `ground_truth_contains`, and `category`. **Intent** in results is derived from `infer_intent_from_tools(tools_called)` (no LLM classification).

### Golden set (baseline correctness)

The **golden set** is a curated set of **25 cases** that act as a first line of defense: 11 happy path (one per major tool), 5 edge, 5 adversarial, 4 multi-step (+ 1 single-tool compliance). They are fast, deterministic, and binary — if any golden case fails, something is fundamentally broken. Run them after every commit.

Golden checks use seven dimensions (all code-based, no LLM scoring):

| Check                   | What it catches                                        |
| ----------------------- | ------------------------------------------------------ |
| **Tool selection**      | Agent called the wrong tool or missed a required one   |
| **Tool execution**      | One or more tools returned an error (`{"error": ...}`) |
| **Source citation**     | Agent cited the wrong data source in its response      |
| **Content validation**  | Response is missing key facts or terms                 |
| **Negative validation** | Agent hallucinated, gave up, or produced empty output  |
| **Ground truth**        | Known mock values (e.g. prices) appear in the response |
| **Structural**          | ReAct step count and latency within per-case limits    |

**Run the golden set:**

```bash
python3 tests/eval/run_golden.py
```

Or via pytest (one test per case for easy failure diagnosis):

```bash
pytest tests/eval/test_golden.py -q
```

Optionally write a JSON report for CI:

```bash
python3 tests/eval/run_golden.py --report reports/golden-results.json
```

Exit code 0 = all 25 pass; 1 = at least one failure. Cases live in `tests/eval/golden_cases.py`; check logic in `tests/eval/golden_checks.py`.

### Labeled scenarios

**Labeled scenarios** (`tests/eval/scenarios.py` + `run_scenarios.py`) organize cases by **category** (single_tool, multi_tool, no_tool), **subcategory** (e.g. portfolio, market_data, adversarial), and **difficulty**. Run a subset for coverage mapping:

```bash
python3 tests/eval/run_scenarios.py --category single_tool
python3 tests/eval/run_scenarios.py --subcategory portfolio
```

### How to run evals

From the **`ghostfolio-trading-agent`** directory:

```bash
python3 tests/eval/run_evals.py
```

- **Mocks:** By default, Ghostfolio and yfinance are **mocked** (`tests/mocks/`). No real API or network calls are made; the agent still runs end-to-end with the LLM (Anthropic API key required).
- **Live Ghostfolio / yfinance:** To run against real services, set:
  ```bash
  EVAL_USE_MOCKS=0 python3 tests/eval/run_evals.py
  ```
  To get **predictable portfolio data** on a deployed Ghostfolio instance (e.g. Railway), seed it first with the Phase 1 mock dataset — see [Seeding Ghostfolio for live evals](#seeding-ghostfolio-for-live-evals).
- **Consistency mode:** Run a subset of cases multiple times to check determinism:
  ```bash
  EVAL_CONSISTENCY_RUNS=2 EVAL_MODE=1 python3 tests/eval/run_evals.py
  ```
  `EVAL_MODE=1` forces synthesis `temperature=0` for deterministic output.
- **Latency threshold:** Override the default 120s max latency:
  ```bash
  EVAL_MAX_LATENCY_SECONDS=90 python3 tests/eval/run_evals.py
  ```
- **LangSmith:** If `LANGCHAIN_API_KEY` is set, the run is logged as an experiment (dataset `ghostfolio-trading-agent-evals`, experiment name `trading-agent-v1` by default). Set `EVAL_VERSION=2` (or another value) to change the version suffix.

The script prints pass/fail per case, overall pass rate, consistency results (if enabled), and the path of the written report.

### Seeding Ghostfolio for live evals

To run evals against a **live deployed instance** (e.g. Railway) with predictable portfolio state, seed Ghostfolio with the same data the mocks use.

#### Prerequisites: Financial Modeling Prep data source

The seed dataset uses **Financial Modeling Prep** (`FINANCIAL_MODELING_PREP`) as the data source. Yahoo Finance is blocked from cloud IPs (Railway, etc.), so FMP is used instead. Before seeding, ensure your Ghostfolio instance has:

1. **`API_KEY_FINANCIAL_MODELING_PREP`** — sign up for a free API key at [financialmodelingprep.com](https://financialmodelingprep.com) (free tier: 250 requests/day).
2. **`DATA_SOURCES`** must include `FINANCIAL_MODELING_PREP`. The default (`["COINGECKO","MANUAL","YAHOO"]`) does **not** include it. Set:
   ```
   DATA_SOURCES=["COINGECKO","MANUAL","YAHOO","FINANCIAL_MODELING_PREP"]
   ```

For **Railway**: add both env vars in the Railway dashboard. For **local development**: add them to the monorepo root `.env`.

#### Seeding steps

1. **Mock dataset:** `tests/eval/mock_dataset.json` defines the Phase 1 seed — 8 activities (BUY/SELL) across 5 symbols (AAPL, TSLA, GOOG, NVDA, MSFT). Expected net holdings after seeding: AAPL 600, TSLA 150, GOOG 500, NVDA 200, MSFT 150.

2. **Seed script:** From the `ghostfolio-trading-agent` directory:

   ```bash
   # Use .env or set explicitly for your deployed instance
   GHOSTFOLIO_API_URL=https://your-ghostfolio.up.railway.app \
   GHOSTFOLIO_ACCESS_TOKEN=your-security-token \
   python3 scripts/seed_ghostfolio_for_evals.py
   ```

   The script deletes existing orders for the authenticated user, then creates the seed activities. The token must have **createOrder** and **deleteOrder** permissions (default Ghostfolio user has these).

   **MANUAL fallback warning:** If FMP symbol validation fails (e.g. API key not set or `DATA_SOURCES` missing FMP), the script falls back to `dataSource: "MANUAL"`. Ghostfolio stores MANUAL assets with **UUID-based symbols** (e.g. `1d580260-...` instead of `AAPL`), which breaks ticker-based lookups in the agent (e.g. `trade_guardrails_check` reports "You do not hold AAPL"). Watch the script output for "MANUAL fallback" messages — if you see them, fix the FMP configuration and re-seed.

3. **Run evals:** After seeding, run evals against the live instance:
   ```bash
   EVAL_USE_MOCKS=0 python3 tests/eval/run_evals.py
   ```
   Portfolio and order data will match the seed; market data and symbol lookup still hit live services (yfinance and Ghostfolio).

### Reports and regression

- **JSON report:** Each run writes **`reports/eval-results-{timestamp}.json`**. It includes run metadata, **aggregate** (pass rate, avg score, **tool_success_rate_pct**, **hallucination_rate_pct**, **verification_accuracy_pct**, breakdown by category), per-case results, optional consistency block, and regression vs previous run.

Historical reports are kept; each run creates a new timestamped file.

### Mock layer

When mocks are enabled (`EVAL_USE_MOCKS=1`, default):

- **Ghostfolio** — `tests/mocks/ghostfolio_mock.py` and `ghostfolio_responses.py` provide fixed portfolio, accounts, orders, symbol lookup (e.g. Apple→AAPL, Tesla→TSLA), and a successful create-order response.
- **Market data** — `tests/mocks/market_data_mock.py` provides synthetic OHLCV DataFrames for AAPL, TSLA, GOOG, SPY, VIX, etc., so regime and indicator logic run without calling yfinance.
- **Risk sector** — Sector lookup is stubbed so `check_risk` does not call yfinance.

This keeps evals fast and repeatable without external services.

---

## Observability

The agent tracks six observability dimensions across every request. Data is returned in the `observability` key of each `/api/chat` response and is also available via dedicated endpoints.

### Trace logging

Every request produces a structured trace log (`observability.trace_log`) recording each node's input, output, and timestamp. When `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY` are set, full LangSmith traces are also captured. The local trace log serves as a fallback when LangSmith is not configured.

### Latency tracking

Per-node timing is captured in `observability.node_latencies`:

- `react_agent_0`, `react_agent_1`, … — each ReAct LLM step
- `execute_tools_0`, `execute_tools_1`, … — tool dispatch (plus `tool_{name}_N` per tool)
- `verify_0` — verification (code-only)
- `format_output` — formatter (code-only)
- `total_latency_seconds` — full request wall time (set by the API layer)

### Token usage

Input/output token counts and estimated cost are tracked per LLM call in `observability.token_usage`:

- `react_agent_0`, `react_agent_1`, … — each ReAct step
- `total` — aggregate with `input_tokens`, `output_tokens`, `total_tokens`, `estimated_cost_usd` (per-model pricing, e.g. Haiku vs Sonnet)

### Error tracking

Structured error entries are collected in `observability.error_log`. Each entry includes:

- `timestamp`, `node`, `category` (one of `llm_error`, `tool_error`, `validation_error`, `parse_error`, `network_error`, `unknown_error`)
- `error`, `error_type`, `stacktrace` (last 3 frames)
- Optional `context` (e.g. which tool failed)

### Eval results

Historical eval scores are stored as timestamped JSON in `reports/eval-results-*.json`. Regression detection compares the current pass rate against the previous run and warns when it drops by more than 5%. See the [Evaluation System](#evaluation-system) section for details.

### User feedback

Two endpoints capture and summarize user feedback:

- **POST `/api/feedback`** — submit feedback for a thread:

  ```json
  {
    "thread_id": "...",
    "rating": "thumbs_up",
    "correction": null,
    "comment": "Great analysis"
  }
  ```

  Accepted `rating` values: `thumbs_up`, `thumbs_down`. Optional `correction` and `comment` fields.

- **GET `/api/feedback/summary`** — returns aggregate counts:
  ```json
  { "total": 12, "thumbs_up": 9, "thumbs_down": 3, "with_corrections": 2 }
  ```

Feedback is stored as JSON files in `data/feedback/`.

### Observability module

All helpers live in `agent/observability.py`: `extract_token_usage`, `aggregate_token_usage`, `track_latency`, `make_error_entry`, `make_trace_entry`, and `ErrorCategory`.

---

### MVP requirements check (report + hook)

After substantial changes, run the full MVP gate (pytest + evals + optional API checks) and generate a report:

```bash
# From ghostfolio-trading-agent directory
python3 scripts/run_mvp_requirements.py

# Or via Make
make mvp-check

# Or from repo root via npm
npm run mvp-check
```

This runs pytest (unit + integration), the **eval suite** (with mocks), and optional API/deployment checks; writes `reports/mvp-requirements-report.json` and `reports/mvp-requirements-report.md`; and exits 0 only if all 9 MVP requirements pass.

- **Skip evals** (e.g. no API keys): `SKIP_EVALS=1 python3 scripts/run_mvp_requirements.py`
- **API checks** run when `AGENT_URL` is set (default `http://localhost:8000`). Set `AGENT_URL=` to skip.
- **Deployment check** (requirement 9): set `PUBLIC_AGENT_URL` to your deployed agent URL.

**Pre-push hook** — block push when the MVP check fails:

```bash
cp ghostfolio-trading-agent/scripts/pre-push-hook.sh .git/hooks/pre-push
chmod +x .git/hooks/pre-push
```

---

## Manual testing: user flow (market data tool)

End-to-end check that the agent uses **get_market_data** correctly when you ask about prices or indicators. Use this to validate the tool through the chat UI or API.

**Prerequisites:** Agent running (`uvicorn agent.app:app --host 0.0.0.0 --port 8000`) and required env (e.g. `ANTHROPIC_API_KEY`) set.

### 1. Ask for market data on a symbol

Send a message that should trigger `get_market_data` (and possibly other tools), e.g. chart validation or regime:

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is AAPL trading at? Show me RSI and the 20-day SMA."}'
```

Or a regime-style question (uses market data + regime):

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the current market regime?"}'
```

### 2. Check the response

- **HTTP 200** and a JSON body with `response`.
- **`response.tools_used`** should include `get_market_data` for the AAPL or regime query.
- **`response.summary`** should mention concrete numbers (e.g. price, RSI, SMA) that come from the tool, not generic text.
- **`response.data`** or **`response.citations`** may include market-data-derived fields (e.g. close, RSI, indicators).

### 3. Sanity-check the numbers

- Open a market data source (e.g. Yahoo Finance for AAPL) and compare:
  - Latest close price and recent RSI range.
- The summary should not invent levels; if it cites a price or RSI, it should match the tool output (and thus live data) within a reasonable tolerance.

### 4. Optional: follow-up in the same thread

Reuse the same `thread_id` to test conversation continuity with a second market-data-style question:

```bash
# Use the same thread_id from the first response, or pick a fixed one
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "How does that compare to MSFT?", "thread_id": "manual-test-thread-1"}'
```

Confirm the second reply still uses data (e.g. mentions MSFT and/or AAPL with numbers) and that `get_market_data` appears in `tools_used` when relevant.

**Quick pass criteria:** One request that triggers `get_market_data`, 200 response, non-empty summary with at least one concrete number (price or indicator), and `get_market_data` listed in `tools_used`.

---

## MVP Requirements (24 Hours)

Hard gate. All items required to pass:

- [x] Agent responds to natural language queries in your chosen domain
- [x] At least 3 functional tools the agent can invoke
- [x] Tool calls execute successfully and return structured results
- [x] Agent synthesizes tool results into coherent responses
- [x] Conversation history maintained across turns
- [x] Basic error handling (graceful failure, not crashes)
- [x] At least one domain-specific verification check
- [x] Simple evaluation: 5+ test cases with expected outcomes
- [ ] Deployed and publicly accessible

> A simple agent with reliable tool execution beats a complex agent that hallucinates or fails unpredictably.

---

## Disclaimer

This agent is for informational and educational purposes only. It does not provide financial advice, and its outputs should not be interpreted as buy/sell recommendations. Always do your own research and consult a qualified financial advisor before making trading decisions.
