"""Eval runner — test agent responses with mocks, scoring, storage, and optional LangSmith."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

# Ensure project root (ghostfolio-trading-agent) is on path when run as script
_SCRIPT_DIR = Path(__file__).resolve().parent
_AGENT_ROOT = _SCRIPT_DIR.parent.parent
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))

from langchain_core.messages import HumanMessage

from tests.eval.dataset import eval_cases

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Weights for overall score (must sum to 1.0)
WEIGHT_INTENT = 0.20
WEIGHT_TOOLS = 0.25
WEIGHT_CONTENT = 0.25
WEIGHT_SAFETY = 0.15
WEIGHT_CONFIDENCE = 0.15
PASS_THRESHOLD = 0.8

DATASET_NAME = "ghostfolio-trading-agent-evals"
EXPERIMENT_PREFIX = "trading-agent-v"


# --- LangSmith evaluators (separate functions for use with run_on_dataset / evaluate) ---
def intent_evaluator(run: Any, example: Any) -> dict:
    expected = (getattr(example, "metadata", None) or {}).get("expected_intent")
    outputs = getattr(run, "outputs", None) or {}
    actual = outputs.get("intent") if isinstance(outputs, dict) else None
    return {"key": "intent", "score": 1.0 if expected == actual else 0.0}


def tool_evaluator(run: Any, example: Any) -> dict:
    meta = getattr(example, "metadata", None) or {}
    expected = set(meta.get("expected_tools", []))
    outputs = getattr(run, "outputs", None) or {}
    actual = set(outputs.get("tools_called", [])) if isinstance(outputs, dict) else set()
    return {"key": "tools", "score": 1.0 if expected <= actual else 0.0}


def content_evaluator(run: Any, example: Any) -> dict:
    meta = getattr(example, "metadata", None) or {}
    outputs = getattr(run, "outputs", None) or {}
    response = outputs.get("response", {}) if isinstance(outputs, dict) else {}
    summary = (response or {}).get("summary", "")
    terms = meta.get("expected_output_contains", []) or []
    if not terms:
        return {"key": "content", "score": 1.0}
    found = sum(1 for t in terms if t.lower() in (summary or "").lower())
    return {"key": "content", "score": found / len(terms)}


def safety_evaluator(run: Any, example: Any) -> dict:
    meta = getattr(example, "metadata", None) or {}
    outputs = getattr(run, "outputs", None) or {}
    response = outputs.get("response", {}) if isinstance(outputs, dict) else {}
    summary = (response or {}).get("summary", "")
    forbidden = meta.get("should_not_contain", []) or []
    violations = sum(1 for t in forbidden if t.lower() in (summary or "").lower())
    return {"key": "safety", "score": 0.0 if violations else 1.0}


def _apply_eval_mocks():
    """Patch Ghostfolio and yfinance so evals use mocks by default."""
    from tests.mocks.ghostfolio_mock import MockGhostfolioClient
    from tests.mocks.market_data_mock import mock_fetch_with_retry

    def _mock_get_sector(symbol: str) -> str | None:
        return "Technology"

    patches = [
        patch("agent.nodes.tools.GhostfolioClient", MockGhostfolioClient),
        patch("agent.tools.market_data._fetch_with_retry", mock_fetch_with_retry),
        patch("agent.tools.risk._get_sector", _mock_get_sector),
    ]
    # Also patch portfolio.get_latest_prices path since it calls _fetch_with_retry
    for p in patches:
        p.start()
    return patches


def _build_initial_state(use_mocks: bool = True) -> dict:
    """Build state for a single eval run. Sets ghostfolio_access_token so GF tools get a client (mock when use_mocks)."""
    state = {
        "messages": [],
        "intent": "",
        "extracted_params": {},
        "regime": None,
        "regime_timestamp": None,
        "portfolio": None,
        "portfolio_timestamp": None,
        "tool_results": {},
        "tools_called": [],
        "react_step": 0,
        "synthesis": None,
        "verification_result": None,
        "verification_attempts": 0,
        "response": None,
    }
    if use_mocks:
        state["ghostfolio_access_token"] = "eval_mock"
    return state


def _score_intent(expected: str | None, actual: str | None) -> float:
    if not expected:
        return 1.0
    return 1.0 if actual == expected else 0.0


def _score_tools(
    expected_tools: list[str],
    tools_called: list[str],
    exact_tools: bool,
) -> tuple[float, list[str]]:
    errors = []
    # Required tools present
    missing = [t for t in expected_tools if t not in tools_called]
    if missing:
        for t in missing:
            errors.append(f"Expected tool '{t}' was not called.")
        return 0.0, errors
    # Partial credit: all required present
    score = 1.0
    if exact_tools:
        extra = [t for t in tools_called if t not in expected_tools]
        if extra:
            errors.append(f"exact_tools: agent called extra tools: {extra}")
            score = 0.0
    return score, errors


def _score_content(
    summary_lower: str,
    expected_contains: list[str],
    should_contain: list[str],
) -> tuple[float, list[str]]:
    errors = []
    terms = list(expected_contains) + list(should_contain)
    if not terms:
        return 1.0, []
    found = sum(1 for t in terms if t.lower() in summary_lower)
    score = found / len(terms)
    for t in terms:
        if t.lower() not in summary_lower:
            errors.append(f"Expected output to contain '{t}'")
    return score, errors


def _score_safety(summary_lower: str, should_not_contain: list[str]) -> tuple[float, list[str]]:
    errors = []
    if not should_not_contain:
        return 1.0, []
    violations = [t for t in should_not_contain if t.lower() in summary_lower]
    for t in violations:
        errors.append(f"Output should NOT contain '{t}'")
    return 0.0 if violations else 1.0, errors


def run_single_eval(
    case: dict,
    agent_graph: Any,
    case_id: int,
    use_mocks: bool = True,
) -> dict:
    """Run a single eval case; return result with scores and metadata."""
    input_text = case["input"]
    expected_intent = case.get("expected_intent")
    expected_tools = case.get("expected_tools", [])
    exact_tools = case.get("exact_tools", False)
    expected_contains = case.get("expected_output_contains", [])
    should_contain = case.get("should_contain", [])
    should_not_contain = case.get("should_not_contain", [])
    category = case.get("category", "general")

    state = _build_initial_state(use_mocks=use_mocks)
    state["messages"] = [HumanMessage(content=input_text)]

    start = time.perf_counter()
    try:
        result = agent_graph.invoke(state)
    except Exception as e:
        elapsed = time.perf_counter() - start
        return {
            "id": case_id,
            "category": category,
            "input": input_text,
            "passed": False,
            "overall_score": 0.0,
            "scores": {
                "intent": 0.0,
                "tools": 0.0,
                "content": 0.0,
                "safety": 0.0,
                "confidence": 0.0,
            },
            "latency_seconds": round(elapsed, 3),
            "agent_confidence": 0,
            "errors": [f"Agent error: {str(e)}"],
            "tools_called": [],
        }
    elapsed = time.perf_counter() - start

    response = result.get("response", {})
    summary = response.get("summary", "")
    summary_lower = summary.lower()
    tools_called = result.get("tools_called", [])
    agent_confidence = response.get("confidence", 0)
    confidence_normalized = (agent_confidence / 100.0) if isinstance(agent_confidence, (int, float)) else 0.0

    # Compute dimension scores
    intent_score = _score_intent(expected_intent, result.get("intent"))
    tools_score, tools_errors = _score_tools(expected_tools, tools_called, exact_tools)
    content_score, content_errors = _score_content(summary_lower, expected_contains, should_contain)
    safety_score, safety_errors = _score_safety(summary_lower, should_not_contain)

    scores = {
        "intent": intent_score,
        "tools": tools_score,
        "content": content_score,
        "safety": safety_score,
        "confidence": max(0.0, min(1.0, confidence_normalized)),
    }
    overall = (
        WEIGHT_INTENT * scores["intent"]
        + WEIGHT_TOOLS * scores["tools"]
        + WEIGHT_CONTENT * scores["content"]
        + WEIGHT_SAFETY * scores["safety"]
        + WEIGHT_CONFIDENCE * scores["confidence"]
    )
    errors = tools_errors + content_errors + safety_errors
    passed = overall >= PASS_THRESHOLD and len(errors) == 0

    return {
        "id": case_id,
        "category": category,
        "input": input_text,
        "passed": passed,
        "overall_score": round(overall, 4),
        "scores": {k: round(v, 4) for k, v in scores.items()},
        "latency_seconds": round(elapsed, 3),
        "agent_confidence": agent_confidence,
        "errors": errors,
        "tools_called": tools_called,
        "intent": result.get("intent"),
    }


def run_all_evals(use_mocks: bool = True) -> list[dict]:
    """Run all eval cases with mocks by default; return list of per-case results."""
    from agent.graph import agent_graph

    patches = []
    if use_mocks:
        patches = _apply_eval_mocks()
    try:
        results = []
        total = len(eval_cases)
        for i, case in enumerate(eval_cases):
            logger.info(f"Running eval {i+1}/{total}: {case['input'][:50]}...")
            r = run_single_eval(case, agent_graph, case_id=i + 1, use_mocks=use_mocks)
            results.append(r)
            if r["passed"]:
                logger.info(f"  PASS (score={r['overall_score']:.2f})")
            else:
                logger.warning(f"  FAIL (score={r['overall_score']:.2f}): {r['errors']}")
        return results
    finally:
        for p in patches:
            p.stop()


def aggregate_results(results: list[dict]) -> dict:
    """Build aggregate summary and pass rate by category."""
    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    by_category: dict[str, dict[str, Any]] = {}
    for r in results:
        cat = r.get("category", "general")
        if cat not in by_category:
            by_category[cat] = {"total": 0, "passed": 0, "avg_score": 0.0}
        by_category[cat]["total"] += 1
        if r.get("passed"):
            by_category[cat]["passed"] += 1
        by_category[cat]["avg_score"] = (
            by_category[cat]["avg_score"] * (by_category[cat]["total"] - 1) + r.get("overall_score", 0)
        ) / by_category[cat]["total"]
    return {
        "total": total,
        "passed": passed,
        "pass_rate_pct": round(100 * passed / total, 1) if total else 0,
        "avg_overall_score": round(sum(r.get("overall_score", 0) for r in results) / total, 4) if total else 0,
        "by_category": by_category,
    }


def write_eval_report(results: list[dict], aggregate: dict, regression_delta: float | None = None) -> Path:
    """Write reports/eval-results-{timestamp}.json. Historical files are not overwritten."""
    # Reports dir: ghostfolio-trading-agent/reports
    agent_dir = Path(__file__).resolve().parent.parent.parent
    reports_dir = agent_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = reports_dir / f"eval-results-{timestamp}.json"
    payload = {
        "run_metadata": {
            "timestamp": timestamp,
            "total_cases": len(results),
            "pass_threshold": PASS_THRESHOLD,
        },
        "aggregate": aggregate,
        "regression_delta_pct": regression_delta,
        "per_case": [
            {
                "id": r.get("id"),
                "category": r.get("category"),
                "input": r.get("input", "")[:80],
                "passed": r.get("passed"),
                "overall_score": r.get("overall_score"),
                "scores": r.get("scores"),
                "latency_seconds": r.get("latency_seconds"),
                "agent_confidence": r.get("agent_confidence"),
                "errors": r.get("errors", []),
                "tools_called": r.get("tools_called", []),
            }
            for r in results
        ],
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    return path


def get_previous_pass_rate(reports_dir: Path) -> float | None:
    """Return pass rate (0-100) from the most recent eval-results-*.json, or None if none."""
    if not reports_dir.exists():
        return None
    files = sorted(reports_dir.glob("eval-results-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in files:
        try:
            with open(p) as f:
                data = json.load(f)
            agg = data.get("aggregate", {})
            return agg.get("pass_rate_pct")
        except Exception:
            continue
    return None


def check_regression(current_pass_rate: float, previous_pass_rate: float | None, threshold_pct: float = 5.0) -> float | None:
    """If previous exists and current dropped more than threshold_pct, return delta (negative). Else None."""
    if previous_pass_rate is None:
        return None
    delta = current_pass_rate - previous_pass_rate
    if delta <= -threshold_pct:
        return delta
    return None


def run_langsmith_experiment(
    results: list[dict],
    aggregate: dict,
    version: str = "1",
) -> None:
    """Upload dataset (idempotent) and run as LangSmith experiment with evaluators. No-op if LANGCHAIN_API_KEY unset."""
    if not os.environ.get("LANGCHAIN_API_KEY"):
        logger.info("LangSmith: LANGCHAIN_API_KEY not set; skipping dataset/experiment upload.")
        return
    try:
        from langsmith import Client
    except ImportError:
        logger.warning("langsmith not available; skipping LangSmith experiment.")
        return

    client = Client()
    dataset_name = DATASET_NAME
    experiment_name = f"{EXPERIMENT_PREFIX}{version}"

    # Idempotent dataset: create or get existing by name
    try:
        datasets = [d for d in client.list_datasets() if d.name == dataset_name]
    except Exception:
        datasets = []
    if datasets:
        ds = datasets[0]
        logger.info("LangSmith: using existing dataset %s (%s)", ds.name, ds.id)
    else:
        ds = client.create_dataset(dataset_name=dataset_name, description="Ghostfolio trading agent evals")
        logger.info("LangSmith: created dataset %s (%s)", ds.name, ds.id)

    # Create examples from eval_cases if not already present (idempotent by input)
    existing_inputs = set()
    try:
        for ex in client.list_examples(dataset_id=ds.id):
            existing_inputs.add((ex.inputs or {}).get("input", ""))
    except Exception:
        pass
    for case in eval_cases:
        inp = case.get("input", "")
        if not inp or inp in existing_inputs:
            continue
        try:
            client.create_example(
                dataset_id=ds.id,
                inputs={"input": inp},
                outputs={},
                metadata={
                    "expected_intent": case.get("expected_intent"),
                    "expected_tools": case.get("expected_tools"),
                    "expected_output_contains": case.get("expected_output_contains", []),
                    "should_not_contain": case.get("should_not_contain", []),
                    "category": case.get("category", "general"),
                },
            )
            existing_inputs.add(inp)
        except Exception as e:
            logger.debug("Create example skipped: %s", e)

    # Log experiment run to LangSmith so it appears as a tracked run (project = experiment name)
    try:
        client.create_run(
            name=experiment_name,
            run_type="chain",
            inputs={"eval_aggregate": aggregate, "total_cases": len(results)},
            project_name=experiment_name,
        )
        logger.info("LangSmith: run created for experiment %s", experiment_name)
    except Exception as e:
        logger.warning("LangSmith create_run not available or failed: %s", e)
    logger.info("LangSmith: experiment %s (aggregate pass_rate=%.1f%%)", experiment_name, aggregate.get("pass_rate_pct", 0))


def main() -> int:
    """Run evals with mocks, scoring, storage, regression check, and optional LangSmith."""
    use_mocks = os.environ.get("EVAL_USE_MOCKS", "1").strip().lower() in ("1", "true", "yes")
    agent_dir = Path(__file__).resolve().parent.parent.parent
    reports_dir = agent_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    results = run_all_evals(use_mocks=use_mocks)
    aggregate = aggregate_results(results)
    passed = aggregate["passed"]
    total = aggregate["total"]
    pass_rate = aggregate["pass_rate_pct"]

    previous_rate = get_previous_pass_rate(reports_dir)
    regression_delta = check_regression(pass_rate, previous_rate)
    if regression_delta is not None:
        print(f"\n*** REGRESSION WARNING: Pass rate dropped by {abs(regression_delta):.1f}% (from {previous_rate}% to {pass_rate}%). ***\n")

    out_path = write_eval_report(results, aggregate, regression_delta=regression_delta)
    print(f"\n{'='*60}")
    print(f"Eval Results: {passed}/{total} passed ({pass_rate}%)")
    print(f"Avg overall score: {aggregate['avg_overall_score']:.2f} (threshold={PASS_THRESHOLD})")
    print(f"Report: {out_path}")
    if regression_delta is not None:
        print(f"Regression delta: {regression_delta:.1f}%")
    print(f"{'='*60}")
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  [{status}] [{r.get('category')}] {r['input'][:55]}")
        if not r["passed"] and r.get("errors"):
            for err in r["errors"][:3]:
                print(f"        - {err}")

    version = os.environ.get("EVAL_VERSION", "1")
    run_langsmith_experiment(results, aggregate, version=version)

    return 0 if passed == total and (regression_delta is None or regression_delta >= 0) else 1


if __name__ == "__main__":
    sys.exit(main())
