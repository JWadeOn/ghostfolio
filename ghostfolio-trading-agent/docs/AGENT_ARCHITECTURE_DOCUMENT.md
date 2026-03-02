# Agent Architecture Document

**Ghostfolio Trading Intelligence Agent**
Stack: LangGraph, Anthropic Claude, FastAPI, Ghostfolio, PostgreSQL, Redis

---

## 1. Overview

The Ghostfolio Trading Agent is a portfolio intelligence assistant that connects to a self-hosted Ghostfolio instance and answers natural-language questions about holdings, risk, taxes, compliance, and market data. It uses a standard ReAct (Reasoning + Acting) loop implemented as a LangGraph state machine with 1-2 LLM calls per request, deterministic verification, and persistent conversation memory.

**Design goals:** sub-5-second latency for simple queries, every number grounded in tool output, no LLM-based intent classification or post-synthesis, and full idempotent re-runability of the seed and eval layers.

---

## 2. ReAct Pipeline

The graph has five nodes. Only one (react_agent) calls the LLM; the rest are code-only.

```
User Message
     |
     v
[check_context]        Code. Checks TTL on cached regime (30 min) and
     |                 portfolio (5 min); clears stale entries.
     v
[react_agent]          LLM (Claude Haiku by default). Receives system prompt,
     |                 cached context, and conversation history. Decides:
     |                 call tools, or return a final answer.
     |
     +-- tool_calls --> [execute_tools]    Code. Runs all requested tools in
     |                       |             parallel (ThreadPoolExecutor, 5 workers).
     |                       |             Injects Ghostfolio client and prior
     |                       |             tool results to avoid redundant calls.
     |                       |
     |                       +-- loop back to react_agent (max 10 steps)
     |
     +-- final text --> [verify]           Code. Fact-checks numbers against
     |                       |             tool output, scores confidence 0-100,
     |                       |             applies domain guardrails.
     |                       v
     |                 [format_output]     Code. Infers intent from tools_called,
     |                                    extracts citations, builds structured
     |                                    AgentResponse JSON.
     v
API Response
```

**Why this shape:** Eliminating separate classify-intent and synthesize nodes cut median latency from ~12 s to ~3 s. Intent is inferred deterministically from the set of tools called (a code-only mapping of 17 tool-set patterns), so evals measure tool accuracy directly.

---

## 3. Tool Registry

Ten core tools, each a Python function registered in `TOOL_REGISTRY` and bound to the LLM via LangGraph's `bind_tools`:

| Tool | Source | Purpose |
|------|--------|---------|
| `get_portfolio_snapshot` | Ghostfolio API | Holdings, cash, allocation, performance |
| `guardrails_check` | Ghostfolio + yfinance | Dual-mode: portfolio health (no symbol) or trade risk evaluation (with symbol, side, amount) |
| `get_trade_history` | Ghostfolio API | Order history, P&L, win rate, transaction patterns |
| `get_market_data` | yfinance | OHLCV + indicators (RSI, SMA, EMA, MACD, Bollinger, ATR) |
| `compliance_check` | Ghostfolio API | Wash sale (IRC 1091), capital gains classification, tax-loss harvesting |
| `detect_regime` | yfinance | 5-dimension market regime (trend, volatility, correlation, breadth, rotation) |
| `scan_strategies` | Internal | Momentum, mean reversion, and VCP breakout scoring with entry/stop/target |
| `lookup_symbol` | Ghostfolio API | Ticker resolution from company name |
| `create_activity` | Ghostfolio API | Record BUY/SELL/DIVIDEND/FEE transactions |
| `add_to_watchlist` | Ghostfolio API | Add symbol to user's watchlist |

**Execution model:** All tools requested in a single react step run concurrently. Results are truncated to 8,000 characters per tool before being passed back to the LLM as ToolMessages.

---

## 4. Verification Layer

After the LLM produces its final answer, `verify` runs seven deterministic checks (no LLM):

1. **Fact-check numbers** - Extracts dollar amounts, percentages, and labeled values from the synthesis, then matches each against tool results with 0.5% tolerance. Skips user-provided inputs and derived-data intents.
2. **Price freshness** - For price_quote and risk_check intents, verifies data is within 3 calendar days or synthesis includes an "as of" disclaimer.
3. **Confidence scoring** - Base 50, +10 per successful tool, -5 per tool error, +15 for data-retrieval intents with successful tools, adjustments for guardrail pass/fail and compliance results. Clamped 0-100.
4. **Guardrail checks** - Flags trade suggestions missing stop loss or target; detects guarantee language ("guaranteed", "100% certain", "can't lose").
5. **Tax sanity** - Validates liability >= 0 and effective rate 0-100%.
6. **Compliance consistency** - Catches contradictions between synthesis text and compliance_check results.
7. **Authoritative rules** - Enforces IRC 1091 (30-day wash sale window) and IRC 1222 (>1 year for long-term gains) against dates and periods mentioned in the synthesis.

Failed checks append warnings to the response but do not re-invoke the LLM. This keeps latency constant while surfacing issues to the user.

---

## 5. Memory and Persistence

**Conversation state** is managed through LangGraph's built-in checkpointing:

- **PostgreSQL (AsyncPostgresSaver):** Stores full state snapshots per `(thread_id, checkpoint_id)` at each graph step. On the next message in a thread, LangGraph automatically loads and merges the checkpoint with the new input. This is the source of truth for multi-turn conversations.
- **Redis (24-hour TTL):** Caches serialized message history at `conv:{thread_id}` for fast retrieval by the `/api/conversation/{thread_id}` endpoint. On cache miss, falls back to the Postgres checkpoint.

**In-graph caching:** Regime and portfolio snapshots are stored in the agent state with timestamps. `check_context` clears entries past their TTL (regime: 30 min, portfolio: 5 min) so subsequent tool calls fetch fresh data only when needed.

**Feedback and escalation** are stored in dedicated Postgres tables. Responses with confidence below the threshold (default 40), guardrail violations, or guarantee language are automatically flagged as escalations for human review.

---

## 6. Orchestration and Data Flow

A concrete example illustrates the full pipeline:

**Query:** "Can I buy $10k of NVDA without over-concentrating tech?"

1. `check_context` clears stale cache entries.
2. `react_agent` (LLM call 1) reads the query and calls three tools in parallel: `guardrails_check(symbol="NVDA", side="buy", dollar_amount=10000)`, `get_portfolio_snapshot()`, `get_market_data(["NVDA"])`.
3. `execute_tools` runs all three concurrently (~1-2 s). Guardrails returns a sector concentration violation; portfolio returns current holdings; market data returns NVDA's price and indicators.
4. `react_agent` (LLM call 2) reads the three ToolMessages and generates: "You cannot add $10k of NVDA. Tech is already 35% of your portfolio, exceeding the 30% sector cap..."
5. `verify` fact-checks "35%" against the guardrails result (match), scores confidence at 75, finds no guardrail or compliance issues.
6. `format_output` infers intent as `risk_check` from the tool set, extracts citations, and builds the final AgentResponse with summary, confidence, data, warnings, tools_used, and disclaimer.

**Total wall time:** ~3 seconds (2 LLM calls + 1 parallel tool batch + code nodes).

---

## 7. System Prompt Design

The react_agent receives a structured system prompt that encodes:

- **When to clarify vs. act:** Single-word commands or missing required parameters (e.g., tax estimate without income) trigger clarification. Everything else goes straight to tools.
- **Tool routing table:** Maps query patterns to tool combinations (e.g., "investment evaluation" triggers portfolio snapshot + market data + guardrails).
- **Efficiency rule:** "Call ALL required tools in ONE parallel step."
- **Response format:** Concise paragraphs, exact numbers from tools, "as of [date]" for prices, mandatory disclaimers for tax and financial content.
- **Safety rules:** No guarantee language, refusal for harmful requests, generic refusal for prompt injection.
- **Authoritative sources:** When tools are called, regulatory excerpts (IRC 1091, IRC 1222) are appended to the prompt to ground the LLM.

---

## 8. Observability

Every request produces four observability dimensions returned in the API response:

- **Token usage:** Input/output counts and estimated cost per LLM call, aggregated across the request.
- **Node latencies:** Per-node and per-tool timing (e.g., `react_agent_0: 1.23s`, `tool_get_market_data_0: 0.87s`).
- **Error log:** Structured entries with timestamp, node, category (llm_error, tool_error, validation_error, etc.), and truncated stacktrace.
- **Trace log:** Per-step summaries of input/output for debugging without external tooling.

Optional LangSmith integration captures full traces when `LANGCHAIN_TRACING_V2=true`.

---

## 9. Evaluation

Three eval layers validate correctness at different granularities:

| Layer | Cases | Purpose | Gate |
|-------|-------|---------|------|
| Golden set | 34 | Regression gate (7 check dimensions, binary pass/fail) | Every commit |
| Scenarios | 47 | Coverage map across query types and difficulty tiers | Before PRs |
| Dataset | 30 | Weighted scoring (intent, tools, content, safety, confidence, verification) | CI gate |

All layers use mocks by default (no live Ghostfolio or yfinance needed; Anthropic API key required). Performance targets: pass rate >= 80%, tool success rate >= 95%, hallucination rate < 5%.
