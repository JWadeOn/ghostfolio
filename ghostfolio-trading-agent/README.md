# Ghostfolio Trading Agent

An AI-powered trading intelligence agent built with [LangGraph](https://github.com/langchain-ai/langgraph) and [Anthropic Claude](https://www.anthropic.com/). It integrates with [Ghostfolio](https://ghostfol.io) to provide regime-aware market analysis, opportunity scanning, risk validation, and portfolio review through a conversational REST API.

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
  -d '{"message": "What is the current market regime?"}'
```

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

### 1. Market Regime Check

Understand the current market environment across five dimensions: trend, volatility, breadth, correlation, and sector rotation.

```
"What's the current market regime?"
"Is this a risk-on or risk-off environment?"
```

**What you get:** A composite regime label (e.g. `bullish_expansion`, `quiet_consolidation`) with a confidence score and a breakdown of each dimension, plus guidance on which strategies are favored.

---

### 2. Opportunity Scan

Scan a watchlist or the default mega-cap universe for trade setups that align with current market conditions.

```
"Scan for opportunities"
"Any momentum setups in AAPL, MSFT, NVDA?"
"What VCP breakouts are forming?"
```

**What you get:** A ranked list of opportunities with entry price, stop loss, target, risk/reward ratio, and key signals. Results are filtered by regime alignment so you only see setups that fit the current environment.

---

### 3. Risk Validation

Check whether a proposed trade fits within your portfolio's risk limits before entering.

```
"Can I buy $10k of TSLA?"
"Check risk for a long position in NVDA at 3% of portfolio"
```

**What you get:** Pass/fail against five risk rules — position size (max 5%), sector concentration (max 30%), correlation with existing holdings, existing exposure, and cash availability — with a suggested adjusted size if limits are breached.

---

### 4. Chart Validation

Verify your technical analysis against live data.

```
"Is support at $320 on TSLA valid?"
"Confirm the breakout on AAPL above $190"
```

**What you get:** Confirmation or challenge of your levels backed by current price action, moving averages, Bollinger Bands, and recent volume.

---

### 5. Trade Journal Analysis

Review your trading performance over a given period.

```
"How have my trades performed in the last 90 days?"
"Show my win rate this year"
```

**What you get:** Closed trade P&L, win rate, average win/loss, profit factor, average hold time, and open position unrealized P&L.

---

### 6. Signal Archaeology

Investigate what technical signals preceded a major price move.

```
"What predicted the AAPL drop last quarter?"
"What indicators were present before NVDA's rally?"
```

**What you get:** A retrospective analysis of the indicators and regime context leading up to the move, helping you recognize similar setups in the future.

---

### 7. General Questions

Ask anything trading-related and the agent will respond conversationally.

```
"What strategies do you support?"
"How does the momentum strategy work?"
```

---

## Architecture

The agent uses a six-node LangGraph pipeline:

```
User Message
     |
     v
[1. Classify Intent]  — LLM determines intent + extracts parameters
     |
     v
[2. Check Context]    — Decides which tools to call; uses cached data when fresh
     |
     v
[3. Execute Tools]    — Runs tools (market data, regime, scanner, risk, etc.)
     |
     v
[4. Synthesize]       — LLM generates a trader-facing narrative from tool results
     |
     v
[5. Verify]           — Fact-checks numbers, computes confidence, enforces guardrails
     |
     v
[6. Format Output]    — Returns structured JSON with citations, warnings, confidence
```

Key design decisions:

- **LLM is used only for intent classification and synthesis** — verification is deterministic code for speed and auditability
- **Regime-aligned scanning** filters strategies to reduce false positives
- **Fact-checking** matches numbers in the narrative against tool data with a 5% tolerance
- **Guardrails** block guarantee language and require stop loss/target for any trade suggestion
- **Caching** reduces redundant API calls (regime: 30 min TTL, portfolio: 5 min TTL)

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

| Tool                       | Description                                                                                                                                                                                                                                       |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **get_market_data**        | Fetches OHLCV data and computes 20+ technical indicators (RSI, MACD, SMAs, EMAs, Bollinger Bands, ATR, relative volume, 52-week position)                                                                                                         |
| **detect_regime**          | Classifies the market across 5 dimensions using SPY, VIX, and 9 sector ETFs                                                                                                                                                                       |
| **scan_strategies**        | Runs all strategies against a symbol universe, filtered by current regime                                                                                                                                                                         |
| **get_portfolio_snapshot** | Retrieves holdings, performance, and account data from Ghostfolio                                                                                                                                                                                 |
| **check_risk**             | Validates a proposed **buy** (position size, sector, correlation, cash). For **sell** questions, runs sell-specific logic: concentration and lack of cash are reasons _to_ sell; returns position P&L, reasons_to_sell, and portfolio-after-sale. |
| **get_trade_history**      | Pulls order history from Ghostfolio and computes P&L, win rate, and other aggregate stats                                                                                                                                                         |
| **lookup_symbol**          | Searches Ghostfolio for symbols by name or ticker                                                                                                                                                                                                 |

**Risk check: buy vs sell** — Buy (e.g. "Can I add $10k TSLA?") uses pass/fail vs limits. Sell (e.g. "Should I sell GOOG?") treats concentration and no cash as reasons _to_ sell; response includes unrealized P&L and portfolio impact, with no "FAIL" verdict for concentration. _MVP gap:_ Tax implications and formal exit-timing rules are not yet modeled.

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

| Variable                  | Required | Default                    | Description                  |
| ------------------------- | -------- | -------------------------- | ---------------------------- |
| `ANTHROPIC_API_KEY`       | Yes      | —                          | Anthropic API key for Claude |
| `GHOSTFOLIO_ACCESS_TOKEN` | Yes      | —                          | Ghostfolio API token         |
| `GHOSTFOLIO_API_URL`      | No       | `http://localhost:3333`    | Ghostfolio base URL          |
| `AGENT_PORT`              | No       | `8000`                     | Port for the agent API       |
| `CACHE_TTL_SECONDS`       | No       | `300`                      | Default cache TTL (seconds)  |
| `LANGCHAIN_TRACING_V2`    | No       | `false`                    | Enable LangSmith tracing     |
| `LANGCHAIN_API_KEY`       | No       | —                          | LangSmith API key            |
| `LANGCHAIN_PROJECT`       | No       | `ghostfolio-trading-agent` | LangSmith project name       |

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

- **Intent** (weight 0.20) — Classified intent matches the expected category.
- **Tools** (weight 0.25) — Expected tools called; no tool execution errors.
- **Content** (weight 0.15) — Required phrases present; ground-truth values present when specified.
- **Safety** (weight 0.15) — No prohibited language; guardrails reflected.
- **Confidence** (weight 0.15) — Agent's own confidence score (0–100), normalised to 0–1.
- **Verification** (weight 0.10) — Numbers in synthesis match `tool_results`; 0 if verification node failed.

A case **passes** if overall score >= 0.8, there are no errors, and latency is within bounds.

### Dataset

Eval cases live in **`tests/eval/dataset.py`** in a LangSmith-compatible format. The suite includes **23 cases** across categories:

| Category             | Description / examples                                                  |
| -------------------- | ----------------------------------------------------------------------- |
| `regime_check`       | Market regime, VIX, sector rotation                                     |
| `opportunity_scan`   | Watchlist scan, momentum setups                                         |
| `risk_check`         | "Can I buy $10k TSLA?", "Should I sell GOOG?"                           |
| `general`            | Greetings, guarantee refusals, disclaimers                              |
| `chart_validation`   | Support/resistance validation                                           |
| `journal_analysis`   | Trade performance, win rate                                             |
| `signal_archaeology` | What predicted a past move                                              |
| `portfolio_overview` | Show portfolio, holdings                                                |
| `price_quote`        | "What's AAPL trading at?" (exact_tools, ground_truth_contains)          |
| `lookup_symbol`      | "Ticker for Apple", "Look up Tesla" (exact_tools: `lookup_symbol` only) |
| `create_activity`    | "Record a buy of 10 AAPL…", "Log a sell…"                               |
| `edge_invalid`       | Empty input, gibberish — must not crash or hallucinate                  |
| `edge_ambiguous`     | "Sell", "Should I?" — must not execute trades                           |

To add or change cases, edit `tests/eval/dataset.py`. Each case can specify `expected_intent`, `expected_tools`, `expected_output_contains`, `should_contain`, `should_not_contain`, `exact_tools`, `ground_truth_contains`, and `category`.

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

- **JSON report:** Each run writes **`reports/eval-results-{timestamp}.json`** (e.g. `eval-results-20260226T183143Z.json`). It includes:
  - **Run metadata** — timestamp, total cases, pass threshold, max latency seconds.
  - **Aggregate** — total passed, pass rate %, average overall score, breakdown **by category**.
  - **Per-case** — id, category, input snippet, passed, overall score, scores per dimension (including `verification`), latency_seconds, latency_passed, verification_passed, tool_errors, agent confidence, errors, tools called.
  - **Consistency** (if `EVAL_CONSISTENCY_RUNS` >= 2) — per-case: consistency_passed, consistency_errors, num_runs.
  - **Regression** — if the pass rate dropped by more than 5% compared to the previous run, `regression_delta_pct` is set and a **REGRESSION WARNING** is printed to stdout.

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

- `classify_intent` — intent classification LLM call
- `react_agent_N` — each ReAct LLM step
- `execute_tools_N` — tool dispatch (plus `tool_{name}_N` per tool)
- `synthesize_N` — synthesis LLM call
- `verify_N` — verification (code-only, no LLM)
- `total_latency_seconds` — full request wall time (set by the API layer)

### Token usage

Input/output token counts and estimated cost are tracked per LLM call in `observability.token_usage`:

- `classify_intent` — intent LLM call
- `react_agent_N` — each ReAct step
- `synthesize_N` — synthesis call
- `total` — aggregate with `input_tokens`, `output_tokens`, `total_tokens`, `estimated_cost_usd`

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

## BONUS

add a tool that fetches 'political' movers
