"""Node: Tool execution for ReAct loop — reads tool_calls from the last AIMessage."""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from agent.ghostfolio_client import GhostfolioClient
from agent.state import AgentState
from agent.observability import (
    track_latency, make_error_entry, make_trace_entry, ErrorCategory,
)
from agent.tools.market_data import get_market_data
from agent.tools.portfolio import get_portfolio_snapshot
from agent.tools.regime import detect_regime
from agent.tools.scanner import scan_strategies
from agent.tools.risk import guardrails_check, portfolio_guardrails_check, trade_guardrails_check, check_risk
from agent.tools.history import get_trade_history
from agent.tools.symbols import lookup_symbol
from agent.tools.activities import create_activity
from agent.tools.compliance_check import compliance_check
from agent.tools.watchlist import add_to_watchlist

logger = logging.getLogger(__name__)

TOOL_REGISTRY = {
    "get_market_data": get_market_data,
    "get_portfolio_snapshot": get_portfolio_snapshot,
    "detect_regime": detect_regime,
    "scan_strategies": scan_strategies,
    "guardrails_check": guardrails_check,
    "get_trade_history": get_trade_history,
    "lookup_symbol": lookup_symbol,
    "create_activity": create_activity,
    "compliance_check": compliance_check,
    "add_to_watchlist": add_to_watchlist,
    # Legacy names — kept for backward compatibility
    "portfolio_guardrails_check": portfolio_guardrails_check,
    "trade_guardrails_check": trade_guardrails_check,
    "check_risk": check_risk,
}

GHOSTFOLIO_TOOLS = frozenset({
    "get_portfolio_snapshot",
    "get_trade_history",
    "guardrails_check",
    "lookup_symbol",
    "create_activity",
    "add_to_watchlist",
    "compliance_check",
    # Legacy names
    "portfolio_guardrails_check",
    "trade_guardrails_check",
    "check_risk",
})


def _execute_single_tool(
    tool_fn,
    tool_name: str,
    tool_args: dict,
    tool_call_id: str,
) -> tuple[str, Any, float, Exception | None, str]:
    """Execute a single tool and return (tool_name, result, timing, error, tool_call_id)."""
    logger.info("Executing tool: %s with args: %s", tool_name, tool_args)
    t0 = time.perf_counter()
    try:
        result = tool_fn(**tool_args)
        elapsed = round(time.perf_counter() - t0, 4)
        return (tool_name, result, elapsed, None, tool_call_id)
    except Exception as e:
        elapsed = round(time.perf_counter() - t0, 4)
        logger.error("Tool %s failed: %s", tool_name, e)
        return (tool_name, {"error": str(e)}, elapsed, e, tool_call_id)


def execute_tools_node(state: AgentState) -> dict[str, Any]:
    """Execute tool_calls from the last AIMessage and return ToolMessages + updated state."""
    messages = state.get("messages", [])
    tool_results = dict(state.get("tool_results", {}))
    tools_called = list(state.get("tools_called", []))
    react_step = state.get("react_step", 0)
    node_latencies = dict(state.get("node_latencies") or {})
    error_log = list(state.get("error_log") or [])
    trace_log = list(state.get("trace_log") or [])

    regime = state.get("regime")
    regime_timestamp = state.get("regime_timestamp")
    portfolio = state.get("portfolio")
    portfolio_timestamp = state.get("portfolio_timestamp")
    ghostfolio_token = state.get("ghostfolio_access_token")

    step_key = f"execute_tools_{react_step}"

    if not messages:
        return {"react_step": react_step + 1}

    last_msg = messages[-1]
    if not isinstance(last_msg, AIMessage) or not getattr(last_msg, "tool_calls", None):
        return {"react_step": react_step + 1}

    # Collect tool call specs preserving order (for deterministic ToolMessage ordering)
    tool_call_specs = []
    for tc in last_msg.tool_calls:
        tool_name = tc["name"]
        tool_args = dict(tc.get("args", {}))
        tool_call_id = tc["id"]

        tool_fn = TOOL_REGISTRY.get(tool_name)
        if not tool_fn:
            tool_call_specs.append((tool_name, tool_args, tool_call_id, None))
            continue

        if tool_name == "scan_strategies" and "regime" not in tool_args and regime:
            tool_args["regime"] = regime

        # Each parallel tool gets its own Ghostfolio client (httpx.Client is not thread-safe)
        if tool_name in GHOSTFOLIO_TOOLS and ghostfolio_token:
            try:
                tool_args["client"] = GhostfolioClient(access_token=ghostfolio_token)
            except Exception as e:
                logger.warning("Failed to create Ghostfolio client for %s: %s", tool_name, e)

        # Inject previously-fetched data to avoid redundant API calls
        if tool_name in ("guardrails_check", "portfolio_guardrails_check", "trade_guardrails_check"):
            if "get_portfolio_snapshot" in tool_results:
                tool_args["portfolio_data"] = tool_results["get_portfolio_snapshot"]
            if "get_market_data" in tool_results:
                tool_args["market_data"] = tool_results["get_market_data"]

        tool_call_specs.append((tool_name, tool_args, tool_call_id, tool_fn))

    # Execute tools in parallel using ThreadPoolExecutor
    # Maintain insertion order for ToolMessage responses
    results_by_call_id: dict[str, tuple[str, Any, float, Exception | None]] = {}
    tool_timings: dict[str, float] = {}
    clients_to_close: list[GhostfolioClient] = []

    with track_latency() as step_timing:
        # Track per-tool clients for cleanup
        for _, args, _, _ in tool_call_specs:
            client = args.get("client")
            if isinstance(client, GhostfolioClient):
                clients_to_close.append(client)

        try:
            # Handle unknown tools immediately; submit valid tools to executor
            futures_map = {}
            with ThreadPoolExecutor(max_workers=5) as executor:
                for tool_name, tool_args, tool_call_id, tool_fn in tool_call_specs:
                    if tool_fn is None:
                        result = {"error": f"Unknown tool: {tool_name}"}
                        results_by_call_id[tool_call_id] = (tool_name, result, 0.0, ValueError(f"Unknown tool: {tool_name}"))
                        continue
                    future = executor.submit(
                        _execute_single_tool, tool_fn, tool_name, tool_args, tool_call_id
                    )
                    futures_map[future] = tool_call_id

                for future in as_completed(futures_map):
                    tool_name, result, elapsed, err, tcid = future.result()
                    results_by_call_id[tcid] = (tool_name, result, elapsed, err)

        finally:
            for client in clients_to_close:
                try:
                    client.close()
                except Exception:
                    pass

    # Build ToolMessages in the original tool_call order
    new_messages = []
    for _, _, tool_call_id, _ in tool_call_specs:
        tool_name, result, elapsed, err = results_by_call_id[tool_call_id]
        tool_timings[tool_name] = elapsed
        tool_results[tool_name] = result
        tools_called.append(tool_name)

        if err is not None:
            error_log.append(make_error_entry(
                step_key, err, ErrorCategory.TOOL, context={"tool": tool_name},
            ))

        now_ts = datetime.now(timezone.utc).isoformat()
        if tool_name == "detect_regime" and err is None:
            regime = result
            regime_timestamp = now_ts
        elif tool_name == "get_portfolio_snapshot" and err is None:
            portfolio = result
            portfolio_timestamp = now_ts
        elif tool_name == "create_activity" and err is None:
            # Activity changes the portfolio — invalidate cache so the next
            # query fetches fresh data from Ghostfolio.
            portfolio = None
            portfolio_timestamp = None

        result_str = json.dumps(result, default=str)
        if len(result_str) > 8000:
            result_str = result_str[:8000] + "... (truncated)"

        new_messages.append(
            ToolMessage(content=result_str, tool_call_id=tool_call_id)
        )

    node_latencies[step_key] = step_timing.get("elapsed_seconds", 0)
    for tn, dur in tool_timings.items():
        node_latencies[f"tool_{tn}_{react_step}"] = dur

    trace_log.append(make_trace_entry(
        step_key,
        input_summary=f"tool_calls={[tc['name'] for tc in last_msg.tool_calls]}",
        output_summary=f"executed={list(tool_timings.keys())}",
        metadata={"tool_timings": tool_timings},
    ))

    return {
        "messages": new_messages,
        "tool_results": tool_results,
        "tools_called": tools_called,
        "react_step": react_step + 1,
        "regime": regime,
        "regime_timestamp": regime_timestamp,
        "portfolio": portfolio,
        "portfolio_timestamp": portfolio_timestamp,
        "node_latencies": node_latencies,
        "error_log": error_log,
        "trace_log": trace_log,
    }
