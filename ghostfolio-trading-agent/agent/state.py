"""Agent state schema for LangGraph."""

from __future__ import annotations

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
    regime: dict | None
    regime_timestamp: str | None
    portfolio: dict | None
    portfolio_timestamp: str | None

    # Tool results for current query
    tool_results: dict          # keyed by tool name -> result
    tools_called: list[str]     # ordered list of tools invoked this turn
    tools_needed: list[dict]    # tools to execute and their params

    # Synthesis and verification
    synthesis: str | None
    verification_result: dict | None
    verification_attempts: int

    # Final output
    response: dict | None
