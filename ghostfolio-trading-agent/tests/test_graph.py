"""Integration tests for the full agent graph."""

import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import HumanMessage


class TestAgentGraph:
    """Tests that require mocking the LLM but test real tool execution."""

    @patch("agent.nodes.intent.ChatAnthropic")
    @patch("agent.nodes.synthesis.ChatAnthropic")
    def test_regime_check_flow(self, mock_synth_llm, mock_intent_llm):
        """Test a regime check query goes through the full pipeline."""
        # Mock intent classification
        intent_response = MagicMock()
        intent_response.content = '{"intent": "regime_check", "params": {"symbols": [], "timeframe": null}}'
        mock_intent_llm.return_value.invoke.return_value = intent_response

        # Mock synthesis
        synth_response = MagicMock()
        synth_response.content = "The current market regime is transitional."
        mock_synth_llm.return_value.invoke.return_value = synth_response

        from agent.graph import agent_graph

        state = {
            "messages": [HumanMessage(content="What's the current market regime?")],
            "intent": "",
            "extracted_params": {},
            "regime": None,
            "regime_timestamp": None,
            "portfolio": None,
            "portfolio_timestamp": None,
            "tool_results": {},
            "tools_called": [],
            "tools_needed": [],
            "synthesis": None,
            "verification_result": None,
            "verification_attempts": 0,
            "response": None,
        }

        result = agent_graph.invoke(state)
        assert result["response"] is not None
        assert result["intent"] == "regime_check"
        assert "detect_regime" in result["tools_called"]

    @patch("agent.nodes.intent.ChatAnthropic")
    @patch("agent.nodes.synthesis.ChatAnthropic")
    def test_general_query_skips_tools(self, mock_synth_llm, mock_intent_llm):
        """Test that a general query skips tool execution."""
        intent_response = MagicMock()
        intent_response.content = '{"intent": "general", "params": {}}'
        mock_intent_llm.return_value.invoke.return_value = intent_response

        synth_response = MagicMock()
        synth_response.content = "Hello! I'm your trading intelligence assistant."
        mock_synth_llm.return_value.invoke.return_value = synth_response

        from agent.graph import agent_graph

        state = {
            "messages": [HumanMessage(content="Hello!")],
            "intent": "",
            "extracted_params": {},
            "regime": None,
            "regime_timestamp": None,
            "portfolio": None,
            "portfolio_timestamp": None,
            "tool_results": {},
            "tools_called": [],
            "tools_needed": [],
            "synthesis": None,
            "verification_result": None,
            "verification_attempts": 0,
            "response": None,
        }

        result = agent_graph.invoke(state)
        assert result["response"] is not None
        assert result["intent"] == "general"
        assert len(result["tools_called"]) == 0
