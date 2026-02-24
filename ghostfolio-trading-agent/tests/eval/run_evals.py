"""Eval runner — test agent responses against expected outcomes."""

import json
import logging
import sys
from typing import Any

from langchain_core.messages import HumanMessage

from tests.eval.dataset import eval_cases

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_single_eval(case: dict, agent_graph: Any) -> dict:
    """Run a single eval case and return pass/fail with details."""
    input_text = case["input"]
    expected_intent = case.get("expected_intent")
    expected_tools = case.get("expected_tools", [])
    expected_contains = case.get("expected_output_contains", [])
    should_contain = case.get("should_contain", [])
    should_not_contain = case.get("should_not_contain", [])

    state = {
        "messages": [HumanMessage(content=input_text)],
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

    try:
        result = agent_graph.invoke(state)
    except Exception as e:
        return {
            "input": input_text,
            "passed": False,
            "errors": [f"Agent error: {str(e)}"],
        }

    errors = []

    # Check intent
    if expected_intent and result.get("intent") != expected_intent:
        errors.append(
            f"Intent mismatch: expected '{expected_intent}', got '{result.get('intent')}'"
        )

    # Check tools called
    tools_called = result.get("tools_called", [])
    for tool in expected_tools:
        if tool not in tools_called:
            errors.append(f"Expected tool '{tool}' was not called. Called: {tools_called}")

    # Check output contains
    response = result.get("response", {})
    summary = response.get("summary", "")
    summary_lower = summary.lower()

    for term in expected_contains:
        if term.lower() not in summary_lower:
            errors.append(f"Expected output to contain '{term}' but it wasn't found")

    # Check should_contain (same as expected_output_contains)
    for term in should_contain:
        if term.lower() not in summary_lower:
            errors.append(f"Expected output to contain '{term}' but it wasn't found")

    # Check should not contain
    for term in should_not_contain:
        if term.lower() in summary_lower:
            errors.append(f"Output should NOT contain '{term}' but it was found")

    return {
        "input": input_text,
        "passed": len(errors) == 0,
        "intent": result.get("intent"),
        "tools_called": tools_called,
        "errors": errors,
        "confidence": response.get("confidence", 0),
    }


def run_all_evals():
    """Run all eval cases and print results."""
    from agent.graph import agent_graph

    results = []
    passed = 0
    total = len(eval_cases)

    for i, case in enumerate(eval_cases):
        logger.info(f"Running eval {i+1}/{total}: {case['input'][:50]}...")
        result = run_single_eval(case, agent_graph)
        results.append(result)

        if result["passed"]:
            passed += 1
            logger.info(f"  PASS")
        else:
            logger.warning(f"  FAIL: {result['errors']}")

    print(f"\n{'='*60}")
    print(f"Eval Results: {passed}/{total} passed ({passed/total*100:.0f}%)")
    print(f"{'='*60}")

    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  [{status}] {r['input'][:60]}")
        if not r["passed"]:
            for err in r["errors"]:
                print(f"        - {err}")

    return results


if __name__ == "__main__":
    run_all_evals()
