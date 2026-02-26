"""Integration tests for the ReAct agent graph."""

import json
import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import AIMessage, HumanMessage


def _make_initial_state(message: str) -> dict:
    return {
        "messages": [HumanMessage(content=message)],
        "intent": "",
        "extracted_params": {},
        "regime": None,
        "regime_timestamp": None,
        "portfolio": None,
        "portfolio_timestamp": None,
        "ghostfolio_access_token": None,
        "tool_results": {},
        "tools_called": [],
        "react_step": 0,
        "synthesis": None,
        "verification_result": None,
        "verification_attempts": 0,
        "response": None,
    }


class TestReActAgentGraph:
    """Tests for the full ReAct graph with mocked LLMs."""

    @patch("agent.nodes.intent.ChatAnthropic")
    @patch("agent.nodes.react_agent.ChatAnthropic")
    @patch("agent.nodes.synthesis.ChatAnthropic")
    def test_regime_check_flow(self, mock_synth_llm, mock_react_llm, mock_intent_llm):
        """Test: intent=regime_check -> ReAct calls detect_regime -> synthesis."""
        intent_response = MagicMock()
        intent_response.content = '{"intent": "regime_check", "params": {"symbols": [], "timeframe": null}}'
        mock_intent_llm.return_value.invoke.return_value = intent_response

        # ReAct agent: first call returns tool_calls for detect_regime, second call returns final text
        react_tool_call = AIMessage(
            content="",
            tool_calls=[{"name": "detect_regime", "args": {"index": "SPY"}, "id": "call_1"}],
        )
        react_final = AIMessage(content="The market regime is transitional.")
        react_mock = MagicMock()
        react_mock.invoke = MagicMock(side_effect=[react_tool_call, react_final])
        mock_react_llm.return_value.bind_tools.return_value = react_mock
        mock_react_llm.return_value.invoke.return_value = react_final

        synth_response = MagicMock()
        synth_response.content = "The current market regime is transitional with moderate volatility."
        mock_synth_llm.return_value.invoke.return_value = synth_response

        from agent.graph import agent_graph
        result = agent_graph.invoke(_make_initial_state("What's the current market regime?"))

        assert result["response"] is not None
        assert result["intent"] == "regime_check"
        assert "detect_regime" in result["tools_called"]

    @patch("agent.nodes.intent.ChatAnthropic")
    @patch("agent.nodes.react_agent.ChatAnthropic")
    @patch("agent.nodes.synthesis.ChatAnthropic")
    def test_general_query_no_tools(self, mock_synth_llm, mock_react_llm, mock_intent_llm):
        """Test: intent=general -> ReAct returns text with no tool_calls -> synthesis."""
        intent_response = MagicMock()
        intent_response.content = '{"intent": "general", "params": {}}'
        mock_intent_llm.return_value.invoke.return_value = intent_response

        react_final = AIMessage(content="Hello! I'm your trading intelligence assistant.")
        react_final.tool_calls = []
        react_mock = MagicMock()
        react_mock.invoke = MagicMock(return_value=react_final)
        mock_react_llm.return_value.bind_tools.return_value = react_mock

        synth_response = MagicMock()
        synth_response.content = "Hello! I'm your trading intelligence assistant."
        mock_synth_llm.return_value.invoke.return_value = synth_response

        from agent.graph import agent_graph
        result = agent_graph.invoke(_make_initial_state("Hello!"))

        assert result["response"] is not None
        assert result["intent"] == "general"
        assert len(result["tools_called"]) == 0

    @patch("agent.nodes.intent.ChatAnthropic")
    @patch("agent.nodes.react_agent.ChatAnthropic")
    @patch("agent.nodes.synthesis.ChatAnthropic")
    def test_multi_step_flow(self, mock_synth_llm, mock_react_llm, mock_intent_llm):
        """Test: agent calls portfolio then risk in two separate ReAct steps."""
        intent_response = MagicMock()
        intent_response.content = '{"intent": "risk_check", "params": {"symbols": ["AAPL"], "action": "buy"}}'
        mock_intent_llm.return_value.invoke.return_value = intent_response

        step1 = AIMessage(
            content="",
            tool_calls=[{"name": "get_portfolio_snapshot", "args": {}, "id": "call_1"}],
        )
        step2 = AIMessage(
            content="",
            tool_calls=[{"name": "trade_guardrails_check", "args": {"symbol": "AAPL", "side": "buy"}, "id": "call_2"}],
        )
        step3 = AIMessage(content="Risk check complete for AAPL.")

        react_mock = MagicMock()
        react_mock.invoke = MagicMock(side_effect=[step1, step2, step3])
        mock_react_llm.return_value.bind_tools.return_value = react_mock
        mock_react_llm.return_value.invoke.return_value = step3

        synth_response = MagicMock()
        synth_response.content = "Risk assessment for AAPL buy position with stop loss at $150 and target at $200."
        mock_synth_llm.return_value.invoke.return_value = synth_response

        from agent.graph import agent_graph
        result = agent_graph.invoke(_make_initial_state("Can I buy $10k of AAPL?"))

        assert result["response"] is not None
        assert result["intent"] == "risk_check"
        assert "get_portfolio_snapshot" in result["tools_called"]
        assert "trade_guardrails_check" in result["tools_called"]
        assert result["react_step"] >= 2
