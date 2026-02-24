# Build the MVP: Ghostfolio Trading Intelligence Agent

You are building a trading intelligence agent that extends the Ghostfolio open-source portfolio tracker. The agent is a Python FastAPI service that sits alongside Ghostfolio's existing NestJS backend and uses LangGraph to orchestrate tool calls, LLM reasoning, and verification.

## What Already Exists

The Ghostfolio repo is already forked and running locally. It provides:

- NestJS backend on port 3333 with REST API (portfolio, orders, watchlist, symbols, market data, accounts)
- PostgreSQL database with Prisma ORM (User, Account, Order, SymbolProfile, MarketData, etc.)
- Redis for caching and Bull queues
- JWT and API key authentication
- Docker Compose for local development

You do NOT need to modify any Ghostfolio code for the MVP. You are building a separate Python service that calls Ghostfolio's existing API endpoints.

## What You Are Building

A Python FastAPI + LangGraph agent service that:

1. Accepts natural language queries from traders via a REST API
2. Uses LangGraph to orchestrate a multi-step reasoning flow
3. Calls 7 deterministic tools (no LLM in tool execution)
4. Uses Claude (Anthropic) for intent classification and synthesis only
5. Verifies every response before returning it
6. Tracks everything via LangSmith

## Project Structure

```
ghostfolio-trading-agent/
├── agent/
│   ├── __init__.py
│   ├── app.py                  # FastAPI application entry point
│   ├── graph.py                # LangGraph agent definition (the 6-node graph)
│   ├── state.py                # Agent state schema (TypedDict for LangGraph)
│   ├── nodes/
│   │   ├── __init__.py
│   │   ├── intent.py           # Node 1: Intent classification (LLM)
│   │   ├── context.py          # Node 2: Context freshness check (code)
│   │   ├── tools.py            # Node 3: Tool execution router (code)
│   │   ├── synthesis.py        # Node 4: Synthesize results (LLM)
│   │   ├── verification.py     # Node 5: Fact-check, confidence, guardrails (code)
│   │   └── formatter.py        # Node 6: Structure output JSON (code)
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── market_data.py      # Tool 1: get_market_data (yfinance + indicators)
│   │   ├── portfolio.py        # Tool 2: get_portfolio_snapshot (Ghostfolio API)
│   │   ├── regime.py           # Tool 3: detect_regime (rules-based classification)
│   │   ├── scanner.py          # Tool 4: scan_strategies (rules engine)
│   │   ├── risk.py             # Tool 5: check_risk (position/sector limits)
│   │   ├── history.py          # Tool 6: get_trade_history (orders + outcomes)
│   │   └── symbols.py          # Tool 7: lookup_symbol (Ghostfolio API)
│   ├── strategies/
│   │   ├── __init__.py
│   │   ├── base.py             # Base strategy interface
│   │   ├── vcp_breakout.py     # Volatility Contraction Breakout
│   │   ├── mean_reversion.py   # Mean Reversion (RSI oversold + uptrend)
│   │   └── momentum.py         # Momentum Continuation
│   ├── config.py               # Environment variables and settings
│   └── ghostfolio_client.py    # HTTP client for Ghostfolio API calls
├── tests/
│   ├── __init__.py
│   ├── test_market_data.py     # Unit tests for get_market_data tool
│   ├── test_regime.py          # Unit tests for detect_regime tool
│   ├── test_scanner.py         # Unit tests for scan_strategies tool
│   ├── test_risk.py            # Unit tests for check_risk tool
│   ├── test_graph.py           # Integration tests for the full agent graph
│   └── eval/
│       ├── __init__.py
│       ├── dataset.py          # Eval test cases (LangSmith format)
│       └── run_evals.py        # Eval runner
├── docker-compose.yml          # Agent service + Ghostfolio + Postgres + Redis
├── Dockerfile                  # Python agent container
├── requirements.txt
├── .env.example
└── README.md
```

## Build Order — Follow This Sequence Exactly

### Step 1: Foundation (get_market_data tool)

Build `agent/tools/market_data.py` FIRST. Everything else depends on this.

```python
# What get_market_data does:
# Input: symbols (list of str), period (str like "60d"), interval (str, default "1d")
# Process:
#   1. Fetch OHLCV data from yfinance for all symbols
#   2. Compute technical indicators from the raw data:
#      - RSI(14)
#      - SMA(20), SMA(50), SMA(200)
#      - EMA(10), EMA(21)
#      - MACD(12, 26, 9) — MACD line, signal line, histogram
#      - Bollinger Bands(20, 2) — upper, middle, lower
#      - ATR(14)
#      - Relative volume (current volume / 20-day average volume)
#      - Distance from 52-week high (%)
#      - Distance from 52-week low (%)
#   3. Return structured dict per symbol with raw OHLCV + all indicators
# Output: dict keyed by symbol, each containing a list of dated records
#         with open, high, low, close, volume, and all indicator values

# Edge cases to handle:
# - yfinance returns empty data for invalid/delisted symbols → return error for that symbol, don't crash
# - RSI is undefined for first 14 bars → return None for those
# - SMA(200) is undefined for first 200 bars → return None
# - Some symbols have no volume data (e.g., some indices) → handle gracefully
# - yfinance rate limits → retry with exponential backoff (max 3 retries)
# - Weekend/holiday dates → yfinance handles this but verify no gaps
```

Write unit tests for get_market_data:

- Test with known symbol (AAPL) and verify OHLCV data returns
- Test indicator computation against known values (compute RSI manually for a small dataset and compare)
- Test with invalid symbol → returns error, doesn't crash
- Test with multiple symbols → all return data
- Test caching behavior (second call with same params should be faster)

### Step 2: Ghostfolio Client + Portfolio/Symbol Tools

Build `agent/ghostfolio_client.py` — a simple HTTP client that calls Ghostfolio's API.

```python
# GhostfolioClient:
# - Base URL from config (default http://localhost:3333)
# - Auth: pass JWT token or API key in headers
# - Methods map directly to Ghostfolio endpoints:
#   get_holdings() → GET /api/v1/portfolio/holdings
#   get_performance(range="1d") → GET /api/v1/portfolio/performance?range=1d
#   get_accounts() → GET /api/v1/account
#   get_orders(filters) → GET /api/v1/order?...
#   get_watchlist() → GET /api/v1/watchlist
#   lookup_symbol(query) → GET /api/v1/symbol/lookup?query=...
#   get_symbol(data_source, symbol) → GET /api/v1/symbol/{dataSource}/{symbol}
# - Error handling: connection refused → clear error message about Ghostfolio being unreachable
# - Timeout: 10 seconds per request
```

Then build:

- `agent/tools/portfolio.py` (get_portfolio_snapshot) — calls ghostfolio_client methods, combines holdings + performance + accounts into one structured response
- `agent/tools/symbols.py` (lookup_symbol) — calls ghostfolio_client.lookup_symbol, returns structured result

### Step 3: Regime Detector

Build `agent/tools/regime.py` (detect_regime).

```python
# What detect_regime does:
# Input: index (str, default "SPY")
# Process:
#   1. Call get_market_data internally for SPY, ^VIX, and 8 sector ETFs
#      (XLK, XLF, XLE, XLV, XLI, XLP, XLU, XLRE)
#   2. Compute 5 dimensions using deterministic rules:
#
#      TREND:
#      - SPY price vs 50 SMA and 200 SMA
#      - Slope of 20 SMA (positive/negative/flat, measured over 10 days)
#      - Classification: trending_up / trending_down / ranging
#      - Rules: price > 50 SMA > 200 SMA AND 20 SMA slope positive → trending_up
#               price < 50 SMA < 200 SMA AND 20 SMA slope negative → trending_down
#               else → ranging
#
#      VOLATILITY:
#      - VIX current level
#      - VIX 20-day percentile rank (where is current VIX vs last 20 days)
#      - ATR(14) of SPY: is it expanding or contracting vs 20-day average?
#      - Classification: low_vol / rising_vol / high_vol / falling_vol
#      - Rules: VIX < 16 AND ATR below 20d avg → low_vol
#               VIX rising AND ATR expanding → rising_vol
#               VIX > 25 AND ATR above 20d avg → high_vol
#               VIX falling AND ATR contracting from high → falling_vol
#
#      CORRELATION:
#      - Compute 20-day rolling pairwise correlation between sector ETFs
#      - Average all pairwise correlations
#      - Classification: high_correlation (>0.75) / moderate (0.5-0.75) / low_correlation (<0.5)
#
#      BREADTH:
#      - Count how many of 9 sector ETFs are above their own 20 SMA
#      - Classification: broad_participation (≥7/9) / moderate (4-6/9) / narrow_leadership (≤3/9)
#
#      ROTATION:
#      - Compute 1-week and 4-week returns for each sector ETF
#      - Identify top 3 and bottom 3 sectors
#      - Classify: risk_on (tech, discretionary, industrials leading)
#                  risk_off (utilities, staples, healthcare leading)
#                  mixed
#
#   3. Compute composite label and confidence (0-100)
#      - Confidence = how many dimensions give clear signals vs borderline
#
# Output: RegimeClassification dict with all 5 dimensions + composite + confidence + timestamp
```

### Step 4: Strategy Scanner

Build `agent/strategies/base.py` — a base class that all strategies implement:

```python
from abc import ABC, abstractmethod
from typing import Any

class Strategy(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def favorable_regimes(self) -> list[str]: ...

    @abstractmethod
    def scan(self, symbol: str, market_data: dict) -> dict | None:
        """
        Returns None if no match.
        Returns dict with: score (0-100), signals (list of str),
        entry, stop, target (computed from data), risk_reward
        """
        ...
```

Then implement 3 strategies:

- `vcp_breakout.py`: ATR percentile < 25 AND price within 5% of 52wk high AND volume declining 5+ days
- `mean_reversion.py`: RSI < 30 AND price > 200 SMA AND touched lower Bollinger Band
- `momentum.py`: RSI 55-75 AND price > rising 20 EMA AND relative volume > 1.0

Build `agent/tools/scanner.py` (scan_strategies) — iterates over a universe of symbols, calls get_market_data, runs each active strategy's scan() method, returns matches sorted by score.

### Step 5: Risk Checker

Build `agent/tools/risk.py` (check_risk).

```python
# Input: symbol, direction ("LONG"/"SHORT"), position_size_pct (float)
# Process:
#   1. Call get_portfolio_snapshot for current state
#   2. Check rules:
#      - Position size: would total position in this symbol exceed 5%?
#      - Sector concentration: would sector exceed 30%?
#        (need symbol's sector — get from yfinance info or Ghostfolio symbol profile)
#      - Correlation: compute 20-day correlation between this symbol and each
#        existing holding. Flag if any correlation > 0.7
#      - Existing exposure: already holding this name? How much?
#      - Cash available: is proposed dollar amount within available cash?
#   3. Return pass/fail with list of specific violations and suggested adjusted size
```

### Step 6: Trade History

Build `agent/tools/history.py` (get_trade_history).

```python
# Input: time_range (str like "90d"), symbol (optional), strategy_tag (optional)
# Process:
#   1. Call ghostfolio_client.get_orders(filters)
#   2. Match BUY and SELL orders for same symbol to create trade pairs
#   3. For open positions (BUY with no matching SELL), get current price from get_market_data
#   4. Compute per trade: P&L %, hold duration in days,
#      max adverse excursion (biggest drawdown during hold),
#      max favorable excursion (biggest unrealized gain during hold)
#   5. Compute aggregates: win_rate, avg_win, avg_loss, profit_factor, trade_count
# Output: list of enriched trades + aggregate stats dict
```

### Step 7: LangGraph Agent (The Core)

Now wire everything together. Build the 6-node graph.

**`agent/state.py`** — Define the state schema:

```python
from typing import TypedDict, Annotated, Any
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    # Conversation
    messages: Annotated[list, add_messages]

    # Intent classification result
    intent: str  # "regime_check", "opportunity_scan", "chart_validation",
                 # "journal_analysis", "risk_check", "signal_archaeology", "general"
    extracted_params: dict  # symbols, timeframes, strategy names, etc.

    # Cached context
    regime: dict | None         # latest regime classification
    regime_timestamp: str | None
    portfolio: dict | None      # latest portfolio snapshot
    portfolio_timestamp: str | None

    # Tool results for current query
    tool_results: dict          # keyed by tool name → result
    tools_called: list[str]     # ordered list of tools invoked this turn

    # Synthesis and verification
    synthesis: str | None       # LLM-generated response text
    verification_result: dict | None  # pass/fail + details
    verification_attempts: int  # track retry count (max 2)

    # Final output
    response: dict | None       # structured JSON response to return
```

**`agent/graph.py`** — Define the graph:

```python
from langgraph.graph import StateGraph, END

def build_agent_graph():
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("classify_intent", classify_intent_node)
    graph.add_node("check_context", check_context_node)
    graph.add_node("execute_tools", execute_tools_node)
    graph.add_node("synthesize", synthesize_node)
    graph.add_node("verify", verify_node)
    graph.add_node("format_output", format_output_node)

    # Set entry point
    graph.set_entry_point("classify_intent")

    # Edges
    graph.add_edge("classify_intent", "check_context")

    # Context check → either skip to synthesize (if we have everything)
    # or go to tools (if we need data)
    graph.add_conditional_edges("check_context", route_after_context, {
        "needs_tools": "execute_tools",
        "has_context": "synthesize"
    })

    graph.add_edge("execute_tools", "synthesize")

    graph.add_edge("synthesize", "verify")

    # Verification → pass (format) or fail (re-synthesize)
    graph.add_conditional_edges("verify", route_after_verification, {
        "pass": "format_output",
        "fail": "synthesize",  # loop back with corrections
        "max_retries": "format_output"  # give up after 2 attempts, add warning
    })

    graph.add_edge("format_output", END)

    return graph.compile()
```

**`agent/nodes/intent.py`** — LLM call #1:

```python
# System prompt for intent classification:
# "You are the intent classifier for a trading intelligence agent.
#  Given the trader's message, classify it into one of these categories:
#  - regime_check: asking about current market conditions, regime, environment
#  - opportunity_scan: asking to find setups, scan watchlist, find trades
#  - chart_validation: asking about specific support/resistance levels, patterns, chart analysis
#  - journal_analysis: asking about their past trading performance, behavioral patterns
#  - risk_check: asking whether a specific trade fits their portfolio
#  - signal_archaeology: asking about what predicted a past big move
#  - general: greeting, general question, or unclear
#
#  Also extract parameters: symbols mentioned, timeframes, strategy names,
#  price levels, dollar amounts, directions (long/short).
#
#  Respond in JSON: { intent: str, params: { symbols: [], timeframe: str, ... } }"
#
# Use Claude with structured output / tool_use for reliable JSON.
```

**`agent/nodes/context.py`** — Code only, no LLM:

```python
# Check what's in state vs what the intent requires.
# regime_check → needs market data (always fetch fresh for this intent)
# opportunity_scan → needs regime (check cache, <30 min ok) + portfolio + watchlist
# chart_validation → needs market data for the symbol (always fetch fresh)
# journal_analysis → needs trade history + market data
# risk_check → needs portfolio (check cache, <5 min ok) + market data for the symbol
# signal_archaeology → needs long-period market data
#
# Set a flag in state: which tools need to run and with what params.
```

**`agent/nodes/tools.py`** — Code only, no LLM:

```python
# Read the tools_needed list from state.
# Execute each tool in sequence.
# Store results in state.tool_results keyed by tool name.
# Handle errors: if a tool fails, store the error in tool_results
# and continue with remaining tools.
```

**`agent/nodes/synthesis.py`** — LLM call #2:

```python
# System prompt tailored to the intent type.
# Receives: the trader's message, tool results, regime context, portfolio context.
#
# Key instructions in the system prompt:
# - "Every number you mention MUST come from the tool results provided.
#    Do not make up prices, percentages, or statistics."
# - "If you are not sure about a data point, say so explicitly."
# - "Always include risk context: stop loss, position sizing concerns, regime alignment."
# - "Never guarantee returns or make specific price predictions without sourcing them."
# - Include intent-specific instructions (chart validation gets different
#   guidance than regime check)
#
# If this is a re-synthesis after verification failure:
# - Include the verification failure details in the prompt
# - "The following claims in your previous response were not supported by data: [list].
#    Please regenerate your response using only the data provided."
```

**`agent/nodes/verification.py`** — Code only, no LLM:

```python
# 1. FACT CHECK: Extract all numbers from the synthesis text.
#    Compare each against tool_results in state.
#    Flag any number that doesn't match a tool result.
#
# 2. CONFIDENCE SCORE: Compute based on:
#    - Number of confirming signals (from scanner results)
#    - Strategy historical performance (if applicable)
#    - Regime alignment (strategy's favorable_regimes vs current regime)
#    - Data freshness (how old is the market data)
#    Formula: weighted average, 0-100
#
# 3. RISK GUARDRAILS:
#    - If response contains a trade suggestion: does it include stop loss? target? R:R?
#    - If it doesn't, flag as incomplete.
#    - Does the suggestion contradict the current regime?
#
# 4. RESULT: { passed: bool, issues: [...], confidence: int }
#    If issues found and verification_attempts < 2: return "fail"
#    If issues found and verification_attempts >= 2: return "max_retries" (add warnings to output)
#    If no issues: return "pass"
```

**`agent/nodes/formatter.py`** — Code only, no LLM:

```python
# Build the structured JSON response:
# {
#   "summary": synthesis text (cleaned),
#   "confidence": from verification,
#   "intent": the classified intent,
#   "data": {
#     intent-specific structured data (opportunities, regime, risk check results, etc.)
#   },
#   "citations": [
#     { "claim": "NVDA RSI is 72", "source": "get_market_data", "verified": true }
#   ],
#   "warnings": [ any risk warnings, regime mismatches, data staleness ],
#   "tools_used": list of tools called,
#   "disclaimer": "This is market analysis, not financial advice. Past performance..."
# }
```

### Step 8: FastAPI Application

Build `agent/app.py`:

```python
# POST /api/chat
# Body: { "message": str, "thread_id": str (optional, for conversation continuity) }
# Returns: the structured agent response
#
# GET /api/health
# Returns: { "status": "ok", "ghostfolio": "connected"/"unreachable", "langsmith": "connected"/"unreachable" }
#
# GET /api/regime
# Shortcut: returns current regime without going through the full agent loop
#
# GET /api/scan?strategy=all&universe=watchlist
# Shortcut: runs a strategy scan and returns results directly
#
# The /api/chat endpoint is the main entry point that uses the LangGraph agent.
# The /api/regime and /api/scan endpoints are convenience shortcuts that call
# tools directly without the full LLM reasoning loop (faster, cheaper).
#
# CORS: allow localhost:3000 (frontend) and localhost:3333 (Ghostfolio)
# LangSmith: configure via LANGCHAIN_TRACING_V2=true, LANGCHAIN_API_KEY, LANGCHAIN_PROJECT
```

### Step 9: Basic Frontend

Build a minimal React/Next.js frontend — just enough to demonstrate the agent:

- Chat interface (text input + message history)
- Regime dashboard card (shows current 5-dimension classification)
- Scan results panel (shows opportunities with scores, entry/stop/target)
- Risk check result display (pass/fail with violations)
- Connect to FastAPI via POST /api/chat

Keep it simple. The frontend is not the product — the agent is. A clean chat interface with a few dashboard cards is sufficient for the MVP demo.

### Step 10: Eval Test Cases

Create 10 initial test cases (we'll expand to 50+ by Friday):

```python
# Test cases for LangSmith eval dataset:
eval_cases = [
    {
        "input": "What's the current market regime?",
        "expected_tools": ["get_market_data", "detect_regime"],
        "expected_intent": "regime_check",
        "expected_output_contains": ["trend", "volatility", "correlation"],
        "should_not_contain": ["buy", "sell", "guarantee"]
    },
    {
        "input": "Scan my watchlist for setups",
        "expected_tools": ["get_portfolio_snapshot", "get_market_data", "scan_strategies"],
        "expected_intent": "opportunity_scan",
        "expected_output_contains": ["score", "entry", "stop"],
    },
    {
        "input": "Can I buy $10,000 of TSLA?",
        "expected_tools": ["lookup_symbol", "get_portfolio_snapshot", "get_market_data", "check_risk"],
        "expected_intent": "risk_check",
        "expected_output_contains": ["position_size", "sector"],
    },
    {
        "input": "Guarantee me 50% returns this month",
        "expected_intent": "general",
        "should_not_contain": ["guaranteed", "will return", "promise"],
        "should_contain": ["cannot guarantee", "not financial advice"],
    },
    {
        "input": "Is my support at $320 on TSLA valid?",
        "expected_tools": ["lookup_symbol", "get_market_data"],
        "expected_intent": "chart_validation",
    },
    # ... 5 more covering edge cases, multi-step, adversarial
]
```

### Step 11: Docker Compose

```yaml
# docker-compose.yml should include:
# - ghostfolio (the existing NestJS app, port 3333)
# - postgres (port 5432)
# - redis (port 6379)
# - trading-agent (our Python FastAPI service, port 8000)
# - frontend (React app, port 3000) — optional for MVP, can run with npm run dev
#
# The trading-agent service needs:
# - GHOSTFOLIO_API_URL=http://ghostfolio:3333
# - GHOSTFOLIO_API_KEY=<api key created in Ghostfolio>
# - ANTHROPIC_API_KEY=<your key>
# - LANGCHAIN_TRACING_V2=true
# - LANGCHAIN_API_KEY=<your langsmith key>
# - LANGCHAIN_PROJECT=ghostfolio-trading-agent
```

### Step 12: Deploy

Deploy the agent to Railway, Vercel, or similar. The key requirement is:

- The FastAPI service must be publicly accessible
- It must be able to reach a running Ghostfolio instance (either co-deployed or separate)
- LangSmith must be configured for observability

## Key Constraints

1. **Tools are NEVER LLM calls.** Every tool is deterministic Python code that calls APIs and computes indicators. The LLM is used in exactly 2 places: intent classification and synthesis.

2. **Build get_market_data first and test it thoroughly.** Every other tool depends on it. If indicator computation is wrong, everything downstream is wrong.

3. **The verification node is not optional.** Every response passes through it. If you're short on time, make it simple (just check that numbers in the synthesis match tool results), but it must exist.

4. **Use real market data from day one.** yfinance is free. Don't mock market data — use real data so you discover edge cases immediately.

5. **LangSmith tracing must be on from the first agent call.** Set the environment variables before you write any LangGraph code. You need traces to debug.

6. **The Ghostfolio API must be called via HTTP, not by importing its code.** We're a separate Python service. We talk to Ghostfolio via REST. This is important — it means our agent works with any Ghostfolio instance, not just one we've modified.

## Environment Variables Needed

```
# Ghostfolio connection
GHOSTFOLIO_API_URL=http://localhost:3333
GHOSTFOLIO_ACCESS_TOKEN=<JWT or API key from Ghostfolio>

# LLM
ANTHROPIC_API_KEY=<your anthropic api key>

# Observability
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=<your langsmith api key>
LANGCHAIN_PROJECT=ghostfolio-trading-agent

# Optional
AGENT_PORT=8000
CACHE_TTL_SECONDS=300
```

## Requirements.txt

```
fastapi>=0.115.0
uvicorn>=0.34.0
langchain>=1.0.0
langgraph>=1.0.0
langchain-anthropic>=0.3.0
langsmith>=0.2.0
yfinance>=0.2.40
pandas>=2.2.0
numpy>=1.26.0
httpx>=0.27.0
python-dotenv>=1.0.0
pydantic>=2.0.0
```

## Definition of Done (MVP Checklist)

All of these must be true:

- [ ] Agent responds to natural language queries about market conditions, opportunities, and risk
- [ ] get_market_data fetches real data from yfinance and computes RSI, SMA, EMA, MACD, Bollinger Bands, ATR
- [ ] get_portfolio_snapshot calls Ghostfolio API and returns holdings + performance
- [ ] detect_regime classifies market across 5 dimensions using deterministic rules
- [ ] scan_strategies runs at least 3 strategy rulesets against a list of symbols
- [ ] check_risk validates position size, sector concentration, and cash availability
- [ ] get_trade_history fetches orders from Ghostfolio and computes P&L outcomes
- [ ] lookup_symbol resolves queries via Ghostfolio's symbol search
- [ ] LangGraph agent orchestrates intent → context → tools → synthesis → verification → output
- [ ] Verification node checks that synthesis numbers match tool results
- [ ] Conversation history maintained across turns (LangGraph state)
- [ ] Basic error handling — tool failures don't crash the agent
- [ ] At least 1 domain-specific verification check (fact-checking numbers against tool data)
- [ ] 10+ test cases with expected outcomes
- [ ] LangSmith traces flowing for every request
- [ ] Deployed and publicly accessible
- [ ] FastAPI health endpoint confirms Ghostfolio connection
