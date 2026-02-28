"""Pytest wrapper for the golden set — run via:

    pytest tests/eval/test_golden.py -q

Each golden case is parametrized as its own test so failures are easy to locate.
"""

from __future__ import annotations

import os
import pytest

os.environ.setdefault("EVAL_MODE", "1")

from tests.eval.golden_cases import GOLDEN_CASES
from tests.eval.golden_checks import run_golden_checks
from tests.eval.run_evals import _apply_eval_mocks, run_single_eval


@pytest.fixture(scope="module")
def agent_graph():
    from agent.graph import agent_graph as graph
    return graph


@pytest.fixture(scope="module", autouse=True)
def mock_env():
    patches = _apply_eval_mocks()
    yield
    for p in patches:
        p.stop()


@pytest.mark.parametrize(
    "case",
    GOLDEN_CASES,
    ids=[c.get("id", f"golden_{i}") for i, c in enumerate(GOLDEN_CASES)],
)
def test_golden_case(case, agent_graph):
    eval_result = run_single_eval(case, agent_graph, case_id=0, use_mocks=True)
    checks = run_golden_checks(case, eval_result)

    if not checks["passed"]:
        failures = []
        for dim in ("tool_selection", "source_citation", "content", "negative"):
            dim_result = checks[dim]
            if not dim_result["passed"]:
                err = dim_result.get("error", "")
                if err:
                    failures.append(f"[{dim}] {err}")
        pytest.fail(
            f"Golden case '{case.get('id')}' failed:\n" + "\n".join(failures)
        )
