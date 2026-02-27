Ghostfolio Trading Intelligence Agent Project Plan: Where We Are, Where
We Are Going, How We Get There AgentForge Week 2 • Deadline: Sunday
10:59 PM CT

# 1. Vision: Where We Are Going

The Ghostfolio Trading Intelligence Agent transforms a passive portfolio
tracker into an active AI-powered decision-support system. Rather than
building from scratch, this is a brownfield integration --- extending an
existing open-source wealth management platform with conversational AI
capabilities.

## 1.1 The Problem

Long-term investors and active traders face the same fundamental
challenge: their tools are fragmented. Portfolio data lives in one
place, market data in another, risk rules in a spreadsheet, tax
implications in a separate calculator. Making a sound investment
decision requires manually pulling all of this together. Ghostfolio
solves the portfolio tracking problem well. It is a rearview mirror. The
agent turns it into a windshield.

## 1.2 Primary User: Long-Term Investor (Phase 1)

Phase 1 scope is deliberately focused on the long-term investor. Active
trader features (technical analysis, strategy scanning, regime
detection) are Phase 2 extensions.

The long-term investor asks conversational, portfolio-level questions:
Am I too concentrated anywhere? How have my investments performed this
year? Should I rebalance? What would my tax bill look like if I sold
everything? Does this trade violate wash sale rules? Should I buy more
AAPL given my current portfolio?

## 1.3 The Six Core Use Cases (Phase 1)

## 1.4 Phase 2: Active Retail Trader (Post-Sunday)

Once Phase 1 is stable, the agent extends to active trading use cases:
Technical analysis --- RSI, MACD, Bollinger Bands, momentum signals
Strategy scanning --- VCP, breakout, mean reversion setups Market regime
detection --- 5-dimension market classification Chart validation ---
support/resistance level analysis Intraday signals and real-time data
requirements

# 2. Current State: Where We Are

## 2.1 Architecture

The system consists of two services deployed on Railway, integrated with
the forked Ghostfolio repository:

## 2.2 The Agent Pipeline

Every natural language query flows through a 6-node LangGraph pipeline:

Key design decision: Claude is called exactly twice per request ---
intent classification and synthesis only. All tool selection, execution,
math, and verification is deterministic Python code.

## 2.3 Tool Registry --- 13 Tools Across 3 Levels

Tools are organized by the three levels of agent capability from the
PRD:

Level Legend: L1 = Deterministic (Ghostfolio API exists) L2 =
Aggregation (combines sources + rules) L3 = Net New (did not exist in
Ghostfolio)

## 2.4 Eval Performance History

The eval framework has been iterating rapidly. Each run produces a
structured JSON report with per-case scoring across 5 dimensions:

## 2.5 Brownfield Integration --- What We Extended

This is a brownfield project. The following changes were made to the
Ghostfolio fork:

# 3. PRD Requirements Status

Each PRD requirement mapped to current status. Green = complete. Orange
= in progress. Red = not started.

## 3.1 MVP Requirements (Hard Gate)

## 3.2 Core Agent Architecture

## 3.3 Required Tools --- Finance Track

## 3.4 Evaluation Framework

## 3.5 Observability

## 3.6 Verification Systems (Need 3+)

## 3.7 Performance Targets

Note: Latency is high due to mock eval overhead and LLM reasoning time.
Real production latency on single-tool queries is 3-5s. Multi-step
latency is a known gap --- flagged for post-submission optimization.

## 3.8 Remaining PRD Deliverables

# 4. Gameplan: How We Get There

Target: All deliverables complete and submitted by Saturday noon. Sunday
is pure buffer.

## 4.1 Thursday Night --- Stabilize

## 4.2 Friday --- Build Deliverables

## 4.3 Saturday --- Polish and Submit

## 4.4 Eval Suite Expansion Plan (50+ Cases)

All new cases scoped to Phase 1: Long-term investor use cases only. Scan
strategies, regime detection, chart validation, and signal archaeology
are Phase 2 --- excluded from this expansion.

# 5. Open Items and Known Gaps

## 5.1 Critical (Must Fix Before Submission)

## 5.2 Known Gaps (Documented, Not Blocking)

## 5.3 Phase 2 Backlog (Post-Sunday)

ReAct pattern refinement --- smarter tool selection within constrained
menu Structured outputs with Pydantic validation at every LLM boundary
Streaming responses --- show agent working in real time Active trader
use cases --- technical analysis, strategy scanning, regime-aware
responses Confidence-weighted synthesis language --- more assertive at
high confidence, more cautious at low Multi-turn context building a
trade thesis across turns Regime-aware responses --- filter every answer
through current market context

# 6. AI Cost Analysis (Template)

To be completed Saturday using actual LangSmith token data. Template
provided here.

## 6.1 Development Spend

## 6.2 Production Cost Projections

Assumptions: 5 queries/user/day, avg 2,000 input tokens + 800 output
tokens per query, 2 LLM calls per request.

Cost is extremely low due to the 2-LLM-call architecture. All tool
execution is deterministic Python --- no LLM costs for market data,
portfolio fetching, risk rules, or verification. Update with actual
token counts from LangSmith on Saturday.

# 7. Master Submission Checklist

Use this as your final review before submitting Saturday noon.

Ship and know. Not perfect and late. AgentForge Week 2 • Ghostfolio
Trading Intelligence Agent • February 2026
