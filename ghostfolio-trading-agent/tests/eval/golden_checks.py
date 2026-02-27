"""Deterministic, binary checks for the golden eval set.

Four check types — all pure functions over (case, result), no LLM calls:
  1. Tool selection   — required tools present; no extras when exact_tools is set.
  2. Source citation   — expected tools appear in response citations.
  3. Content validation — all required terms appear in response summary.
  4. Negative validation — no forbidden terms, no give-up phrases, non-empty summary.
"""

from __future__ import annotations

from tests.eval.run_evals import CONTENT_SYNONYMS


DEFAULT_GIVE_UP_PHRASES = [
    "i couldn't",
    "i was unable",
    "i don't have access",
    "unable to process",
    "unable to retrieve",
    "i cannot access",
]


def _term_found(term: str, text: str) -> bool:
    t = term.lower()
    if t in text:
        return True
    alt = CONTENT_SYNONYMS.get(t)
    return bool(alt and alt in text)


# ── 1. Tool selection ────────────────────────────────────────────────────

def check_tool_selection(case: dict, result: dict) -> tuple[bool, list[str]]:
    expected_tools = case.get("expected_tools", [])
    exact_tools = case.get("exact_tools", False)
    tools_called = result.get("tools_called", [])
    errors: list[str] = []

    missing = [t for t in expected_tools if t not in tools_called]
    if missing:
        errors.append(f"Missing tools: {missing}")

    if exact_tools:
        extra = [t for t in tools_called if t not in expected_tools]
        if extra:
            errors.append(f"Extra tools (exact_tools=True): {extra}")

    if not expected_tools and tools_called:
        errors.append(f"Expected no tools but agent called: {tools_called}")

    return (len(errors) == 0, errors)


# ── 2. Source citation ───────────────────────────────────────────────────

def check_source_citation(case: dict, result: dict) -> tuple[bool, list[str]]:
    expected_cited = case.get("expected_cited_tools")
    if not expected_cited:
        return (True, [])

    response = result.get("response") or {}
    citations = response.get("citations") or []
    cited_sources = {c.get("source") for c in citations if c.get("source")}

    errors: list[str] = []
    for tool in expected_cited:
        if tool not in cited_sources:
            errors.append(f"Expected citation from '{tool}' not found in sources: {sorted(cited_sources)}")

    return (len(errors) == 0, errors)


# ── 3. Content validation ───────────────────────────────────────────────

def check_content(case: dict, result: dict) -> tuple[bool, list[str]]:
    terms = list(case.get("expected_output_contains") or []) + list(case.get("should_contain") or [])
    if not terms:
        return (True, [])

    response = result.get("response") or {}
    summary_lower = (response.get("summary") or "").lower()

    errors: list[str] = []
    for term in terms:
        if not _term_found(term, summary_lower):
            errors.append(f"Missing required content: '{term}'")

    return (len(errors) == 0, errors)


# ── 4. Negative validation ──────────────────────────────────────────────

def check_negative(case: dict, result: dict) -> tuple[bool, list[str]]:
    response = result.get("response") or {}
    summary = response.get("summary") or ""
    summary_lower = summary.lower()

    errors: list[str] = []

    if not summary.strip():
        errors.append("Summary is empty")
        return (False, errors)

    forbidden = case.get("should_not_contain") or []
    for term in forbidden:
        if term.lower() in summary_lower:
            errors.append(f"Forbidden term found: '{term}'")

    give_up = case.get("give_up_phrases", DEFAULT_GIVE_UP_PHRASES)
    for phrase in give_up:
        if phrase.lower() in summary_lower:
            errors.append(f"Give-up phrase found: '{phrase}'")

    return (len(errors) == 0, errors)


# ── Aggregate ────────────────────────────────────────────────────────────

def run_golden_checks(case: dict, result: dict) -> dict:
    """Run all four golden checks and return structured result."""
    ts_pass, ts_err = check_tool_selection(case, result)
    sc_pass, sc_err = check_source_citation(case, result)
    ct_pass, ct_err = check_content(case, result)
    ng_pass, ng_err = check_negative(case, result)

    all_passed = ts_pass and sc_pass and ct_pass and ng_pass

    return {
        "passed": all_passed,
        "tool_selection": {"passed": ts_pass, "errors": ts_err},
        "source_citation": {"passed": sc_pass, "errors": sc_err},
        "content": {"passed": ct_pass, "errors": ct_err},
        "negative": {"passed": ng_pass, "errors": ng_err},
    }
