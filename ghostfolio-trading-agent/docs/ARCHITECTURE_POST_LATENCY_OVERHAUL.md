# Architecture Snapshot: Post–Latency Overhaul

**Purpose:** Historical reference and architecture knowledge. This document captures how the trading agent system works after the latency overhaul and related architecture changes (standard ReAct pipeline, code-only intent inference, updated golden cases and labeled scenarios). It is intended for onboarding and for understanding design decisions without re-reading the full plan or commit history.

**Snapshot date:** 2025-02-28 (approximate). Plan reference: `latency_overhaul_and_requirements_d8f6c417.plan.md`.

---

## 1. Architecture: Standard ReAct (1–2 LLM Calls)

**Before (plan):** The pipeline used four sequential LLM calls: `classify_intent` → `check_context` → `react_agent` → `execute_tools` → `react_agent` → `synthesize` → `verify` → `format_output`. Latency was 7–22s for single-tool and 21–44s for multi-step, missing targets (<5s and <15s).

**Now (implemented in `agent/graph.py`):**

- **Entry:** `check_context` (no LLM).
- **Core loop:** `react_agent` ↔ `execute_tools`. If the agent emits tool calls → go to `execute_tools`, then back to `react_agent`. If the agent returns a final answer (no tools) → go to `verify`.
- **Exit:** `verify` → `format_output` → `END`.

So:

- **0-tool:** 1 LLM call (react answers directly).
- **1+ tool:** 2 LLM calls (first react calls tools, second react reads results and answers).

`classify_intent` and `synthesize` are removed; the react agent’s final answer **is** the user-facing response. This matches the “New pipeline” in the plan.

---

## 2. Intent: Code-Only Inference (No Extra LLM)

Intent is no longer from a separate LLM node. It’s inferred **after** the run from `tools_called` in `agent/nodes/formatter.py` via `infer_intent_from_tools()` and a `TOOL_TO_INTENT` mapping (e.g. `trade_guardrails_check` → `risk_check`, `get_portfolio_snapshot` + `portfolio_guardrails_check` → `portfolio_health`). That inferred intent is used by:

- **Verification** (`agent/nodes/verification.py`) for intent-aware fact-checking.
- **Formatter** (`agent/nodes/formatter.py`) for structured output and metadata.
- **Evals** (`tests/eval/run_evals.py`) so “intent score” effectively measures **tool selection accuracy** (did the agent call the right tools for the query).

No extra latency; all from tool-call history.

---

## 3. Model and Observability

- **Config** (`agent/config.py`): `agent_model` (default `claude-haiku-4-5`) is configurable via `AGENT_MODEL` so you can swap to Sonnet for quality if needed.
- **Observability:** Per-model token cost in `agent/observability.py`; node latencies fixed (manual timing before returning in `react_agent.py` and `tools.py` per plan Phase 1).
- **Eval aggregates** (`tests/eval/run_evals.py`): `aggregate_results()` now reports **tool_success_rate_pct**, **hallucination_rate_pct**, and **verification_accuracy_pct** so you can track >95% tool success, <5% hallucination, >90% verification as in the plan.

---

## 4. Verification and Formatting

- **Verify** runs on the react agent’s final text; uses inferred intent; on failure it adds warnings in code rather than re-routing to a synthesis LLM.
- **Format** builds the final JSON (citations, confidence, warnings, disclaimer) using the same inferred intent. Synthesis-style rules (“every number from tool results”, “not financial advice”, no “promise”) are merged into the react agent’s system prompt so a single model pass produces a compliant answer.

---

## 5. Evals: Golden Set, Labeled Scenarios, and Full Eval Suite

- **Golden set** (`tests/eval/golden_cases.py`): 25 curated cases — 11 happy path (one per major tool), 5 edge, 5 adversarial, 4 multi-step (+ 1 single-tool compliance). Each case specifies `expected_tools`, `expected_output_contains` / `should_not_contain`, and optional `ground_truth_contains`. Run with `python3 tests/eval/run_golden.py` (optionally `--id gs-XXX`). Used for post-commit, deterministic checks.
- **Labeled scenarios** (`tests/eval/scenarios.py` + `run_scenarios.py`): Cases grouped by **category** (single_tool, multi_tool, no_tool), **subcategory** (e.g. portfolio, market_data, adversarial), and **difficulty** (straightforward, ambiguous, adversarial, edge_case). Run e.g. `--category single_tool` or `--subcategory portfolio` to see coverage and regressions by area.
- **Full eval suite** (`tests/eval/dataset.py` + `run_evals.py`): Larger set (69+ cases in dataset, Phase 1 vs Phase 2). Uses inferred intent for scoring; produces pass rate, per-case scores (intent/tools/content/safety/confidence/verification), latencies, and the aggregate metrics above. Reports written to `reports/`; optional LangSmith experiments.

---

## 6. End-to-End Flow (Single Query) — Summary

1. Request hits API → state prepared (e.g. conversation, context).
2. **check_context** runs (TTL/cache, no LLM).
3. **react_agent** runs (Haiku by default): either calls tools or returns final answer.
4. If tools: **execute_tools** runs → back to **react_agent** with tool results → react produces final answer.
5. **verify** runs on that answer (fact-check, hallucination, etc.) using inferred intent; appends warnings if needed.
6. **format_output** infers intent from `tools_called`, builds JSON response.
7. Eval pipelines (golden, scenarios, or full run_evals) score tool choice, content, safety, and optionally latency against the same inferred intent and aggregate metrics.

---

## 7. Detailed End-to-End Flow (Shapes, Routes, Code vs LLM)

### AgentState shape (reference)

All nodes read and return **partial updates** to this state (LangGraph merges them; `messages` uses `add_messages` so new messages are appended):

```text
AgentState = {
  messages: list[HumanMessage | AIMessage | ToolMessage],   # conversation + ReAct turns
  intent: str,                                               # set only by formatter (inferred)
  extracted_params: dict,
  regime: dict | None,
  regime_timestamp: str | None,
  portfolio: dict | None,
  portfolio_timestamp: str | None,
  ghostfolio_access_token: str | None,
  tool_results: dict,                                        # tool_name -> result
  tools_called: list[str],
  react_step: int,                                           # 0, 1, 2, ...
  synthesis: str | None,                                     # final text from react_agent
  verification_result: dict | None,
  verification_attempts: int,
  response: dict | None,                                     # final JSON from format_output
  token_usage: dict,
  node_latencies: dict,
  error_log: list[dict],
  trace_log: list[dict],
}
```

### Step 0: API receives request (code only)

- **Where:** `agent/app.py` — `POST /api/chat`.
- **Input:** `ChatRequest`: `message`, optional `thread_id`, optional `access_token`.
- **Action:** Validate message length; `thread_id = request.thread_id or uuid4()`. Build **input_state** (see below). If a checkpointer is configured, LangGraph will **merge** this with any checkpointed state for `thread_id` (e.g. prior `messages`, `regime`, `portfolio` from a previous turn).
- **Output:** `input_state` passed to `agent_graph.ainvoke(input_state, config={"configurable": {"thread_id": thread_id}})`.

**Initial state shape (per request):**

```text
input_state = {
  "messages": [HumanMessage(content=message)],
  "intent": "", "extracted_params": {}, "ghostfolio_access_token": access_token or None,
  "tool_results": {}, "tools_called": [], "react_step": 0,
  "synthesis": None, "verification_result": None, "verification_attempts": 0,
  "response": None, "token_usage": {}, "node_latencies": {}, "error_log": [], "trace_log": [],
}
```

**Route after API:** Graph entry point is `check_context` (single path).

### Step 1: check_context (code only)

- **Where:** `agent/nodes/context.py` — `check_context_node(state)`.
- **Type:** Code only; no LLM, no network (only reads state and system time).
- **Input:** Full `AgentState` (e.g. `regime`, `regime_timestamp`, `portfolio`, `portfolio_timestamp` from checkpoint or from previous tool runs).
- **Logic:** If `regime` exists and `regime_timestamp` is within `REGIME_TTL` (30 min), keep `regime`/`regime_timestamp`; else set to `None`. Same for `portfolio`/`portfolio_timestamp` with `PORTFOLIO_TTL` (5 min).
- **Output:** Partial state: `{ "regime", "regime_timestamp", "portfolio", "portfolio_timestamp" }`.
- **Route:** Fixed edge: `check_context` → **react_agent**.

### Step 2: react_agent (LLM)

- **Where:** `agent/nodes/react_agent.py` — `react_agent_node(state)`.
- **Type:** **LLM** (ChatAnthropic, model from `config.agent_model`, default Haiku). Tools bound when `react_step < MAX_REACT_STEPS` (10).
- **Input:** State’s `messages`; `regime`/`portfolio` used to build context block in system prompt.
- **Prompt shape:** `[SystemMessage(REACT_SYSTEM_PROMPT + context_block), ...messages]`. If `react_step >= MAX_REACT_STEPS`, appends `FINAL_STEP_ADDENDUM`.
- **Invocation:** `llm_with_tools.invoke(llm_messages)` → single **AIMessage** with optional `content` and/or `tool_calls` (list of `{ "id", "name", "args" }`).
- **Output:** Append AIMessage to `messages`; set `synthesis` to `response.content.strip()` **only when** `tool_calls` is empty and there is content; update `token_usage`, `node_latencies`, `trace_log`, `error_log`.
- **Route:** **route_after_react(state)**: if last message has `tool_calls` and `react_step < MAX_REACT_STEPS` → **execute_tools**; else → **verify**.

### Step 3a: execute_tools (code only)

- **Where:** `agent/nodes/tools.py` — `execute_tools_node(state)`.
- **Type:** Code only; runs tool functions in **parallel** via `ThreadPoolExecutor` (max_workers=5). Some tools call Ghostfolio/market APIs.
- **Input:** `messages[-1]` = AIMessage with `tool_calls`. State has `tool_results`, `tools_called`, `regime`, `portfolio`, `ghostfolio_access_token` for injection.
- **Logic:** For each tool: resolve from `TOOL_REGISTRY`, inject `client` (Ghostfolio) where needed, inject `portfolio_data`/`market_data` from prior results. Execute; optionally update `regime`/`portfolio` timestamps. Truncate result to 8000 chars for ToolMessage content.
- **Output:** Append one **ToolMessage** per tool call; update `tool_results`, `tools_called`; increment `react_step`; update `node_latencies`, `error_log`, `trace_log`.
- **Route:** Fixed edge: **execute_tools** → **react_agent** (loop back).

### Step 3b: react_agent again (LLM)

- Same node. `messages` now includes ToolMessages. LLM either calls more tools (→ execute_tools) or returns final text (→ verify). That text is stored in `synthesis`.

### Step 4: verify (code only)

- **Where:** `agent/nodes/verification.py` — `verify_node(state)`.
- **Type:** Code only.
- **Input:** `synthesis`, `tool_results`, `tools_called`, `messages` (last user message), `extracted_params`. Intent = `infer_intent_from_tools(tools_called)`.
- **Logic:** Fact-check numbers vs tool results (intent-aware); price-quote freshness; confidence 0–100; guardrail checks; tax_estimate sanity; compliance vs synthesis consistency.
- **Output:** `verification_result`: `{ "passed", "issues", "confidence", "fact_check_issues", "guardrail_issues" }`; increment `verification_attempts`; update `node_latencies`, `trace_log`.
- **Route:** Fixed edge: **verify** → **format_output**.

### Step 5: format_output (code only)

- **Where:** `agent/nodes/formatter.py` — `format_output_node(state)`.
- **Type:** Code only.
- **Input:** `synthesis`, `tool_results`, `tools_called`, `verification_result`, `token_usage`, `node_latencies`, `error_log`, `trace_log`, `regime`.
- **Logic:** `intent = infer_intent_from_tools(tools_called)`; build `warnings` from verification; extract citations; build intent-specific `data`; aggregate token usage.
- **Output:** `response`: `{ "summary", "confidence", "intent", "data", "citations", "warnings", "tools_used", "disclaimer", "observability" }`.
- **Route:** **format_output** → **END**.

### Step 6: API returns (code only)

- **Where:** `agent/app.py` after `ainvoke` returns. Adds `total_latency_seconds` to `response["observability"]`; optionally caches messages; returns `ChatResponse(response=response_data, thread_id=thread_id)`.

### Graph edges and node types (visual)

```text
[API] --> input_state --> check_context (code) --> react_agent (LLM)
                                                          |
                                            route_after_react: tool_calls?
                                                          |
                                    +---------------------+---------------------+
                                    | yes                 | no (final answer)   |
                                    v                     v                     |
                            execute_tools (code)      verify (code)              |
                                    |                     |                     |
                                    +---------------------+                     |
                                    |                     v                     |
                                    |               format_output (code)         |
                                    |                     |                     |
                                    +---------------------+---------------------+
                                                              v
                                                            END
```

---

## 8. ReAct Loop — In-Depth

### What “ReAct” means here

The agent uses a **Reasoning + Acting** loop: the LLM can **reason** (output text) and **act** (request tool calls) in the same step. There is no separate “classify” or “synthesize” LLM; one model both chooses tools and produces the final answer after seeing tool results.

### Loop structure

1. **First call to react_agent**  
   Input: `messages` = `[HumanMessage(user_query)]` (plus any conversation history from checkpoint). System prompt: tool-routing table, response-format rules, safety rules, and a **context block** (cached regime/portfolio if fresh).  
   LLM either: **(A)** Returns `tool_calls` → go to **execute_tools**; or **(B)** Returns only `content` (no tool_calls) → go to **verify** (0-tool path).

2. **execute_tools**  
   Reads `messages[-1].tool_calls`. Runs each tool (with optional injection of prior `tool_results` and Ghostfolio client). Appends one **ToolMessage** per call to `messages`, updates `tool_results` and `tools_called`, increments `react_step`. Single fixed edge: back to **react_agent**.

3. **Second (and later) call to react_agent**  
   Input: `messages` = previous messages + new ToolMessages. LLM either: **(A)** Issues more `tool_calls` → execute_tools again (up to `MAX_REACT_STEPS`); or **(B)** Returns only `content` (final answer) → stored in `synthesis` → go to **verify**.

4. **Exiting the loop**  
   **route_after_react** sends to **verify** when: the last message has **no** `tool_calls`, or `react_step >= MAX_REACT_STEPS`. After verify → format_output → END; no return to react_agent.

### Message accumulation

- `messages` uses LangGraph’s `add_messages` reducer: every node that returns `"messages": [new_msg]` **appends** to the list. Typical sequence: `[HumanMessage]` → `[HumanMessage, AIMessage(tool_calls=[...])]` → `[..., ToolMessage, ToolMessage, ...]` → `[..., AIMessage(content="Final answer.")]`.
- The same list is used for: (1) next react_agent invocation, (2) verify’s “last user message”, (3) checkpoint/cache for conversation history.

### Tool-call contract

- **AIMessage.tool_calls:** list of `{"id": str, "name": str, "args": dict}`.
- **execute_tools** preserves order and returns one **ToolMessage** per call with matching `tool_call_id`.
- **TOOL_REGISTRY** maps `name` to a Python function. Ghostfolio-backed tools get `client` (and optionally `portfolio_data` / `market_data`) injected from state.

### Context and caching

- **check_context** only promotes or clears cached `regime`/`portfolio` in state; it does not fetch.
- **execute_tools** writes back `regime`/`regime_timestamp` when `detect_regime` runs, and `portfolio`/`portfolio_timestamp` when `get_portfolio_snapshot` runs. So on a later react_agent step (or a later request with the same thread), the context block and tools can reuse that data.

### Efficiency and limits

- **Prompt rule:** “Call ALL required tools in ONE parallel step.” So for “Can I buy $10k TSLA?” the model is steered to call `get_portfolio_snapshot`, `get_market_data`, and `trade_guardrails_check` in one go; execute_tools runs them in parallel.
- **MAX_REACT_STEPS = 10:** Prevents infinite tool loops. After 10 steps, the system addendum forces a final answer.
- **Per-tool result truncation:** ToolMessage content is capped at 8000 characters.

---

## 9. Summary Table

| Aspect                    | Before (plan)                                                                   | After (current system)                                                                 |
| ------------------------- | ------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| **LLM calls per request** | 4 (intent + react + react + synthesize)                                         | 1–2 (react only, loop as needed)                                                       |
| **Intent**                | Separate classify_intent LLM                                                    | Inferred from `tools_called` in formatter/verification                                 |
| **Synthesis**             | Dedicated synthesize LLM node                                                   | Rules in react system prompt; final answer = response                                  |
| **Graph**                 | classify → check_context → react → tools → react → synthesize → verify → format | check_context → react ↔ tools → verify → format                                        |
| **Model**                 | Implicit Sonnet                                                                 | Configurable (default Haiku)                                                           |
| **Eval intent**           | From intent node                                                                | From `infer_intent_from_tools` (tool selection accuracy)                               |
| **Eval coverage**         | Full suite                                                                      | Full suite + 25 golden cases + labeled scenarios (category/subcategory/difficulty)     |
| **Observability**         | Broken node timings, no aggregates                                              | Fixed timings; tool_success_rate, hallucination_rate, verification_accuracy in reports |

---

## References

- **Plan:** `.cursor/plans/latency_overhaul_and_requirements_d8f6c417.plan.md` (or equivalent path in your environment).
- **Key commits (illustrative):** `eb285191b` (refactor standard ReAct pipeline), `04a269ccf` (scenario eval), `0619b3888` (SIGFPE/edge + gs-015), `b6e1de5b5` (golden set baseline), `aee817493` (latency via caching/prompt).
- **Code:** `agent/state.py`, `agent/graph.py`, `agent/config.py`, `agent/app.py`, `agent/nodes/context.py`, `agent/nodes/react_agent.py`, `agent/nodes/tools.py`, `agent/nodes/formatter.py`, `agent/nodes/verification.py`, `tests/eval/run_evals.py`, `tests/eval/dataset.py`, `tests/eval/golden_cases.py`, `tests/eval/scenarios.py`.
