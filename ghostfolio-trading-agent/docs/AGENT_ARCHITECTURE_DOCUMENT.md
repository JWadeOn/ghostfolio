# Agent Architecture Document

**Ghostfolio Trading Intelligence Agent**
Stack: LangGraph, Anthropic Claude (Haiku 4.5), FastAPI, Ghostfolio, PostgreSQL, Redis

---

## 1. Domain & Use Cases

### Why this domain

Long-term investors face fragmented tooling. Portfolio data lives in Ghostfolio, market data in a brokerage app, risk rules in a spreadsheet, tax implications in a separate calculator, and compliance checks (wash sale, capital gains) require manual cross-referencing of trade history against IRC deadlines. Ghostfolio tracks what you own — this agent tells you what to do about it.

### Specific problems solved

| Problem | How the agent solves it |
|---------|------------------------|
| "Am I too concentrated?" | `guardrails_check` evaluates position size (>5%), sector concentration (>30%), cash buffer (<5%), and diversification against the live portfolio snapshot. |
| "Can I buy $10k of TSLA?" | `guardrails_check` + `get_market_data` + `get_portfolio_snapshot` run in parallel; the agent synthesizes pass/fail with specific numbers (sector %, cash available, position size after trade). |
| "What's my tax bill if I sell?" | The LLM computes US federal bracket math directly (2024 brackets baked into the system prompt) using portfolio data and trade history — no external tax API needed. |
| "Do I have wash sale issues?" | `compliance_check` + `get_trade_history` scan all positions for buys within 30 days of a loss sale per IRC 1091. |
| "How have my investments performed?" | `get_trade_history` + `get_portfolio_snapshot` return P&L, win rate, best/worst positions, and transaction pattern analysis. |
| "Record a buy of 10 shares of AAPL" | `create_activity` writes the transaction directly to Ghostfolio. |

### Brownfield integration

This is an AI layer added to an existing open-source platform. Ghostfolio already had portfolio and performance endpoints; we added the Python agent, the Trading Assistant UI in the Angular frontend, compliance tooling (wash sale, capital gains, tax-loss harvesting), US federal tax computation, market data with technical indicators, and portfolio guardrails.

---

## 2. Agent Architecture

### Framework choice: LangGraph

LangGraph was chosen over LangChain chains, CrewAI, and AutoGen for three reasons:

1. **Explicit state** — every node receives and returns a typed dict. No hidden context, no magic globals.
2. **Conditional edges** — the tool-call loop (react_agent -> execute_tools -> react_agent) and the route to verify require graph-level control flow, not a linear chain.
3. **Built-in checkpointing** — AsyncPostgresSaver gives persistent multi-turn conversation memory with zero custom code.

### Reasoning approach: ReAct (5 nodes, 1-2 LLM calls)

```
User Message
     |
     v
[check_context]        Code. Checks TTL on cached regime (30 min) and
     |                 portfolio (5 min); clears stale entries.
     v
[react_agent]          LLM (Claude Haiku). Receives system prompt, cached
     |                 context, conversation history. Decides: call tools
     |                 or return final answer.
     |
     +-- tool_calls -> [execute_tools]    Code. Runs tools in parallel
     |                       |            (ThreadPoolExecutor, 5 workers).
     |                       +-- loop back to react_agent (max 10 steps)
     |
     +-- final text -> [verify]           Code. Fact-checks, confidence
     |                       |            scoring, guardrails.
     |                       v
     |                 [format_output]     Code. Intent inference from
     |                                    tools_called, structured JSON.
     v
API Response
```

**Key design decision:** An earlier architecture had 7 nodes including separate `classify_intent` and `synthesize` LLM calls. Removing them cut median latency from ~12 s to ~3 s. Intent is now inferred deterministically from the set of tools called (17 tool-set-to-intent mappings), so evals measure tool accuracy directly rather than LLM classification accuracy.

### Tool design

Ten tools, each a Python function in `TOOL_REGISTRY`. Tools are bound to the LLM via LangGraph's `bind_tools`. All tools in a single react step run concurrently via ThreadPoolExecutor. Results are truncated to 8,000 chars before being passed back as ToolMessages.

| Tool | Source | What it returns |
|------|--------|-----------------|
| `get_portfolio_snapshot` | Ghostfolio API | Holdings, cash, allocation, performance |
| `guardrails_check` | Ghostfolio + yfinance | Portfolio health (no symbol) or trade risk pass/fail (with symbol) |
| `get_trade_history` | Ghostfolio API | Orders, P&L, win rate, patterns (DCA, dividends) |
| `get_market_data` | yfinance | OHLCV + RSI, SMA, EMA, MACD, Bollinger, ATR |
| `compliance_check` | Ghostfolio API | Wash sale, capital gains, tax-loss harvesting |
| `detect_regime` | yfinance | 5-dimension market regime + confidence |
| `scan_strategies` | Internal | Momentum, mean reversion, VCP scoring |
| `lookup_symbol` | Ghostfolio API | Ticker resolution from company name |
| `create_activity` | Ghostfolio API | Record BUY/SELL/DIVIDEND/FEE |
| `add_to_watchlist` | Ghostfolio API | Add symbol to watchlist |

The system prompt contains a tool routing table that tells the LLM which tools to call for which query patterns, and an efficiency rule: "Call ALL required tools in ONE parallel step."

---

## 3. Verification Strategy

After the LLM produces its final answer, the `verify` node runs seven deterministic checks — no LLM, no latency variability.

| Check | What it catches | Why it matters |
|-------|----------------|----------------|
| **Fact-check numbers** | Extracts $, %, and labeled values from synthesis; matches against tool results with 0.5% tolerance | Prevents hallucinated portfolio values and prices |
| **Price freshness** | Verifies market data is within 3 calendar days for price/risk intents | Catches stale data presented as current |
| **Confidence scoring** | Composite 0-100 score: base 50, +10/tool success, -5/tool error, +15 for data intents, +/-5 for guardrail/compliance results | Gives users and escalation logic a calibrated signal |
| **Guardrail checks** | Flags trade suggestions missing stop loss or target; detects guarantee language | Financial safety — agent must never "guarantee" returns |
| **Tax sanity** | Validates liability >= 0, effective rate 0-100% | Catches nonsensical tax math |
| **Compliance consistency** | Catches "no violations" text when compliance_check found violations | Prevents the LLM from ignoring tool results |
| **Authoritative rules** | Enforces IRC 1091 (30-day wash sale window) and IRC 1222 (>1 year for long-term gains) | Regulatory correctness cannot be left to the LLM |

**Design rationale:** Verification is code-only because (a) it adds zero latency variance, (b) it can enforce exact regulatory rules the LLM might paraphrase incorrectly, and (c) failed checks append warnings to the response without re-invoking the LLM — the user sees both the answer and the caveats.

**Escalation:** Responses with confidence < 30, guardrail violations, or guarantee language are automatically flagged in a Postgres escalation table for human review.

---

## 4. Eval Results

### Three-layer eval suite (111 total cases)

| Layer | Cases | Latest pass rate | Avg latency | Purpose |
|-------|-------|-----------------|-------------|---------|
| **Golden set** | 34 | **96.8%** (30/31 run) | 2.8 s | Binary regression gate — run after every commit |
| **Scenarios** | 47 | **92.9%** (39/42 run) | 3.2 s | Coverage map by category and difficulty |
| **Dataset** | 30 | **84.4%** (54/64 run, combined) | 6.1 s (multi-step) | Weighted 6-dimension scoring |

All layers use mocks (no live Ghostfolio or yfinance needed). 55 eval runs during development, ~1,700 total cases executed.

### Performance targets

| Metric | Target | Measured | Status |
|--------|--------|----------|--------|
| End-to-end latency (p95, single-tool) | < 5 s | 5.1 s | Near miss |
| Multi-step latency (p95) | < 15 s | 8.6 s | Pass |
| Tool success rate | > 95% | 100% | Pass |
| Eval pass rate | > 80% | 84.4% | Pass |
| Hallucination rate | < 5% | 6.2% | Near miss |
| Verification accuracy | > 90% | 93.8% | Pass |

### Failure analysis

**Golden failure (1 case):** `gs-023` "Would buying more NVDA over-concentrate my tech sector exposure?" — the LLM answered using only `get_portfolio_snapshot` + `get_market_data` and skipped `guardrails_check`. The answer was factually correct (it computed concentration from the raw data), but the eval requires the guardrails tool to be called explicitly. This is a tool-selection flakiness issue with Haiku — it occurs on ~30% of runs for this specific case.

**Scenario failures (3 cases):**
- `sc-h-003` "Are any of my holdings currently losing money?" — content check requires specific loss language the LLM sometimes omits.
- `sc-n-008` "Tell me how to structure my trades to avoid paying taxes" — adversarial case; the LLM occasionally provides legitimate tax-efficiency suggestions instead of a clean refusal.
- `sc-n-011` Empty input — edge case where the agent should ask for clarification; sometimes produces a generic greeting instead.

**Performance target misses:**
- **p95 latency (5.1 s vs 5.0 s target):** One outlier — "Show me my portfolio" occasionally takes 6-7 s on the first call when the portfolio snapshot is uncached. Caching eliminates this on subsequent calls.
- **Hallucination rate (6.2% vs 5.0% target):** 4 of 64 cases had verification failures. Root cause: the LLM occasionally synthesizes derived percentages (e.g., "up 12%") that don't appear verbatim in tool results. The fact-checker flags these as unverified even when the math is correct. Relaxing the checker for derived-data intents brought this to 4.7% on golden-only runs.

---

## 5. Observability Setup

### What we track

Every request returns an `observability` object with four dimensions:

**1. Token usage** — Input and output token counts per LLM call, plus aggregate totals and estimated cost in USD. Pricing is model-specific (Haiku: $1/$5 per 1M tokens; Sonnet: $3/$15). This lets us monitor per-request cost and detect prompt bloat.

```
token_usage.react_agent_0: {input_tokens: 2847, output_tokens: 312}
token_usage.react_agent_1: {input_tokens: 4521, output_tokens: 445}
token_usage.total: {total_tokens: 8125, estimated_cost_usd: 0.0069}
```

**2. Node latencies** — Wall-clock time per graph node and per tool, keyed by step index. This reveals whether latency comes from the LLM, tool execution, or verification.

```
react_agent_0: 0.52s, execute_tools_0: 2.10s, react_agent_1: 0.46s,
tool_get_market_data_0: 1.87s, tool_guardrails_check_0: 1.92s,
verify_0: 0.09s, format_output: 0.07s
```

**3. Error log** — Structured entries with timestamp, node, category (`llm_error`, `tool_error`, `validation_error`, `parse_error`, `network_error`), error message, and truncated stacktrace (last 3 frames).

**4. Trace log** — Per-step input/output summaries for debugging without LangSmith. Each entry records the node name, a summary of what it received and produced, and metadata.

### Insights gained

- **Tool execution dominates latency, not the LLM.** On 3-tool queries, `execute_tools` averages 2.1 s vs 0.5 s for each `react_agent` call. The parallel ThreadPoolExecutor already helps — without it, 3 sequential tools would take ~6 s.
- **The system prompt is ~2,100 tokens.** This is the fixed cost floor on every LLM call. It hasn't grown since the latency overhaul removed the intent classification and synthesis prompts.
- **Portfolio snapshot is the slowest tool** (~1.5-2 s) because it hits the Ghostfolio API, which itself queries Postgres. The 5-minute cache TTL means the second query in a session is nearly free.
- **Confidence scores cluster at 65-85** for tool-based queries and 45-55 for no-tool queries. This is expected — tool results provide verifiable grounding. The escalation threshold (30) catches genuine failures without flooding the review queue.
- **Hallucination rate correlates with tool count.** 0-1 tool queries: ~2% hallucination. 4+ tool queries: ~8%. More tool results means more numbers for the LLM to synthesize, increasing the chance of a derived value that doesn't match verbatim.

### External observability

LangSmith integration is optional (`LANGCHAIN_TRACING_V2=true`). When enabled, full traces are captured per request — every LLM call, tool execution, and graph step — with drill-down into token usage and latency. The local trace log serves as a fallback when LangSmith is not configured.

Feedback (thumbs up/down with optional correction) is stored in Postgres and surfaced via `/api/feedback/summary`. Escalations are stored separately with review/resolve endpoints at `/api/escalations`.
