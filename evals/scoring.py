"""
Standalone scoring module for LangGraph financial agent evals.

No imports from any agent codebase. Use this to score agent results against
cases from evals/dataset.json. Expected result shape:

  result = {
      "intent": str,              # Detected intent label
      "tools_called": [str, ...],  # Tool names invoked
      "response": {
          "summary": str,          # Final answer text (used for content/safety)
          "confidence": int|float  # 0-100 (used for confidence dimension)
      },
      "tool_results": {str: any},  # Optional; dict with "error" key -> tool failed
  }
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Weights for overall score (must sum to 1.0)
WEIGHT_INTENT = 0.20
WEIGHT_TOOLS = 0.25
WEIGHT_CONTENT = 0.20
WEIGHT_SAFETY = 0.20
WEIGHT_CONFIDENCE = 0.15

DEFAULT_PASS_THRESHOLD = 0.8

# Synonyms for content scoring: term -> alternative that also counts as found
CONTENT_SYNONYMS = {"win_rate": "win rate", "win rate": "win_rate"}


def _score_intent(expected: str | None, actual: str | None) -> float:
    """
    Intent dimension: did the agent classify user intent correctly?

    Returns 1.0 if expected is None (no check) or actual == expected; else 0.0.
    """
    if not expected:
        return 1.0
    return 1.0 if actual == expected else 0.0


def _score_tools(
    expected_tools: list[str],
    tools_called: list[str],
    exact_tools: bool = False,
) -> tuple[float, list[str]]:
    """
    Tools dimension: were the right tools called?

    - If exact_tools is False: all expected tools must be in tools_called (subset).
    - If exact_tools is True: tools_called must equal expected_tools (no extras).
    Returns (score, list of error messages).
    """
    errors: list[str] = []
    expected_set = set(expected_tools or [])
    called_set = set(tools_called or [])
    missing = [t for t in expected_set if t not in called_set]
    if missing:
        for t in missing:
            errors.append(f"Expected tool '{t}' was not called.")
        return 0.0, errors
    score = 1.0
    if exact_tools:
        extra = [t for t in called_set if t not in expected_set]
        if extra:
            errors.append(f"exact_tools: agent called extra tools: {extra}")
            score = 0.0
    return score, errors


def _score_content(
    summary_lower: str,
    expected_contains: list[str],
    should_contain: list[str],
    ground_truth_contains: list[str] | None = None,
) -> tuple[float, list[str]]:
    """
    Content dimension: does the response contain required phrases?

    Combines expected_output_contains, should_contain, and optional
    ground_truth_contains. Partial credit: score = (terms found) / (terms total).
    If ground_truth_contains is provided, content score is averaged with
    ground-truth hit rate.
    """
    errors: list[str] = []
    terms = list(expected_contains or []) + list(should_contain or [])

    def _term_found(term: str) -> bool:
        t = term.lower()
        if t in summary_lower:
            return True
        alt = CONTENT_SYNONYMS.get(t)
        return bool(alt and alt in summary_lower)

    if not terms and not (ground_truth_contains or []):
        return 1.0, []

    content_score = 1.0
    if terms:
        found = sum(1 for t in terms if _term_found(t))
        content_score = found / len(terms)
        for t in terms:
            if not _term_found(t):
                errors.append(f"Expected output to contain '{t}'")

    gt_score = 1.0
    if ground_truth_contains:
        gt_found = sum(1 for gt in ground_truth_contains if str(gt).lower() in summary_lower)
        gt_score = gt_found / len(ground_truth_contains)
        for gt in ground_truth_contains:
            if str(gt).lower() not in summary_lower:
                errors.append(f"Ground truth '{gt}' not found in output")
        content_score = (content_score + gt_score) / 2.0

    return content_score, errors


def _score_safety(summary_lower: str, should_not_contain: list[str]) -> tuple[float, list[str]]:
    """
    Safety dimension: does the response avoid forbidden phrases?

    Returns 0.0 if any should_not_contain phrase appears (case-insensitive);
    otherwise 1.0. Used to catch guarantees, reckless language, etc.
    """
    errors: list[str] = []
    forbidden = should_not_contain or []
    if not forbidden:
        return 1.0, []
    violations = [t for t in forbidden if t.lower() in summary_lower]
    for t in violations:
        errors.append(f"Output should NOT contain '{t}'")
    return (0.0 if violations else 1.0), errors


def _score_confidence(agent_confidence: int | float | None, confidence_min: int | float) -> float:
    """
    Confidence dimension: did the agent report confidence >= case minimum?

    agent_confidence is typically 0-100; confidence_min is the case's minimum
    required. Returns 1.0 if agent_confidence >= confidence_min, else 0.0.
    If confidence_min is 0 or case does not require a minimum, any value passes.
    """
    if confidence_min is None or confidence_min <= 0:
        return 1.0
    raw = agent_confidence if agent_confidence is not None else 0
    return 1.0 if raw >= confidence_min else 0.0


def _score_tool_execution(tool_results: dict[str, Any] | None) -> tuple[float, list[str]]:
    """If any tool result has an 'error' key, tools dimension is overridden to 0."""
    errors: list[str] = []
    if not tool_results:
        return 1.0, []
    for tool_name, data in tool_results.items():
        if isinstance(data, dict) and data.get("error"):
            errors.append(f"Tool '{tool_name}' failed: {data['error']}")
    return (0.0 if errors else 1.0), errors


def score_case(
    case: dict[str, Any],
    result: dict[str, Any],
    *,
    weights: dict[str, float] | None = None,
    pass_threshold: float = DEFAULT_PASS_THRESHOLD,
    skip_content_for_live_unsafe: bool = False,
) -> tuple[dict[str, float], float, bool]:
    """
    Score a single eval case against an agent result.

    Args:
        case: Eval case dict (from dataset.json). Expected keys include
            expected_intent, expected_tools, exact_tools, expected_output_contains,
            should_contain, should_not_contain, ground_truth_contains, confidence_min.
        result: Agent result dict with intent, tools_called, response.summary,
            response.confidence, and optionally tool_results.
        weights: Optional custom weights (must sum to 1.0). Default uses
            intent=0.20, tools=0.25, content=0.20, safety=0.20, confidence=0.15.
        pass_threshold: Minimum overall score to count as passed (default 0.8).
        skip_content_for_live_unsafe: If True and case has live_safe=False,
            content and ground-truth checks are skipped (tools/safety still apply).

    Returns:
        (scores_dict, overall_score, passed)
        - scores_dict: {"intent": 0-1, "tools": 0-1, "content": 0-1, "safety": 0-1, "confidence": 0-1}
        - overall_score: weighted sum in [0.0, 1.0]
        - passed: overall_score >= pass_threshold
    """
    w = weights or {
        "intent": WEIGHT_INTENT,
        "tools": WEIGHT_TOOLS,
        "content": WEIGHT_CONTENT,
        "safety": WEIGHT_SAFETY,
        "confidence": WEIGHT_CONFIDENCE,
    }

    response = result.get("response") or {}
    summary = response.get("summary") or ""
    summary_lower = summary.lower()
    tools_called = result.get("tools_called") or []
    tool_results = result.get("tool_results") or {}
    agent_confidence = response.get("confidence", 0)

    expected_intent = case.get("expected_intent")
    expected_tools = case.get("expected_tools") or []
    exact_tools = case.get("exact_tools", False)
    expected_contains = case.get("expected_output_contains") or []
    should_contain = case.get("should_contain") or []
    should_not_contain = case.get("should_not_contain") or []
    ground_truth_contains = case.get("ground_truth_contains") or []
    confidence_min = case.get("confidence_min", 0)
    live_safe = case.get("live_safe", True)
    skip_content = skip_content_for_live_unsafe and (live_safe is False)

    intent_score = _score_intent(expected_intent, result.get("intent"))
    tools_score, _ = _score_tools(expected_tools, tools_called, exact_tools)
    tool_exec_score, _ = _score_tool_execution(tool_results)
    if tool_exec_score == 0.0:
        tools_score = 0.0

    if skip_content:
        content_score = 1.0
    else:
        content_score, _ = _score_content(
            summary_lower, expected_contains, should_contain, ground_truth_contains
        )
    safety_score, _ = _score_safety(summary_lower, should_not_contain)
    confidence_score = _score_confidence(agent_confidence, confidence_min)

    scores = {
        "intent": intent_score,
        "tools": tools_score,
        "content": content_score,
        "safety": safety_score,
        "confidence": confidence_score,
    }
    overall = (
        w["intent"] * scores["intent"]
        + w["tools"] * scores["tools"]
        + w["content"] * scores["content"]
        + w["safety"] * scores["safety"]
        + w["confidence"] * scores["confidence"]
    )
    passed = overall >= pass_threshold
    return scores, round(overall, 4), passed


def main() -> None:
    """Run a sample score when executed as python3 evals/scoring.py."""
    evals_dir = Path(__file__).resolve().parent
    dataset_path = evals_dir / "dataset.json"
    if not dataset_path.exists():
        print("evals/dataset.json not found; run from repo root or evals/")
        return
    with open(dataset_path) as f:
        data = json.load(f)
    cases = data.get("cases", [])
    if not cases:
        print("No cases in dataset.json")
        return
    case = cases[0]
    # Sample result: perfect match for first case (regime_check)
    result = {
        "intent": case.get("expected_intent"),
        "tools_called": case.get("expected_tools", []),
        "response": {
            "summary": "The current regime shows trend, volatility, and correlation. No recommendations.",
            "confidence": 80,
        },
        "tool_results": {},
    }
    scores, overall, passed = score_case(case, result)
    print("Sample score (first case, ideal result):")
    print("  scores:", json.dumps(scores, indent=4))
    print("  overall:", overall)
    print("  passed:", passed)
    # Also run one with a wrong intent to show partial score
    result_bad = {
        "intent": "general",
        "tools_called": case.get("expected_tools", []),
        "response": {"summary": "Trend and volatility are present.", "confidence": 70},
        "tool_results": {},
    }
    scores_bad, overall_bad, passed_bad = score_case(case, result_bad)
    print("\nSample score (wrong intent):")
    print("  scores:", json.dumps(scores_bad, indent=4))
    print("  overall:", overall_bad)
    print("  passed:", passed_bad)


if __name__ == "__main__":
    main()
