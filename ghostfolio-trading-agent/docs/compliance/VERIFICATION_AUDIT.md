# Verification Systems Audit

> Last updated: 2026-02-28

## Status: 5 of 6 types implemented (requirement: 3+)

---

## 1. Fact Checking

**Status:** Partial
**Files:** `agent/nodes/verification.py` (lines 97-178), `agent/authoritative_sources/`

### Numerical Fact Checking

- `_check_facts()` extracts numbers from synthesis using regex (dollars, percentages, indicators)
- Verifies each number exists in tool results with 0.5% tolerance
- Intent-based exemptions (skips for create_activity, portfolio_overview, etc.)
- Skips common numbers 0-200 to reduce false positives

### Authoritative Source Attribution

- `agent/authoritative_sources/sources.json` — 8 tax/compliance sources
- Covers: IRC §1091, §1222, §1(h); IRS Pub 550, 17, 544, 551
- `TOOL_TO_SOURCES` maps compliance_check → relevant source IDs
- `get_excerpts_for_tools()` injects source excerpts into system prompt

### Gaps

- Only numerical claims are fact-checked; non-numeric assertions are not validated
- Source attribution limited to tax/compliance domain
- No external source lookup (IRS website validation, etc.)

---

## 2. Hallucination Detection

**Status:** Partial
**Files:** `agent/nodes/verification.py`, `agent/nodes/synthesis.py`

### What's Implemented

- **Unsupported number flagging:** Any number in synthesis not found in tool results is flagged
- **Guarantee language detection:** Flags "guaranteed", "will definitely", "100% certain", "can't lose", "sure thing"
- **Source attribution prompt:** Synthesis system prompt requires "Every number you mention MUST come from the tool results"
- **Authoritative consistency:** `_check_authoritative_consistency()` validates wash sale 30-day window and long-term capital gains > 1 year claims

### Gaps

- No detection of unsupported non-numeric claims (regime classification, technical analysis claims)
- No LLM-based hallucination detection; only rule-based pattern matching
- Citations are "guessed" from keywords, not extracted from actual tool call context

---

## 3. Confidence Scoring

**Status:** Full
**File:** `agent/nodes/verification.py` (lines 229-276)

### Scoring Algorithm

```
Base score: 50

Boosters:
  +10 per tool result without error
  +0 to +10 from regime confidence
  +3 per strategy match (up to +10)
  +10 if guardrails_check passed
  -5 if guardrails failed
  +5 if compliance_check passed
  -5 if compliance violations

Final range: 0–100 (clamped)
```

### Output

- Included in `response.confidence` (integer 0-100)
- Low-confidence responses get verification warnings surfaced in `response.warnings`

### Gaps

- No threshold-based escalation (e.g., confidence < 40 triggers warning)
- No confidence calibration (comparing score vs actual correctness)

---

## 4. Domain Constraints

**Status:** Full
**File:** `agent/nodes/verification.py` (lines 181-441)

### Implemented Constraints

| Constraint             | Function                           | Rule                                                                          |
| ---------------------- | ---------------------------------- | ----------------------------------------------------------------------------- |
| Price freshness        | `_check_price_quote_freshness`     | Data must be from current trading day or within 3 calendar days               |
| Tax sanity             | `_check_tax_estimate_sanity`       | Liability >= 0, effective rate 0-100%                                         |
| Compliance consistency | `_check_compliance_consistency`    | Synthesis must not say "no violations" if compliance tool reported violations |
| Trade guardrails       | `_check_guardrails`                | Trade suggestions must include stop loss and target levels                    |
| Authoritative rules    | `_check_authoritative_consistency` | Wash sale = 30-day window; long-term = > 1 year holding                       |
| Input constraints      | `input_validation.py`              | Max 8000 chars, blocks injection phrases, requires non-empty                  |

---

## 5. Output Validation

**Status:** Partial
**File:** `agent/nodes/formatter.py` (lines 187-247)

### What's Implemented

- Response schema with mandatory fields: summary, confidence, intent, data, citations, warnings, tools_used, authoritative_sources, disclaimer, observability
- Intent-specific data extraction (`_build_intent_data`)
- JSON serialization of numpy/pandas types
- Citation extraction with source tool mapping

### Gaps

- No schema validation library (Pydantic or similar)
- No type checking on individual fields
- No completeness validation per intent (e.g., opportunity_scan must have opportunities list)

---

## 6. Human-in-the-Loop

**Status:** Not Implemented

### What Doesn't Exist

- No escalation triggers for high-risk decisions
- No approval workflow or confirmation step
- No "pending review" state or human review queue
- No threshold-based routing (e.g., low confidence → human)

### Related (but insufficient)

- User feedback endpoint (`POST /api/feedback`) — post-hoc, not real-time
- Verification retry on failure — re-synthesis, not human escalation

---

## Verification Node Flow

```
verify_node(state) called after synthesis
    ↓
_check_facts()                    # numerical claims vs tool results
_check_price_quote_freshness()    # domain constraint
_check_guardrails()               # trade guardrails + guarantee language
_check_tax_estimate_sanity()      # tax domain constraint
_check_compliance_consistency()   # compliance domain constraint
_check_authoritative_consistency()# authoritative rule validation
_compute_confidence()             # multi-factor confidence score
    ↓
If issues found and verification_attempts < max:
    → re-run synthesis with correction instructions
If still failing:
    → surface warnings in response
```
