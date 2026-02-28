#!/usr/bin/env python3
"""Golden Set Evaluator for Portfolio Intelligence Agent.

Runs curated test cases and reports pass/fail results across seven dimensions:
  1. Tool selection   — did the agent call the right tools?
  2. Tool execution   — did every tool call succeed (no tool_errors)?
  3. Source citation   — did the response cite the right data source?
  4. Content           — does the response contain expected information?
  5. Negative          — no hallucination, no give-up phrases?
  6. Ground truth      — do known mock-data values appear in the response?
  7. Structural        — react_step count and latency within budget?

Usage:
    python3 tests/eval/run_golden.py
    python3 tests/eval/run_golden.py --verbose
    python3 tests/eval/run_golden.py --id gs-001
    python3 tests/eval/run_golden.py --report reports/golden-results.json
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

_SCRIPT_DIR = Path(__file__).resolve().parent
_AGENT_ROOT = _SCRIPT_DIR.parent.parent
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))

os.environ.setdefault("EVAL_MODE", "1")

from agent.config import get_settings as _get_settings

_s = _get_settings()
if _s.langchain_api_key and _s.langchain_tracing_v2:
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_API_KEY", _s.langchain_api_key)
    os.environ.setdefault("LANGCHAIN_PROJECT", _s.langchain_project)

from tests.eval.golden_cases import GOLDEN_CASES
from tests.eval.golden_checks import run_golden_checks
from tests.eval.run_evals import _apply_eval_mocks, run_single_eval

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_test_case(case: dict, agent_graph, case_idx: int) -> dict:
    """Run a single golden test case and return structured result."""
    case_id = case.get("id", f"gs-{case_idx:03d}")

    eval_result = run_single_eval(case, agent_graph, case_id=case_idx, use_mocks=True)

    # Extract react_step from the eval result (number of ReAct loop iterations)
    response = eval_result.get("response") or {}
    observability = response.get("observability") or {}
    node_latencies = eval_result.get("node_latencies") or observability.get("node_latencies") or {}
    # Count react_agent_N keys to determine step count
    react_steps = sum(1 for k in node_latencies if k.startswith("react_agent_"))
    eval_result["react_step"] = react_steps

    checks = run_golden_checks(case, eval_result)

    return {
        "id": case_id,
        "input": case["input"],
        "category": case.get("category", "general"),
        "passed": checks["passed"],
        "checks": checks,
        "tools_called": eval_result.get("tools_called", []),
        "tool_errors": eval_result.get("tool_errors", []),
        "react_steps": react_steps,
        "latency_seconds": eval_result.get("latency_seconds"),
    }


def run_golden_set(
    test_cases: list[dict],
    verbose: bool = False,
    test_id: str | None = None,
) -> list[dict]:
    """Run all golden cases with mocks and return per-case results."""
    from agent.graph import agent_graph

    if test_id:
        test_cases = [tc for tc in test_cases if tc.get("id") == test_id]
        if not test_cases:
            print(f"No test case found with id: {test_id}")
            return []

    patches = _apply_eval_mocks()
    try:
        results = []
        total = len(test_cases)

        for i, case in enumerate(test_cases):
            case_id = case.get("id", f"gs-{i + 1:03d}")
            query = case["input"][:50] or "(empty)"
            print(f"[{i + 1}/{total}] Running {case_id}: {query}...")

            result = run_test_case(case, agent_graph, case_idx=i + 1)
            results.append(result)

            status = "✓" if result["passed"] else "✗"
            print(f"       {status} {'PASS' if result['passed'] else 'FAIL'}")

            if verbose and not result["passed"]:
                for dim in ("tool_selection", "tool_execution", "source_citation", "content", "negative", "ground_truth", "structural"):
                    dim_data = result["checks"].get(dim, {})
                    err = dim_data.get("error", "")
                    if err:
                        print(f"         - {dim}: {err}")

        return results
    finally:
        for p in patches:
            p.stop()


def print_summary(results: list[dict]) -> bool:
    """Print summary with per-dimension status for each case."""
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    pct = (passed / total * 100) if total > 0 else 0
    all_passed = passed == total

    print(f"\n{'=' * 60}")
    print("GOLDEN SET RESULTS")
    print(f"{'=' * 60}\n")

    dim_labels = {
        "tool_selection": "Tools",
        "tool_execution": "ToolExec",
        "source_citation": "Sources",
        "content": "Content",
        "negative": "Negative",
        "ground_truth": "GroundTruth",
        "structural": "Structural",
    }

    for r in results:
        status = "✓" if r["passed"] else "✗"
        steps_str = f" [{r.get('react_steps', '?')} steps]" if r.get("react_steps") is not None else ""
        print(f"{status} {r['id']}: {r['input'][:50]}...{steps_str}")

        checks = r["checks"]
        dims = []
        for dim, label in dim_labels.items():
            dim_result = checks.get(dim, {})
            mark = "✓" if dim_result.get("passed", True) else "✗"
            dims.append(f"{label}: {mark}")
        print(f"    {' | '.join(dims)}")

        if not r["passed"]:
            for dim in dim_labels:
                err = checks.get(dim, {}).get("error", "")
                if err:
                    print(f"    ERROR: {err}")

        print()

    print("-" * 60)
    print(f"Total: {passed}/{total} passed ({pct:.1f}%)")

    if all_passed:
        print("\n✓ All golden set tests passed!")
    else:
        print(f"\n✗ {total - passed} test(s) failed")

    return all_passed


def write_report(results: list[dict], reports_dir: Path) -> Path:
    """Write a timestamped JSON report. Each run creates a new file."""
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    latencies = [r["latency_seconds"] for r in results if r.get("latency_seconds") is not None]
    # Tool success: among cases that called tools, fraction with no tool_errors (PRD target >95%)
    cases_with_tools = [r for r in results if r.get("tools_called")]
    tool_success_count = sum(
        1 for r in cases_with_tools
        if r.get("checks", {}).get("tool_execution", {}).get("passed", True)
    )
    tool_success_rate_pct = (
        round(100 * tool_success_count / len(cases_with_tools), 1) if cases_with_tools else 100.0
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "timestamp": timestamp,
        "total": total,
        "passed": passed,
        "pass_rate_pct": round(100 * passed / total, 1) if total else 0,
        "all_passed": passed == total,
        "tool_success_rate_pct": tool_success_rate_pct,
        "cases_with_tools": len(cases_with_tools),
        "avg_latency_seconds": round(sum(latencies) / len(latencies), 2) if latencies else None,
        "cases": results,
    }
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"golden-results-{timestamp}.json"
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\nReport written to {path}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run portfolio intelligence golden set evaluation")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show error details for failing cases")
    parser.add_argument("--id", type=str, help="Run only a specific test case by ID (e.g. gs-001)")
    parser.add_argument("--report", action="store_true", help="Write timestamped JSON report to reports/")
    args = parser.parse_args()

    print("Portfolio Intelligence Agent - Golden Set Evaluation")
    print("=" * 60)
    print()

    print(f"Loaded {len(GOLDEN_CASES)} test cases\n")

    start = time.perf_counter()
    results = run_golden_set(GOLDEN_CASES, verbose=args.verbose, test_id=args.id)
    elapsed = time.perf_counter() - start

    all_passed = print_summary(results)
    print(f"\nTotal time: {elapsed:.1f}s")

    if args.report:
        reports_dir = Path(__file__).resolve().parent.parent.parent / "reports"
        write_report(results, reports_dir)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
