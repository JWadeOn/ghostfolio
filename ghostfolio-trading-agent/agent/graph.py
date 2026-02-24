"""LangGraph agent definition — the 6-node reasoning graph."""

from langgraph.graph import StateGraph, END

from agent.state import AgentState
from agent.nodes.intent import classify_intent_node
from agent.nodes.context import check_context_node, route_after_context
from agent.nodes.tools import execute_tools_node
from agent.nodes.synthesis import synthesize_node
from agent.nodes.verification import verify_node, route_after_verification
from agent.nodes.formatter import format_output_node


def build_agent_graph():
    """Build and compile the 6-node LangGraph agent."""
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

    # Linear edges
    graph.add_edge("classify_intent", "check_context")

    # Context check → either tools or synthesize
    graph.add_conditional_edges("check_context", route_after_context, {
        "needs_tools": "execute_tools",
        "has_context": "synthesize",
    })

    graph.add_edge("execute_tools", "synthesize")
    graph.add_edge("synthesize", "verify")

    # Verification → pass (format) or fail (re-synthesize) or max_retries (format with warnings)
    graph.add_conditional_edges("verify", route_after_verification, {
        "pass": "format_output",
        "fail": "synthesize",
        "max_retries": "format_output",
    })

    graph.add_edge("format_output", END)

    return graph.compile()


# Singleton compiled graph
agent_graph = build_agent_graph()
