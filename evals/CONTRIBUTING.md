# Contributing New Eval Cases

This guide explains how to add and validate new cases for the LangGraph financial agent eval dataset.

---

## Case structure template

Each case in `dataset.json` must be a single object. Use this template and fill only the fields that apply:

```json
{
  "id": "case_XXX",
  "category": "category_name",
  "difficulty": "easy | medium | hard",
  "phase": 1,
  "input": "User message to send to the agent",
  "expected_intent": "intent_label_or_null",
  "expected_tools": ["tool_a", "tool_b"],
  "expected_output_contains": ["phrase1", "phrase2"],
  "should_not_contain": ["forbidden_phrase"],
  "should_contain": ["required_phrase"],
  "confidence_min": 0,
  "golden": true,
  "live_safe": true,
  "exact_tools": false,
  "ground_truth_contains": []
}
```

- **id**: Unique string (e.g. `case_025`, `case_026`). Use the next sequential id.
- **category**: One of the existing categories (see Category guidelines below).
- **difficulty**: `easy`, `medium`, or `hard` (see Difficulty guidelines).
- **phase**: `1` (long-term investor flows) or `2` (regime/scan flows).
- **input**: The exact user message. Required.
- **expected_intent**: Intent label your agent should predict, or omit for “no check”.
- **expected_tools**: List of tool names that must be called. Use `[]` if no tools required.
- **expected_output_contains**: Phrases that should appear in the final answer (partial credit).
- **should_not_contain**: Phrases that must not appear (safety).
- **should_contain**: Additional required phrases (e.g. disclaimers).
- **confidence_min**: Minimum agent confidence (0–100) to pass the confidence dimension; use `0` to skip.
- **golden**: `true` to include in fast mode (high-signal subset); `false` for full/live only.
- **live_safe**: `true` if content/safety checks apply when running live (no mocks); `false` to skip content checks in live mode (only tools checked).
- **exact_tools**: `true` if the agent must call exactly `expected_tools` (no extras); default `false` (subset).
- **ground_truth_contains**: Optional list of strings that must appear when using mocks (e.g. mock price).

---

## Difficulty guidelines

- **Easy**
  - Single, clear intent; one or two tools; simple pass/fail content (e.g. symbol lookup, portfolio overview, greeting).
  - Good for: `lookup_symbol`, `portfolio_overview`, `price_quote`, simple `general`.
- **Medium**
  - Multiple tools or multi-step reasoning; several content phrases; risk/guardrail checks.
  - Good for: `risk_check`, `chart_validation`, `journal_analysis`, `create_activity`, `regime_check`.
- **Hard**
  - Ambiguous or adversarial input; safety-critical (e.g. refusing guarantees); edge cases (empty/gibberish/vague).
  - Good for: `opportunity_scan`, `signal_archaeology`, `edge_invalid`, `edge_ambiguous`, guarantee-refusal `general`.

---

## Category guidelines

- **portfolio_overview**: User asks to see portfolio/holdings. Expect `get_portfolio_snapshot` and output containing position/value language.
- **risk_check**: User asks about adding/selling or position sizing. Expect portfolio + market + guardrail tools; no execution.
- **regime_check**: User asks about market regime, volatility, or sector rotation. Expect regime/market tools; no trade recommendations.
- **opportunity_scan**: User asks for setups, ideas, or scans. Expect scan + market tools; output should be informational, not execution.
- **price_quote**: User asks for current price. Expect market data tool; optional `ground_truth_contains` for mock price.
- **lookup_symbol**: User asks for ticker by name. Expect `lookup_symbol`; `exact_tools: true` often appropriate.
- **create_activity**: User asks to log a buy/sell. Expect `create_activity`; output should confirm “recorded”/“activity”.
- **chart_validation**: User asks whether a level (support/resistance) is valid. Expect market data; answer should be data-based.
- **journal_analysis**: User asks about trade history or performance. Expect `get_trade_history`; include metrics like win rate where relevant.
- **signal_archaeology**: User asks what “predicted” a past move. Expect market/data tools; answer retrospective, no guarantees.
- **general**: Greetings, identity, or non-action. Use `should_not_contain` to avoid spurious trade language; use `should_contain` for disclaimers when refusing guarantees.
- **edge_invalid**: Empty or gibberish input. Expect no tools, no guarantees or trade language.
- **edge_ambiguous**: Vague input (e.g. “Sell”, “Should I?”). Expect no execution or specific order placement; `should_not_contain` for “sold”, “order executed”, etc.

---

## How to validate a new case before submitting

1. **IDs**: Ensure `id` is unique and sequential (e.g. next after the last in `dataset.json`).
2. **JSON**: Validate that the new case is valid JSON and that the full `dataset.json` still loads (e.g. `python3 -c "import json; json.load(open('evals/dataset.json'))"`).
3. **Scoring**: Run the standalone scorer on a sample result to ensure the case is scoreable:
   ```bash
   python3 -c "
   import json
   from evals.scoring import score_case
   with open('evals/dataset.json') as f:
       data = json.load(f)
   case = data['cases'][-1]  # your new case
   result = {'intent': case.get('expected_intent'), 'tools_called': case.get('expected_tools', []), 'response': {'summary': '...', 'confidence': 80}, 'tool_results': {}}
   scores, overall, passed = score_case(case, result)
   print('overall', overall, 'passed', passed)
   "
   ```
4. **Golden**: Only set `golden: true` for cases that are stable and high-signal (no flaky or live-only content).
5. **live_safe**: Set `live_safe: false` only when the case relies on mock-specific content (e.g. exact mock price); then in live mode only tool usage will be checked.

After validation, add the case to the `cases` array in `evals/dataset.json` and open a PR or submit the patch.
