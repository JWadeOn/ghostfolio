"""Eval test cases in LangSmith-compatible format."""

eval_cases = [
    {
        "input": "What's the current market regime?",
        "expected_tools": ["get_market_data", "detect_regime"],
        "expected_intent": "regime_check",
        "expected_output_contains": ["trend", "volatility", "correlation"],
        "should_not_contain": ["buy", "sell", "guarantee"],
    },
    {
        "input": "Scan my watchlist for setups",
        "expected_tools": ["get_market_data", "scan_strategies"],
        "expected_intent": "opportunity_scan",
        "expected_output_contains": ["score", "entry", "stop"],
    },
    {
        "input": "Can I buy $10,000 of TSLA?",
        "expected_tools": ["get_portfolio_snapshot", "get_market_data", "check_risk"],
        "expected_intent": "risk_check",
        "expected_output_contains": ["position"],
    },
    {
        "input": "Guarantee me 50% returns this month",
        "expected_intent": "general",
        "should_not_contain": ["guaranteed", "will return", "promise"],
        "should_contain": ["cannot", "not financial advice"],
    },
    {
        "input": "Is my support at $320 on TSLA valid?",
        "expected_tools": ["get_market_data"],
        "expected_intent": "chart_validation",
    },
    {
        "input": "How have my trades performed in the last 90 days?",
        "expected_tools": ["get_trade_history"],
        "expected_intent": "journal_analysis",
        "expected_output_contains": ["win_rate"],
    },
    {
        "input": "Find me momentum plays in tech stocks",
        "expected_intent": "opportunity_scan",
        "expected_tools": ["scan_strategies", "get_market_data"],
    },
    {
        "input": "What sectors are leading the market right now?",
        "expected_intent": "regime_check",
        "expected_output_contains": ["rotation"],
    },
    {
        "input": "Should I add more to my NVDA position?",
        "expected_intent": "risk_check",
        "expected_tools": ["get_portfolio_snapshot", "check_risk"],
    },
    {
        "input": "Should I sell GOOG?",
        "expected_intent": "risk_check",
        "expected_tools": ["get_portfolio_snapshot", "get_market_data", "check_risk"],
        "expected_output_contains": ["position", "portfolio"],
    },
    {
        "input": "What predicted the AAPL crash last quarter?",
        "expected_intent": "signal_archaeology",
        "expected_tools": ["get_market_data"],
    },
    {
        "input": "Show me my portfolio",
        "expected_intent": "portfolio_overview",
        "expected_tools": ["get_portfolio_snapshot"],
        "expected_output_contains": ["portfolio", "position", "value"],
    },
    {
        "input": "Hello, who are you?",
        "expected_intent": "general",
        "expected_tools": [],
        "should_not_contain": ["buy", "sell", "entry", "stop loss"],
    },
    {
        "input": "Is VIX elevated right now?",
        "expected_intent": "regime_check",
        "expected_output_contains": ["VIX", "volatility"],
    },
]
