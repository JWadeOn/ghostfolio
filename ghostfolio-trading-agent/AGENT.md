# Ghostfolio Trading Intelligence Agent — Project Context

## Current Status

- Phase 1 (Long-term investor) only. Phase 2 (active trader) is post-Sunday.
- 13 tools implemented and tested
- Mock evals target 80%+
- Deadline: Saturday noon (Sunday is buffer)

## DO NOT TOUCH (Phase 2)

- scan_strategies
- detect_regime
- chart_validation eval cases
- signal_archaeology eval cases
- regime_check eval cases
- opportunity_scan eval cases

## Active Priorities (in order)

1. Mock evals stable at 80%+ (3 consecutive runs)
2. LangSmith Datasets + Experiments wired
3. Redis + Postgres session management
4. Expand eval suite to 50+ cases (Phase 1 scope only)
5. User feedback endpoint POST /api/feedback

## Architecture Rules

- Phase 1 user: long-term investor (conversational, portfolio-level queries)
- Phase 2 user: active trader (technical analysis, signals, regime-aware)
