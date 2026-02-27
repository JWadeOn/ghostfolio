"""Golden set runner — fast baseline correctness check (15 cases, binary pass/fail).

Usage:
    python3 tests/eval/run_golden.py
    python3 tests/eval/run_golden.py --report reports/golden-results.json

Exit code 0 = all golden cases pass; 1 = at least one failure.
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

from tests.eval.golden_cases import GOLDEN_CASES
from tests.eval.golden_checks import run_golden_checks
from tests.eval.run_evals import _apply_eval_mocks, run_single_eval

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_golden_suite() -> list[dict]:
    """Run all 15 golden cases with mocks and return per-case results."""
    from agent.graph import agent_graph

    patches = _apply_eval_mocks()
    try:
        results = []
        total = len(GOLDEN_CASES)
        for i, case in enumerate(GOLDEN_CASES):
            case_id = case.get("id", f"golden_{i + 1}")
            logger.info("Golden %d/%d: %s", i + 1, total, case["input"][:60] or "(empty)")

            eval_result = run_single_eval(case, agent_graph, case_id=i + 1, use_mocks=True)
            checks = run_golden_checks(case, eval_result)

            entry = {
                "id": case_id,
                "input": case["input"],
                "category": case.get("category", "general"),
                "passed": checks["passed"],
                "checks": checks,
                "tools_called": eval_result.get("tools_called", []),
                "latency_seconds": eval_result.get("latency_seconds"),
            }
            results.append(entry)

            status = "PASS" if checks["passed"] else "FAIL"
            logger.info("  %s  %s", status, case_id)
        return results
    finally:
        for p in patches:
            p.stop()


def print_summary(results: list[dict]) -> bool:
    """Print a concise summary table. Returns True if all passed."""
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    all_passed = passed == total

    print(f"\n{'=' * 70}")
    print(f"GOLDEN SET: {passed}/{total} passed {'(ALL PASS)' if all_passed else '*** FAILURES ***'}")
    print(f"{'=' * 70}")

    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        line = f"  [{status}] {r['id']}: {r['input'][:55]}"
        print(line)
        if not r["passed"]:
            checks = r["checks"]
            for dim in ("tool_selection", "source_citation", "content", "negative"):
                dim_result = checks[dim]
                if not dim_result["passed"]:
                    for err in dim_result["errors"]:
                        print(f"        {dim}: {err}")

    print(f"{'=' * 70}\n")
    return all_passed


def write_report(results: list[dict], path: Path) -> None:
    """Write a JSON report for CI artifacts."""
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    payload = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "total": total,
        "passed": passed,
        "all_passed": passed == total,
        "cases": results,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"Report written to {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run golden set baseline evals")
    parser.add_argument(
        "--report",
        type=str,
        default=None,
        help="Path to write JSON report (optional)",
    )
    args = parser.parse_args()

    start = time.perf_counter()
    results = run_golden_suite()
    elapsed = time.perf_counter() - start

    all_passed = print_summary(results)
    print(f"Total time: {elapsed:.1f}s")

    if args.report:
        write_report(results, Path(args.report))

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
