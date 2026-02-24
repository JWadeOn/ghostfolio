# Ghostfolio Trading Agent

An AI-powered trading intelligence agent built with [LangGraph](https://github.com/langchain-ai/langgraph) and [Anthropic Claude](https://www.anthropic.com/). It integrates with [Ghostfolio](https://ghostfol.io) to provide regime-aware market analysis, opportunity scanning, risk validation, and portfolio review through a conversational REST API.

## Table of Contents

- [Quick Start](#quick-start)
- [Use Cases](#use-cases)
- [Architecture](#architecture)
- [Strategies](#strategies)
- [Tools](#tools)
- [API Endpoints](#api-endpoints)
- [Configuration](#configuration)
- [Running Tests](#running-tests)

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

```bash
docker-compose up -d
```

This launches four services:

| Service           | URL                        | Description                   |
| ----------------- | -------------------------- | ----------------------------- |
| **Ghostfolio**    | http://localhost:3333      | Portfolio management platform |
| **Trading Agent** | http://localhost:8000      | AI trading agent API          |
| **Swagger Docs**  | http://localhost:8000/docs | Interactive API documentation |
| **PostgreSQL**    | localhost:5432             | Ghostfolio database           |
| **Redis**         | localhost:6379             | Ghostfolio cache              |

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

| Tool                       | Description                                                                                                                               |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| **get_market_data**        | Fetches OHLCV data and computes 20+ technical indicators (RSI, MACD, SMAs, EMAs, Bollinger Bands, ATR, relative volume, 52-week position) |
| **detect_regime**          | Classifies the market across 5 dimensions using SPY, VIX, and 9 sector ETFs                                                               |
| **scan_strategies**        | Runs all strategies against a symbol universe, filtered by current regime                                                                 |
| **get_portfolio_snapshot** | Retrieves holdings, performance, and account data from Ghostfolio                                                                         |
| **check_risk**             | Validates a proposed trade against position size, sector, correlation, exposure, and cash limits                                          |
| **get_trade_history**      | Pulls order history from Ghostfolio and computes P&L, win rate, and other aggregate stats                                                 |
| **lookup_symbol**          | Searches Ghostfolio for symbols by name or ticker                                                                                         |

---

## API Endpoints

### `POST /api/chat`

Main conversational endpoint. Supports multi-turn conversations via `thread_id`.

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

---

## Running Tests

### Unit and integration tests

```bash
pytest tests/ -v
```

Tests cover market data fetching, regime detection, strategy scanning, and risk validation.

### Evaluation suite

Run the full eval dataset (12 cases across all intents) against the live agent:

```bash
python tests/eval/run_evals.py
```

This validates intent classification accuracy, correct tool execution, output content, and guardrail enforcement.

### MVP requirements check (report + hook)

After substantial changes, run the full MVP gate and generate a report:

```bash
# From ghostfolio-trading-agent directory
python3 scripts/run_mvp_requirements.py

# Or via Make
make mvp-check

# Or from repo root via npm
npm run mvp-check
```

This runs pytest (unit + integration), the eval suite, and optional API/deployment checks; writes `reports/mvp-requirements-report.json` and `reports/mvp-requirements-report.md`; and exits 0 only if all 9 MVP requirements pass.

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

- [ ] Agent responds to natural language queries in your chosen domain
- [ ] At least 3 functional tools the agent can invoke
- [ ] Tool calls execute successfully and return structured results
- [ ] Agent synthesizes tool results into coherent responses
- [ ] Conversation history maintained across turns
- [ ] Basic error handling (graceful failure, not crashes)
- [ ] At least one domain-specific verification check
- [ ] Simple evaluation: 5+ test cases with expected outcomes
- [ ] Deployed and publicly accessible

> A simple agent with reliable tool execution beats a complex agent that hallucinates or fails unpredictably.

---

## Disclaimer

This agent is for informational and educational purposes only. It does not provide financial advice, and its outputs should not be interpreted as buy/sell recommendations. Always do your own research and consult a qualified financial advisor before making trading decisions.

## BONUS

add a tool that fetches 'political' movers
