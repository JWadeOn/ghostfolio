"""LangGraph agent definition — ReAct loop with mandatory intent and passive context."""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import StateGraph, END

from agent.state import AgentState
from agent.nodes.intent import classify_intent_node
from agent.nodes.context import check_context_node
from agent.nodes.react_agent import react_agent_node, route_after_react
from agent.nodes.tools import execute_tools_node
from agent.nodes.synthesis import synthesize_node
from agent.nodes.verification import verify_node, route_after_verification
from agent.nodes.formatter import format_output_node


def build_agent_graph(checkpointer: BaseCheckpointSaver | None = None):
    """Build and compile the ReAct agent graph.

    Flow:
        classify_intent -> check_context -> react_agent <-> execute_tools -> synthesize -> verify -> format_output
    """
    graph = StateGraph(AgentState)

    graph.add_node("classify_intent", classify_intent_node)
    graph.add_node("check_context", check_context_node)
    graph.add_node("react_agent", react_agent_node)
    graph.add_node("execute_tools", execute_tools_node)
    graph.add_node("synthesize", synthesize_node)
    graph.add_node("verify", verify_node)
    graph.add_node("format_output", format_output_node)

    graph.set_entry_point("classify_intent")

    graph.add_edge("classify_intent", "check_context")
    graph.add_edge("check_context", "react_agent")

    graph.add_conditional_edges("react_agent", route_after_react, {
        "execute_tools": "execute_tools",
        "synthesize": "synthesize",
    })

    graph.add_edge("execute_tools", "react_agent")

    graph.add_edge("synthesize", "verify")

    graph.add_conditional_edges("verify", route_after_verification, {
        "pass": "format_output",
        "fail": "synthesize",
        "max_retries": "format_output",
    })

    graph.add_edge("format_output", END)

    return graph.compile(checkpointer=checkpointer)


# Graph without checkpointer for tests and scripts that import directly
agent_graph = build_agent_graph()
