"""Eval runner — test agent responses with mocks, scoring, storage, and optional LangSmith.

Reproducibility: set EVAL_MODE=1 (or "true") so synthesis uses temperature 0 and evals are deterministic.
"""

from __future__ import annotations

import argparse
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
WEIGHT_CONTENT = 0.15
WEIGHT_SAFETY = 0.15
WEIGHT_CONFIDENCE = 0.15
WEIGHT_VERIFICATION = 0.10
PASS_THRESHOLD = 0.8
TARGET_PASS_RATE_PCT = 80

MAX_LATENCY_SECONDS = float(os.environ.get("EVAL_MAX_LATENCY_SECONDS", "120"))

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
        "skip_synthesis": False,
        "verification_result": None,
        "verification_attempts": 0,
        "response": None,
        "token_usage": {},
        "node_latencies": {},
        "error_log": [],
        "trace_log": [],
    }
    if use_mocks:
        state["ghostfolio_access_token"] = "eval_mock"
    else:
        from agent.config import get_settings
        token = (os.environ.get("GHOSTFOLIO_ACCESS_TOKEN") or get_settings().ghostfolio_access_token or "").strip()
        state["ghostfolio_access_token"] = token or None
    return state


INTENT_EQUIVALENCE: dict[str, set[str]] = {
    "portfolio_health": {"portfolio_overview", "risk_check"},
    "performance_review": {"journal_analysis"},
    "tax_implications": {"general", "compliance"},
    "compliance": {"risk_check", "general", "tax_implications"},
    "multi_step": {
        "risk_check", "portfolio_overview", "general",
        "portfolio_health", "performance_review",
        "tax_implications", "compliance", "journal_analysis",
    },
    "journal_analysis": {"performance_review"},
}


def _score_intent(expected: str | None, actual: str | None) -> float:
    if not expected:
        return 1.0
    if actual == expected:
        return 1.0
    equivalents = INTENT_EQUIVALENCE.get(expected, set())
    if actual in equivalents:
        return 1.0
    return 0.0


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


# Synonyms for content scoring: term -> alternative that also counts as found
CONTENT_SYNONYMS = {
    "win_rate": "win rate",
    "win rate": "win_rate",
    "recorded": "logged",
    "logged": "recorded",
    "not financial advice": "not advice",
    "not advice": "not financial advice",
    "informational only": "not financial advice",
    "allocation": "diversification",
    "diversification": "allocation",
    "concentration": "concentrated",
    "concentrated": "concentration",
    "capital gains": "capital gain",
    "capital gain": "capital gains",
    "wash sale": "wash-sale",
    "wash-sale": "wash sale",
    "cannot guarantee": "no guarantee",
    "no guarantee": "cannot guarantee",
    "symbol": "ticker",
    "ticker": "symbol",
    "stock": "ticker",
}


def _score_content(
    summary_lower: str,
    expected_contains: list[str],
    should_contain: list[str],
) -> tuple[float, list[str]]:
    errors = []
    terms = list(expected_contains) + list(should_contain)
    if not terms:
        return 1.0, []

    def _term_found(term: str) -> bool:
        t = term.lower()
        if t in summary_lower:
            return True
        alt = CONTENT_SYNONYMS.get(t)
        return bool(alt and alt in summary_lower)

    found = sum(1 for t in terms if _term_found(t))
    score = found / len(terms)
    for t in terms:
        if not _term_found(t):
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


def _score_tool_execution(tool_results: dict) -> tuple[float, list[str]]:
    """Score 0 if any tool returned an error dict, 1 otherwise."""
    errors = []
    for tool_name, data in tool_results.items():
        if isinstance(data, dict) and data.get("error"):
            errors.append(f"Tool '{tool_name}' failed: {data['error']}")
    return (0.0 if errors else 1.0), errors


def _score_verification(verification_result: dict | None) -> float:
    """1.0 if verification passed (or was not run), 0.0 if it explicitly failed."""
    if not verification_result:
        return 1.0
    return 1.0 if verification_result.get("passed", True) else 0.0


def _score_ground_truth(summary_lower: str, ground_truth_contains: list[str]) -> tuple[float, list[str]]:
    """Check that known ground-truth values appear in the summary."""
    if not ground_truth_contains:
        return 1.0, []
    errors = []
    found = 0
    for gt in ground_truth_contains:
        if str(gt).lower() in summary_lower:
            found += 1
        else:
            errors.append(f"Ground truth '{gt}' not found in output")
    score = found / len(ground_truth_contains)
    return score, errors


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
    ground_truth_contains = case.get("ground_truth_contains", [])
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
                "verification": 0.0,
            },
            "latency_seconds": round(elapsed, 3),
            "latency_passed": False,
            "verification_passed": None,
            "tool_errors": [],
            "agent_confidence": 0,
            "errors": [f"Agent error: {str(e)}"],
            "tools_called": [],
            "intent": "",
            "response": {},
        }
    elapsed = time.perf_counter() - start

    response = result.get("response", {})
    summary = response.get("summary", "")
    summary_lower = summary.lower()
    tools_called = result.get("tools_called", [])
    tool_results = result.get("tool_results", {})
    verification_result = result.get("verification_result")
    agent_confidence = response.get("confidence", 0)
    confidence_normalized = (agent_confidence / 100.0) if isinstance(agent_confidence, (int, float)) else 0.0

    # Compute dimension scores
    intent_score = _score_intent(expected_intent, result.get("intent"))
    tools_score, tools_errors = _score_tools(expected_tools, tools_called, exact_tools)
    tool_exec_score, tool_exec_errors = _score_tool_execution(tool_results)
    # When live run and case is not live_safe, skip content assertions and only check tools
    skip_content_assertions = (not use_mocks) and (case.get("live_safe", True) is False)
    if skip_content_assertions:
        content_score, content_errors = 1.0, []
        gt_score, gt_errors = 1.0, []
    else:
        content_score, content_errors = _score_content(summary_lower, expected_contains, should_contain)
        gt_score, gt_errors = _score_ground_truth(summary_lower, ground_truth_contains)
    safety_score, safety_errors = _score_safety(summary_lower, should_not_contain)
    verification_score = _score_verification(verification_result)

    # Tool execution domain errors (e.g. "You do not hold X") are informational —
    # they indicate correct tool behavior, not misuse. Only override tools_score
    # when the expected tools themselves were NOT called (tools_errors already captures that).
    # tool_exec_errors are reported in tool_errors but don't block passing.

    # Ground-truth failures reduce content score (only when not skipping content)
    if ground_truth_contains and not skip_content_assertions:
        content_score = (content_score + gt_score) / 2.0

    scores = {
        "intent": intent_score,
        "tools": tools_score,
        "content": content_score,
        "safety": safety_score,
        "confidence": max(0.0, min(1.0, confidence_normalized)),
        "verification": verification_score,
    }
    overall = (
        WEIGHT_INTENT * scores["intent"]
        + WEIGHT_TOOLS * scores["tools"]
        + WEIGHT_CONTENT * scores["content"]
        + WEIGHT_SAFETY * scores["safety"]
        + WEIGHT_CONFIDENCE * scores["confidence"]
        + WEIGHT_VERIFICATION * scores["verification"]
    )

    # Hard errors: wrong tools, missing content, safety violations, ground-truth mismatches
    errors = tools_errors + content_errors + safety_errors + gt_errors

    latency_passed = elapsed <= MAX_LATENCY_SECONDS
    if not latency_passed:
        errors.append(f"Latency {elapsed:.1f}s exceeds max {MAX_LATENCY_SECONDS}s")

    # Verification failures affect the score through the verification dimension
    # but are not hard-blocking — the agent may synthesize from partial data
    # when a tool returns a domain error (e.g. "You do not hold X").
    v_passed = verification_result.get("passed", True) if verification_result else None

    passed = overall >= PASS_THRESHOLD and len(errors) == 0

    return {
        "id": case_id,
        "category": category,
        "input": input_text,
        "passed": passed,
        "overall_score": round(overall, 4),
        "scores": {k: round(v, 4) for k, v in scores.items()},
        "latency_seconds": round(elapsed, 3),
        "latency_passed": latency_passed,
        "verification_passed": v_passed,
        "tool_errors": [e for e in tool_exec_errors],
        "agent_confidence": agent_confidence,
        "errors": errors,
        "tools_called": tools_called,
        "intent": result.get("intent"),
        "response": response,
    }


def run_all_evals(use_mocks: bool = True, eval_cases_list: list[dict] | None = None) -> list[dict]:
    """Run eval cases with mocks by default; return list of per-case results.

    eval_cases_list: if provided, run only these cases (e.g. filtered by --phase); else use dataset.eval_cases.
    """
    from agent.graph import agent_graph

    cases = eval_cases_list if eval_cases_list is not None else eval_cases
    patches = []
    if use_mocks:
        patches = _apply_eval_mocks()
    try:
        results = []
        total = len(cases)
        for i, case in enumerate(cases):
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


def run_consistency_check(
    num_runs: int = 2,
    use_mocks: bool = True,
) -> list[dict]:
    """Run a subset of eval cases multiple times and compare outputs for determinism."""
    from agent.graph import agent_graph

    CONSISTENCY_CATEGORIES = {"regime_check", "price_quote", "general", "portfolio_overview"}
    subset = [c for c in eval_cases if c.get("category") in CONSISTENCY_CATEGORIES][:5]

    if not subset:
        logger.info("Consistency: no cases matched; skipping.")
        return []

    patches = []
    if use_mocks:
        patches = _apply_eval_mocks()
    try:
        results = []
        for i, case in enumerate(subset):
            runs: list[dict] = []
            for run_idx in range(num_runs):
                r = run_single_eval(case, agent_graph, case_id=i + 1, use_mocks=use_mocks)
                runs.append(r)

            consistency_errors = []
            base = runs[0]
            for run_idx in range(1, num_runs):
                comp = runs[run_idx]
                if base.get("intent") != comp.get("intent"):
                    consistency_errors.append(
                        f"Run {run_idx}: intent '{comp.get('intent')}' differs from run 0 '{base.get('intent')}'"
                    )
                if sorted(base.get("tools_called", [])) != sorted(comp.get("tools_called", [])):
                    consistency_errors.append(
                        f"Run {run_idx}: tools_called {comp.get('tools_called')} differs from run 0 {base.get('tools_called')}"
                    )

            results.append({
                "id": i + 1,
                "input": case["input"],
                "category": case.get("category", "general"),
                "consistency_passed": len(consistency_errors) == 0,
                "consistency_errors": consistency_errors,
                "num_runs": num_runs,
            })
            status = "PASS" if not consistency_errors else "FAIL"
            logger.info(f"  Consistency [{status}] {case['input'][:50]}")
        return results
    finally:
        for p in patches:
            p.stop()


def aggregate_results(results: list[dict]) -> dict:
    """Build aggregate summary, pass rate by category, and per-dimension averages by category."""
    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    by_category: dict[str, dict[str, Any]] = {}
    for r in results:
        cat = r.get("category", "general")
        if cat not in by_category:
            by_category[cat] = {
                "total": 0,
                "passed": 0,
                "avg_score": 0.0,
                "avg_intent": 0.0,
                "avg_tools": 0.0,
                "avg_content": 0.0,
                "avg_safety": 0.0,
                "avg_confidence": 0.0,
                "avg_verification": 0.0,
            }
        by_category[cat]["total"] += 1
        if r.get("passed"):
            by_category[cat]["passed"] += 1
        s = r.get("overall_score", 0)
        sc = r.get("scores") or {}
        n = by_category[cat]["total"]
        by_category[cat]["avg_score"] = (by_category[cat]["avg_score"] * (n - 1) + s) / n
        for key in ("intent", "tools", "content", "safety", "confidence", "verification"):
            v = sc.get(key, 0)
            by_category[cat][f"avg_{key}"] = (by_category[cat][f"avg_{key}"] * (n - 1) + v) / n
    return {
        "total": total,
        "passed": passed,
        "pass_rate_pct": round(100 * passed / total, 1) if total else 0,
        "avg_overall_score": round(sum(r.get("overall_score", 0) for r in results) / total, 4) if total else 0,
        "by_category": by_category,
    }


def write_eval_report(
    results: list[dict],
    aggregate: dict,
    regression_delta: float | None = None,
    consistency_results: list[dict] | None = None,
) -> Path:
    """Write reports/eval-results-{timestamp}.json. Historical files are not overwritten."""
    agent_dir = Path(__file__).resolve().parent.parent.parent
    reports_dir = agent_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = reports_dir / f"eval-results-{timestamp}.json"
    pass_rate = aggregate.get("pass_rate_pct", 0)
    payload = {
        "run_metadata": {
            "timestamp": timestamp,
            "total_cases": len(results),
            "pass_threshold": PASS_THRESHOLD,
            "target_pass_rate_pct": TARGET_PASS_RATE_PCT,
            "target_met": pass_rate >= TARGET_PASS_RATE_PCT,
            "max_latency_seconds": MAX_LATENCY_SECONDS,
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
                "latency_passed": r.get("latency_passed"),
                "verification_passed": r.get("verification_passed"),
                "tool_errors": r.get("tool_errors", []),
                "agent_confidence": r.get("agent_confidence"),
                "errors": r.get("errors", []),
                "tools_called": r.get("tools_called", []),
            }
            for r in results
        ],
    }
    if consistency_results is not None:
        payload["consistency"] = consistency_results
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    return path


def get_previous_pass_rate(reports_dir: Path, total_cases: int | None = None) -> float | None:
    """Return pass_rate_pct (0-100) from the most recent eval-results-*.json with same total_cases if given."""
    if not reports_dir.exists():
        return None
    files = sorted(reports_dir.glob("eval-results-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in files:
        try:
            with open(p) as f:
                data = json.load(f)
            run_meta = data.get("run_metadata", {})
            if total_cases is not None and run_meta.get("total_cases") != total_cases:
                continue
            agg = data.get("aggregate", {})
            return agg.get("pass_rate_pct")
        except Exception:
            continue
    return None


def check_regression(current_pass_rate: float, previous_pass_rate: float | None) -> float | None:
    """Return regression_delta_pct = current - previous when previous exists, else None."""
    if previous_pass_rate is None:
        return None
    return round(current_pass_rate - previous_pass_rate, 1)


def run_langsmith_experiment(
    results: list[dict],
    aggregate: dict,
    version: str = "1",
) -> str | None:
    """Upload dataset (idempotent), run LangSmith evaluate() with replay of pre-computed results.

    Uses the evaluate() API so the experiment appears in Datasets & Experiments UI.
    No second agent run — replay_target returns results from run_all_evals().
    Returns the experiment URL if successful, None otherwise.
    Silently no-ops when LANGCHAIN_API_KEY is not set.
    """
    from agent.config import get_settings

    api_key = os.environ.get("LANGCHAIN_API_KEY") or get_settings().langchain_api_key
    if not api_key:
        return None
    os.environ.setdefault("LANGCHAIN_API_KEY", api_key)

    try:
        from langsmith import Client, evaluate  # noqa: WPS433
    except ImportError:
        logger.warning("langsmith package not installed; skipping LangSmith experiment.")
        return None

    client = Client()

    # ---- 1. Idempotent dataset (extended outputs for evaluators) --------------
    try:
        ds = client.read_dataset(dataset_name=DATASET_NAME)
        logger.info("LangSmith: reusing dataset '%s'", DATASET_NAME)
    except Exception:
        ds = client.create_dataset(
            dataset_name=DATASET_NAME,
            description="Ghostfolio trading agent eval cases",
        )
        logger.info("LangSmith: created dataset '%s'", DATASET_NAME)

    existing_queries: set[str] = set()
    try:
        for ex in client.list_examples(dataset_id=ds.id):
            existing_queries.add((ex.inputs or {}).get("query", ""))
    except Exception:
        pass

    added = 0
    for case in eval_cases:
        query = case.get("input", "")
        if query in existing_queries:
            continue
        try:
            client.create_example(
                dataset_id=ds.id,
                inputs={"query": query},
                outputs={
                    "expected_intent": case.get("expected_intent", ""),
                    "expected_tools": case.get("expected_tools", []),
                    "expected_output_contains": case.get("expected_output_contains", []),
                    "should_not_contain": case.get("should_not_contain", []),
                    "confidence_min": case.get("confidence_min", 0),
                },
            )
            existing_queries.add(query)
            added += 1
        except Exception as exc:
            logger.debug("LangSmith: example upload skipped: %s", exc)
    if added:
        logger.info("LangSmith: uploaded %d new example(s)", added)

    # ---- 2. Replay target (no second agent call) -------------------------------
    results_by_query = {r["input"]: r for r in results}

    def replay_target(inputs: dict) -> dict:
        result = results_by_query.get(inputs.get("query", ""), {})
        response = result.get("response", {}) or {}
        return {
            "intent": result.get("intent", ""),
            "tools_called": result.get("tools_called", []),
            "summary": response.get("summary", ""),
            "confidence": response.get("confidence", 0),
            "overall_score": result.get("overall_score", 0.0),
            "passed": result.get("passed", False),
        }

    # ---- 3. Evaluators (run.outputs and example.outputs) ----------------------
    def _outputs(run: Any) -> dict:
        return getattr(run, "outputs", None) or {}

    def _example_outputs(example: Any) -> dict:
        return getattr(example, "outputs", None) or {}

    def _intent_evaluator(run: Any, example: Any) -> dict:
        predicted = _outputs(run).get("intent", "")
        expected = _example_outputs(example).get("expected_intent", "")
        return {"key": "intent_score", "score": 1.0 if predicted == expected else 0.0}

    def _tools_evaluator(run: Any, example: Any) -> dict:
        expected = set(_example_outputs(example).get("expected_tools", []))
        actual = set(_outputs(run).get("tools_called", []))
        if not expected:
            return {"key": "tools_score", "score": 1.0}
        return {"key": "tools_score", "score": len(expected & actual) / len(expected)}

    def _content_evaluator(run: Any, example: Any) -> dict:
        terms = _example_outputs(example).get("expected_output_contains", [])
        summary = (_outputs(run).get("summary", "") or "").lower()
        if not terms:
            return {"key": "content_score", "score": 1.0}
        hits = sum(1 for t in terms if (t or "").lower() in summary)
        return {"key": "content_score", "score": hits / len(terms)}

    def _safety_evaluator(run: Any, example: Any) -> dict:
        forbidden = _example_outputs(example).get("should_not_contain", [])
        summary = (_outputs(run).get("summary", "") or "").lower()
        violations = [t for t in forbidden if (t or "").lower() in summary]
        return {"key": "safety_score", "score": 0.0 if violations else 1.0}

    def _confidence_evaluator(run: Any, example: Any) -> dict:
        confidence = _outputs(run).get("confidence", 0)
        min_conf = _example_outputs(example).get("confidence_min", 0)
        return {"key": "confidence_score", "score": 1.0 if confidence >= min_conf else 0.0}

    def _overall_evaluator(run: Any, example: Any) -> dict:
        return {"key": "overall_score", "score": float(_outputs(run).get("overall_score", 0.0))}

    evaluators = [
        _intent_evaluator,
        _tools_evaluator,
        _content_evaluator,
        _safety_evaluator,
        _confidence_evaluator,
        _overall_evaluator,
    ]

    # ---- 4. Run evaluate() ----------------------------------------------------
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    experiment_prefix = f"{EXPERIMENT_PREFIX}{version}"
    try:
        experiment_results = evaluate(
            replay_target,
            data=DATASET_NAME,
            evaluators=evaluators,
            experiment_prefix=experiment_prefix,
            metadata={
                "version": version,
                "timestamp": ts,
                "pass_rate": aggregate.get("pass_rate_pct"),
                "total_cases": aggregate.get("total"),
            },
            client=client,
        )
    except Exception as exc:
        logger.warning("LangSmith evaluate() failed: %s", exc)
        return None

    # ---- 5. Resolve and return experiment URL ---------------------------------
    # Build a Datasets & Experiments URL so the experiment is findable from
    # the dataset dashboard (not just as a hidden project).
    # Format: /o/{org_id}/datasets/{dataset_id}/compare?selectedSessions={experiment_id}
    experiment_url: str | None = None
    try:
        exp_name = getattr(experiment_results, "experiment_name", None)
        if exp_name:
            project = client.read_project(project_name=exp_name)
            org_id = getattr(project, "tenant_id", None)
            if org_id and ds.id and project.id:
                experiment_url = (
                    f"https://smith.langchain.com/o/{org_id}/datasets/{ds.id}"
                    f"/compare?selectedSessions={project.id}"
                )
            else:
                experiment_url = f"https://smith.langchain.com/projects/p/{project.id}"
        if not experiment_url:
            experiment_url = "https://smith.langchain.com/projects"
    except Exception:
        experiment_url = experiment_url or "https://smith.langchain.com/projects"

    logger.info(
        "LangSmith: experiment '%s' logged (pass_rate=%.1f%%)",
        experiment_prefix,
        aggregate.get("pass_rate_pct", 0),
    )
    return experiment_url


def main() -> int:
    """Run evals with mocks, scoring, storage, regression check, consistency, and optional LangSmith."""
    parser = argparse.ArgumentParser(description="Run Ghostfolio trading agent evals")
    parser.add_argument(
        "--phase",
        type=int,
        default=1,
        help="Run only cases with this phase (1=Phase 1 long-term investor, 2=regime/scan). Default: 1",
    )
    args = parser.parse_args()
    phase = args.phase

    use_mocks = os.environ.get("EVAL_USE_MOCKS", "1").strip().lower() in ("1", "true", "yes")
    consistency_runs = int(os.environ.get("EVAL_CONSISTENCY_RUNS", "0"))
    agent_dir = Path(__file__).resolve().parent.parent.parent
    reports_dir = agent_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    # When running live, print which Ghostfolio token is in use (masked) so seed vs eval mismatches are visible
    if not use_mocks:
        from agent.config import get_settings
        token = (os.environ.get("GHOSTFOLIO_ACCESS_TOKEN") or get_settings().ghostfolio_access_token or "").strip()
        if token:
            mask = f"{token[:4]}...{token[-4:]}" if len(token) >= 10 else "***"
            print(f"EVAL_USE_MOCKS=0: using GHOSTFOLIO_ACCESS_TOKEN ({mask})")
        else:
            print("EVAL_USE_MOCKS=0: GHOSTFOLIO_ACCESS_TOKEN is unset (Ghostfolio tools may fail)")

    # Filter to cases matching the requested phase
    filtered_cases = [c for c in eval_cases if c.get("phase", 1) == phase]
    logger.info("Running %d cases for phase=%d (total dataset=%d)", len(filtered_cases), phase, len(eval_cases))

    results = run_all_evals(use_mocks=use_mocks, eval_cases_list=filtered_cases)
    aggregate = aggregate_results(results)
    passed = aggregate["passed"]
    total = aggregate["total"]
    pass_rate = aggregate["pass_rate_pct"]

    # Optional consistency check
    consistency_results: list[dict] | None = None
    if consistency_runs >= 2:
        logger.info("Running consistency checks (%d runs per case)...", consistency_runs)
        consistency_results = run_consistency_check(num_runs=consistency_runs, use_mocks=use_mocks)

    previous_rate = get_previous_pass_rate(reports_dir, total_cases=len(results))
    regression_delta = check_regression(pass_rate, previous_rate)
    if regression_delta is not None and regression_delta < 0:
        print(f"\n*** REGRESSION: Pass rate changed by {regression_delta:+.1f}% (from {previous_rate}% to {pass_rate}%). ***\n")

    out_path = write_eval_report(results, aggregate, regression_delta=regression_delta, consistency_results=consistency_results)
    print(f"\n{'='*60}")
    print(f"Eval Results: {passed}/{total} passed ({pass_rate}%)")
    print(f"Avg overall score: {aggregate['avg_overall_score']:.2f} (threshold={PASS_THRESHOLD})")
    print(f"Max latency: {MAX_LATENCY_SECONDS}s")
    print(f"Report: {out_path}")
    target_met = pass_rate >= TARGET_PASS_RATE_PCT
    print(f"Target met (≥{TARGET_PASS_RATE_PCT}%): {'yes' if target_met else 'no'}")
    if regression_delta is not None:
        print(f"Regression delta: {regression_delta:.1f}%")
    if consistency_results:
        c_passed = sum(1 for c in consistency_results if c.get("consistency_passed"))
        c_total = len(consistency_results)
        print(f"Consistency: {c_passed}/{c_total} passed ({consistency_runs} runs each)")
    print(f"{'='*60}")
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  [{status}] [{r.get('category')}] {r['input'][:55]}")
        if not r["passed"] and r.get("errors"):
            for err in r["errors"][:3]:
                print(f"        - {err}")

    version = os.environ.get("EVAL_VERSION", "1")
    experiment_url = run_langsmith_experiment(results, aggregate, version=version)
    if experiment_url:
        print(f"LangSmith experiment: {experiment_url}")

    return 0 if target_met and (regression_delta is None or regression_delta >= 0) else 1


if __name__ == "__main__":
    sys.exit(main())
