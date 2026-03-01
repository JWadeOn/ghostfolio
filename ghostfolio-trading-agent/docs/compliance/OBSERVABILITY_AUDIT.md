# Observability Audit

> Last updated: 2026-02-28

## Status: All 6 capabilities implemented

---

## 1. Trace Logging

**Status:** Implemented
**Files:** `agent/observability.py` (make_trace_entry), all node files
**State field:** `trace_log` (list of dicts)

**Coverage:**

- `react_agent.py` — logs tool calls, final answers, input/output summaries per ReAct step
- `tools.py` — logs tool execution with timing metadata
- `synthesis.py` — logs synthesis LLM calls with intent and tool list
- `verification.py` — logs verification results with passed/issues/confidence
- `formatter.py` — logs output formatting

**Entry format:**

```python
{
    "timestamp": "ISO8601",
    "node": "react_agent_0",
    "input": "...",           # first 500 chars
    "output": "...",          # first 500 chars
    "metadata": {...}         # tool calls, timings
}
```

**Output path:** `response.observability.trace_log`

---

## 2. Latency Tracking

**Status:** Implemented (multi-level)
**Files:** `agent/observability.py` (track_latency), all node files
**State field:** `node_latencies` (dict)

**Breakdown:**
| Level | Key Format | Where |
|-------|-----------|-------|
| Per-LLM call | `react_agent_N` | react*agent.py |
| Per-tool | `tool*{name}\_{step}`| tools.py |
| Per-synthesis |`synthesize_N`| synthesis.py |
| Per-verification |`verify_N`| verification.py |
| Formatting |`format_output` | formatter.py |
| Total request | computed | app.py |

**Precision:** 4 decimal places (0.0001s)
**Output path:** `response.observability.node_latencies`

---

## 3. Error Tracking

**Status:** Implemented (structured, categorized)
**Files:** `agent/observability.py` (ErrorCategory, make_error_entry)
**State field:** `error_log` (list of dicts)

**6 Error Categories:**

```
LLM, TOOL, VALIDATION, PARSE, NETWORK, UNKNOWN
```

**Entry format:**

```python
{
    "timestamp": "ISO8601",
    "node": "react_agent_0",
    "category": "tool_error",
    "error": "str(exception)",
    "error_type": "ExceptionClassName",
    "stacktrace": [...],         # last 3 frames
    "context": {...}             # tool name, additional info
}
```

**Capture points:** react_agent.py (LLM errors), tools.py (tool errors), synthesis.py (synthesis errors)
**Output path:** `response.observability.error_log`

---

## 4. Token Usage

**Status:** Implemented (with cost estimation)
**Files:** `agent/observability.py` (extract_token_usage, aggregate_token_usage)
**State field:** `token_usage` (dict keyed by node)

**Tracking points:**

- ReAct LLM calls: per `react_agent_N` key
- Synthesis LLM calls: per `synthesize_N` key
- Aggregated in formatter with model-specific pricing

**Cost calculation:**

```python
MODEL_PRICING = {
    "claude-sonnet-4-20250514": (3.00, 15.00),  # per 1M tokens
    "claude-haiku-4-5": (1.00, 5.00),
}
```

**Aggregate format:**

```python
{
    "input_tokens": int,
    "output_tokens": int,
    "total_tokens": int,
    "estimated_cost_usd": float
}
```

**Output path:** `response.observability.token_usage.total`

---

## 5. Eval Results & Regression Detection

**Status:** Implemented (multi-tier)
**Files:** `tests/eval/run_evals.py`

**Storage:** JSON files in `reports/`

```
reports/
├── eval-results-{timestamp}.json      # dataset layer
├── golden-results-{timestamp}.json    # golden set
└── scenario-results-{timestamp}.json  # scenarios
```

**Regression detection:**

```python
get_previous_pass_rate(reports_dir) → float | None  # reads most recent report
check_regression(current, previous) → float | None  # returns delta
```

**LangSmith integration:** Auto-uploads to `ghostfolio-trading-agent-evals` dataset when API key is set.

---

## 6. User Feedback

**Status:** Implemented (basic) — **backend only; no UI**
**Files:** `agent/app.py` (lines 263-318)

**Endpoints:**

- `POST /api/feedback` — submit feedback
- `GET /api/feedback/summary` — aggregate stats

**Feedback structure:**

```python
{
    "thread_id": str,
    "rating": "thumbs_up" | "thumbs_down",
    "correction": str | None,
    "comment": str | None,
    "timestamp": "ISO8601"
}
```

**Storage:** `data/feedback/{thread_id}_{timestamp}.json`
**Summary:** total, thumbs_up, thumbs_down, with_corrections

**Where it should be visible (not yet implemented):**

- **Location:** Trading Assistant page (`apps/client/.../trading-agent-page`), on each **assistant** message row — e.g. thumbs up / thumbs down buttons (and optionally “Add correction” or a short comment field).
- **Flow:** User rates a response → client sends `POST /api/feedback` with current `thread_id`, `rating`, and optional `correction`/`comment`. The Ghostfolio API does not yet proxy this endpoint; the client would need to call it via a new API route (e.g. `POST /api/v1/trading-agent/feedback`) that forwards to the agent’s `POST /api/feedback`.
- **Usage:** Thumbs up = response was helpful; thumbs down = not helpful, with optional correction text to improve future answers. Summary (`GET /api/feedback/summary`) is for admins/analytics, not shown in the main chat UI by default.

---

## Data Flow

```
Agent Execution
    ↓
AgentState accumulates: trace_log, node_latencies, error_log, token_usage
    ↓
formatter.py embeds into response.observability
    ↓
app.py returns in API response
    ↓
Eval runners capture in reports/*.json
    ↓
LangSmith (optional) for experiment tracking
```
