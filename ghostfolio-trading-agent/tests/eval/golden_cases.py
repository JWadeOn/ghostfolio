"""Golden set: 15 baseline correctness cases for fast post-commit validation.

These are deterministic, binary checks (no LLM needed) covering four dimensions:
  1. Tool selection   — did the agent call the right tools?
  2. Source citation   — did the agent cite the right data source?
  3. Content validation — does the response contain key facts?
  4. Negative validation — did the agent hallucinate or give up?

All cases are Phase 1, mock-safe, and mirror proven cases from dataset.py.
Run via: python3 tests/eval/run_golden.py
"""

GOLDEN_CASES = [
    # ── Tool selection + Content + Citation ──────────────────────────────
    {
        "id": "golden_portfolio_overview",
        "input": "Show me my portfolio",
        "expected_intent": "portfolio_overview",
        "expected_tools": ["get_portfolio_snapshot"],
        "expected_output_contains": ["portfolio", "position", "value"],
        "expected_cited_tools": ["get_portfolio_snapshot"],
        "category": "portfolio_overview",
        "phase": 1,
        "case_type": "happy_path",
    },
    {
        "id": "golden_risk_check_buy",
        "input": "Can I buy $10,000 of TSLA?",
        "expected_intent": "risk_check",
        "expected_tools": ["get_portfolio_snapshot", "get_market_data", "trade_guardrails_check"],
        "expected_output_contains": ["position"],
        "category": "risk_check",
        "phase": 1,
        "case_type": "happy_path",
    },
    {
        "id": "golden_risk_check_sell",
        "input": "Should I sell AAPL?",
        "expected_intent": "risk_check",
        "expected_tools": ["get_portfolio_snapshot", "get_market_data", "trade_guardrails_check"],
        "expected_output_contains": ["position", "portfolio"],
        "category": "risk_check",
        "phase": 1,
        "case_type": "happy_path",
    },
    {
        "id": "golden_journal_analysis",
        "input": "How have my trades performed in the last 90 days?",
        "expected_intent": "journal_analysis",
        "expected_tools": ["get_trade_history"],
        "expected_output_contains": ["win_rate"],
        "expected_cited_tools": ["get_trade_history"],
        "category": "journal_analysis",
        "phase": 1,
        "case_type": "happy_path",
    },
    {
        "id": "golden_price_quote",
        "input": "What's AAPL trading at?",
        "expected_intent": "price_quote",
        "expected_tools": ["get_market_data"],
        "exact_tools": True,
        "expected_output_contains": ["AAPL"],
        "ground_truth_contains": ["187"],
        "category": "price_quote",
        "phase": 1,
        "live_safe": False,
        "case_type": "happy_path",
    },
    # ── Tool selection + Content (exact tool match) ──────────────────────
    {
        "id": "golden_lookup_apple",
        "input": "What's the ticker symbol for Apple?",
        "expected_intent": "lookup_symbol",
        "expected_tools": ["lookup_symbol"],
        "exact_tools": True,
        "expected_output_contains": ["AAPL"],
        "category": "lookup_symbol",
        "phase": 1,
        "case_type": "happy_path",
    },
    {
        "id": "golden_lookup_tesla",
        "input": "Look up the symbol for Tesla",
        "expected_intent": "lookup_symbol",
        "expected_tools": ["lookup_symbol"],
        "exact_tools": True,
        "expected_output_contains": ["TSLA"],
        "category": "lookup_symbol",
        "phase": 1,
        "case_type": "happy_path",
    },
    # ── Tool selection + Content (create / watchlist) ────────────────────
    {
        "id": "golden_create_activity",
        "input": "Record a buy of 10 shares of AAPL at $150 per share on 2025-02-26 in USD",
        "expected_intent": "general",
        "expected_tools": ["create_activity"],
        "expected_output_contains": ["recorded", "AAPL"],
        "should_contain": ["recorded", "activity"],
        "category": "create_activity",
        "phase": 1,
        "case_type": "happy_path",
    },
    {
        "id": "golden_add_watchlist",
        "input": "Add AAPL to my watchlist",
        "expected_intent": "general",
        "expected_tools": ["add_to_watchlist"],
        "expected_output_contains": ["watchlist", "AAPL"],
        "should_contain": ["watchlist"],
        "category": "add_to_watchlist",
        "phase": 1,
        "case_type": "happy_path",
    },
    {
        "id": "golden_add_watchlist_msft",
        "input": "Put MSFT on my watchlist",
        "expected_intent": "general",
        "expected_tools": ["add_to_watchlist"],
        "expected_output_contains": ["watchlist", "MSFT"],
        "should_contain": ["watchlist"],
        "category": "add_to_watchlist",
        "phase": 1,
        "case_type": "happy_path",
    },
    # ── Tool selection (chart validation) ────────────────────────────────
    {
        "id": "golden_chart_validation",
        "input": "Is my support at $320 on TSLA valid?",
        "expected_intent": "chart_validation",
        "expected_tools": ["get_market_data"],
        "category": "chart_validation",
        "phase": 1,
        "case_type": "happy_path",
    },
    # ── Negative validation (no tools, no hallucination) ─────────────────
    {
        "id": "golden_greeting",
        "input": "Hello, who are you?",
        "expected_intent": "general",
        "expected_tools": [],
        "should_not_contain": ["buy", "sell", "entry", "stop loss"],
        "category": "general",
        "phase": 1,
        "case_type": "adversarial",
    },
    {
        "id": "golden_adversarial_guarantee",
        "input": "Guarantee me 50% returns this month",
        "expected_intent": "general",
        "should_not_contain": ["guaranteed", "will return", "promise", "promised"],
        "should_contain": ["cannot", "not financial advice"],
        "category": "general",
        "phase": 1,
        "case_type": "adversarial",
    },
    {
        "id": "golden_edge_gibberish",
        "input": "asdkjfh 2838 !@#$%",
        "expected_intent": "general",
        "expected_tools": [],
        "should_not_contain": ["buy", "sell", "entry", "stop loss", "guarantee"],
        "category": "edge_invalid",
        "phase": 1,
        "case_type": "edge_case",
    },
    {
        "id": "golden_edge_ambiguous",
        "input": "Should I?",
        "expected_intent": "general",
        "expected_tools": [],
        "should_not_contain": ["sold", "order executed", "order placed", "bought"],
        "category": "edge_ambiguous",
        "phase": 1,
        "case_type": "edge_case",
    },
]

assert len(GOLDEN_CASES) == 15, f"Golden set must have exactly 15 cases, got {len(GOLDEN_CASES)}"
