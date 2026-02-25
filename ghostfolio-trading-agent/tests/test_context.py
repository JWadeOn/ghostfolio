"""Unit tests for context node — tool selection and param building."""

from langchain_core.messages import AIMessage, HumanMessage

from agent.nodes.context import check_context_node


def test_risk_check_action_buy_from_current_message():
    """When the current user message says 'buy' (not 'sell'), check_risk gets action=buy even if params say sell."""
    state = {
        "intent": "risk_check",
        "extracted_params": {
            "symbols": ["GOOG"],
            "action": "sell",  # e.g. LLM confused by previous sell discussion
        },
        "messages": [
            HumanMessage(content="should I sell GOOG?"),
            AIMessage(content="Recommendation: SELL 80-90%..."),
            HumanMessage(content="Should I buy it?"),
        ],
    }
    result = check_context_node(state)
    tools_needed = result["tools_needed"]
    check_risk_spec = next((t for t in tools_needed if t["tool"] == "check_risk"), None)
    assert check_risk_spec is not None
    assert check_risk_spec["params"].get("action") == "buy"


def test_risk_check_action_sell_when_user_says_sell():
    """When the current user message says 'sell', check_risk gets action=sell."""
    state = {
        "intent": "risk_check",
        "extracted_params": {"symbols": ["GOOG"], "action": "buy"},
        "messages": [
            HumanMessage(content="Should I sell GOOG?"),
        ],
    }
    result = check_context_node(state)
    tools_needed = result["tools_needed"]
    check_risk_spec = next((t for t in tools_needed if t["tool"] == "check_risk"), None)
    assert check_risk_spec is not None
    assert check_risk_spec["params"].get("action") == "sell"


def test_risk_check_action_from_params_when_message_ambiguous():
    """When message has neither 'buy' nor 'sell', use params.action or default buy."""
    state = {
        "intent": "risk_check",
        "extracted_params": {"symbols": ["GOOG"], "action": "sell"},
        "messages": [HumanMessage(content="What about GOOG?")],
    }
    result = check_context_node(state)
    tools_needed = result["tools_needed"]
    check_risk_spec = next((t for t in tools_needed if t["tool"] == "check_risk"), None)
    assert check_risk_spec is not None
    assert check_risk_spec["params"].get("action") == "sell"


def test_risk_check_resolves_symbol_from_single_holding_when_user_says_buy():
    """When user says 'buy' but intent didn't resolve symbols, use single holding as 'it' and force action=buy."""
    state = {
        "intent": "risk_check",
        "extracted_params": {"symbols": [], "action": "sell"},
        "messages": [
            HumanMessage(content="should I sell GOOG?"),
            AIMessage(content="SELL 80-90%..."),
            HumanMessage(content="should i buy it?"),
        ],
        "portfolio": {
            "holdings": [{"symbol": "GOOG", "weight": 100}],
            "summary": {"total_value": 155460, "total_cash": 0},
        },
    }
    result = check_context_node(state)
    tools_needed = result["tools_needed"]
    check_risk_spec = next((t for t in tools_needed if t["tool"] == "check_risk"), None)
    assert check_risk_spec is not None
    assert check_risk_spec["params"].get("symbol") == "GOOG"
    assert check_risk_spec["params"].get("action") == "buy"
