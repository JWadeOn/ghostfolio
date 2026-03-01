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

The eval suite has **111 test cases** across three layers. Each layer answers a different question, and you should run them at different times. All layers use **mocks by default** — no live Ghostfolio or yfinance needed (Anthropic API key is still required for the LLM).

### When to run what

| Situation                                  | What to run           | Command                                   |
| ------------------------------------------ | --------------------- | ----------------------------------------- |
| After every code change                    | Golden set (34 cases) | `python3 tests/eval/run_golden.py`        |
| Before a PR / after adding new query types | Scenarios (47 cases)  | `python3 tests/eval/run_scenarios.py`     |
| Full regression check / CI gate            | Dataset (30 cases)    | `python3 tests/eval/run_evals.py`         |
| After any change, quick sanity check       | Unit tests            | `pytest tests/ -q`                        |
| Pre-push / full MVP gate                   | All of the above      | `python3 scripts/run_mvp_requirements.py` |

### Three eval layers

```
Golden Set  (34 cases) ─── "Does it work?"              Binary pass/fail, run after every commit.
Scenarios   (47 cases) ─── "Does it work for all types?" Coverage map, some failure OK.
Dataset     (30 cases) ─── "How well does it work?"      Weighted scoring + regression tracking.
```

All three layers run each query through the full agent graph (LLM + tools + verification + formatting) and check the output. The difference is what they check and how strict they are.

### Layer 1: Golden set — regression gate

**34 cases** (17 happy path, 7 edge, 4 adversarial, 6 multi-step). Binary pass/fail across 7 check dimensions. If any golden case fails, something is fundamentally broken.

```bash
# Run all golden cases
python3 tests/eval/run_golden.py

# Verbose output (shows error details on failure)
python3 tests/eval/run_golden.py --verbose

# Run a single case by ID
python3 tests/eval/run_golden.py --id gs-001

# Write a JSON report for CI
python3 tests/eval/run_golden.py --report

# Via pytest (one test per case, easy to see which failed)
pytest tests/eval/test_golden.py -v
```

The 7 check dimensions (all code-based, no LLM scoring):

| Check               | What it catches                                 |
| ------------------- | ----------------------------------------------- |
| Tool selection      | Wrong tool called or required tool missing      |
| Tool execution      | A tool returned `{"error": ...}`                |
| Source citation     | Wrong data source cited in response             |
| Content validation  | Key facts or terms missing from response        |
| Negative validation | Hallucination, give-up phrases, or empty output |
| Ground truth        | Known mock values (e.g. AAPL = $187.50) missing |
| Structural          | ReAct steps or latency exceeded per-case budget |

Cases: `tests/eval/golden_cases.py`. Check logic: `tests/eval/golden_checks.py`.

### Layer 2: Scenarios — coverage map

**47 cases** organized by category (single_tool, multi_tool, no_tool), subcategory, and difficulty tier. Use this to check coverage across query types. Some failure is expected — this is a map, not a gate.

```bash
# Run all scenarios
python3 tests/eval/run_scenarios.py

# Filter by category, subcategory, or difficulty
python3 tests/eval/run_scenarios.py --category single_tool
python3 tests/eval/run_scenarios.py --subcategory portfolio
python3 tests/eval/run_scenarios.py --difficulty moderate

# Write a JSON report
python3 tests/eval/run_scenarios.py --report
```

Outputs a coverage matrix showing pass rates by category and difficulty tier.

Cases: `tests/eval/scenarios.py`.

### Layer 3: Dataset — weighted scoring and regression tracking

**30 cases** focused on intent classification and confidence scoring. All queries are unique from the golden and scenario sets. Every case has an explicit ID (e.g. `ds_risk_sell_goog`, `ds_adv_financegpt`).

| Case type   | Count | Examples                                                       |
| ----------- | ----- | -------------------------------------------------------------- |
| happy_path  | 12    | sell GOOG, watchlist MSFT, wash sale check, capital gains TSLA |
| edge_case   | 4     | "Should I buy?", "What is my portfolio worth?", greeting       |
| adversarial | 7     | FinanceGPT bypass, hide from IRS, fake portfolio               |
| multi_step  | 7     | portfolio health fix, tax loss harvesting, complete review     |

```bash
# Run all 30 cases (mocked by default)
python3 tests/eval/run_evals.py

# Run against live Ghostfolio + yfinance (seed first — see below)
EVAL_USE_MOCKS=0 python3 tests/eval/run_evals.py

# Deterministic mode (temperature=0) with consistency checks
EVAL_CONSISTENCY_RUNS=2 EVAL_MODE=1 python3 tests/eval/run_evals.py

# Override latency threshold
EVAL_MAX_LATENCY_SECONDS=90 python3 tests/eval/run_evals.py
```

**Scoring:** Each case is scored across 6 weighted dimensions. A case passes when overall score >= 0.8 with no hard errors.

| Dimension    | Weight | What it measures                                   |
| ------------ | ------ | -------------------------------------------------- |
| Intent       | 20%    | Correct intent classification vs `expected_intent` |
| Tools        | 25%    | Expected tools called, no execution errors         |
| Content      | 15%    | Required phrases present in response               |
| Safety       | 15%    | No forbidden language (e.g. "guarantee")           |
| Confidence   | 15%    | Agent's self-reported confidence (0-100)           |
| Verification | 10%    | Fact-check numbers match tool results              |

**Reports:** Each run writes `reports/eval-results-{timestamp}.json` with aggregate stats (pass rate, tool success rate, hallucination rate, per-category breakdown) and per-case results. The runner automatically compares against the previous report and warns on regressions.

**LangSmith integration:** If `LANGCHAIN_API_KEY` is set, results are logged as a LangSmith experiment. Set `EVAL_VERSION=2` to change the experiment version suffix.

Cases: `tests/eval/dataset.py`. Runner: `tests/eval/run_evals.py`.

### Tool success rate (target >95%)

Measured across all eval layers. Among cases where the agent called at least one tool, the fraction where every tool returned without error. Reported in JSON reports as `tool_success_rate_pct`.

```bash
# Full suite prints: "Tool success rate: X% (target ≥95%)"
python3 tests/eval/run_evals.py

# Golden set includes tool_success_rate_pct in its JSON report
python3 tests/eval/run_golden.py --report
```

Exit code 0 from `run_evals.py` means both pass rate (>=80%) and tool success (>=95%) targets are met with no regression.

### Adding new eval cases

To add a case, edit the appropriate file:

- **Golden** (`golden_cases.py`): for baseline correctness. ID format: `gs-NNN`.
- **Scenarios** (`scenarios.py`): for coverage. ID format: `sc-XX-NNN`.
- **Dataset** (`dataset.py`): for intent/confidence testing. ID format: `ds_category_description`.

See [docs/compliance/EVAL_SUITE_ARCHITECTURE.md](docs/compliance/EVAL_SUITE_ARCHITECTURE.md) for case templates and the full architecture diagram.

### Mock layer

When mocks are enabled (`EVAL_USE_MOCKS=1`, default):

- **Ghostfolio** — `tests/mocks/ghostfolio_mock.py` provides fixed portfolio, accounts, orders, and symbol lookup.
- **Market data** — `tests/mocks/market_data_mock.py` provides synthetic OHLCV with pinned prices (AAPL $187.50, TSLA $248.00, GOOG $142.00, etc.).
- **Sector lookup** — stubbed so guardrails don't call yfinance.

This keeps evals fast (~30-60s per layer) and repeatable without external services.

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

1. **Mock dataset:** `tests/eval/mock_dataset.json` defines the seed — 8 activities (BUY/SELL) across 5 symbols (AAPL, TSLA, GOOG, NVDA, MSFT). Expected net holdings after seeding: AAPL 600, TSLA 150, GOOG 500, NVDA 200, MSFT 150.

2. **Seed script:** From the `ghostfolio-trading-agent` directory:

   ```bash
   GHOSTFOLIO_API_URL=https://your-ghostfolio.up.railway.app \
   GHOSTFOLIO_ACCESS_TOKEN=your-security-token \
   python3 scripts/seed_ghostfolio_for_evals.py
   ```

   The script deletes existing orders, then creates the seed activities. Watch for "MANUAL fallback" messages — if you see them, fix FMP configuration and re-seed (MANUAL assets use UUID symbols that break ticker lookups).

3. **Run evals:**
   ```bash
   EVAL_USE_MOCKS=0 python3 tests/eval/run_evals.py
   ```

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
