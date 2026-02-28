"""Agent state schema for LangGraph."""

from __future__ import annotations

from typing import TypedDict, Annotated, Any
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    # Conversation (HumanMessage, AIMessage with tool_calls, ToolMessage)
    messages: Annotated[list, add_messages]

    # Intent — inferred from tools_called by format_output (not set by an LLM node)
    intent: str
    extracted_params: dict

    # Cached context
    regime: dict | None
    regime_timestamp: str | None
    portfolio: dict | None
    portfolio_timestamp: str | None

    # Optional JWT/security token for Ghostfolio API calls (forwarded from request)
    ghostfolio_access_token: str | None

    # Tool results for current query (accumulated across ReAct steps)
    tool_results: dict
    tools_called: list[str]

    # ReAct loop control
    react_step: int

    # Synthesis (set by react_agent when it produces a final text answer)
    synthesis: str | None
    verification_result: dict | None
    verification_attempts: int

    # Final output
    response: dict | None

    # Observability: token usage, latency, errors, trace
    token_usage: dict
    node_latencies: dict
    error_log: list[dict]
    trace_log: list[dict]
