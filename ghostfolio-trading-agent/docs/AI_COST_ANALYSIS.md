# AI Cost Analysis — Ghostfolio Trading Agent

---

## 1. Development Costs To Date

### LLM usage during development

The eval suite was the primary consumer of LLM tokens during development. Each eval run sends queries through the full agent graph (LLM + tools + verification).

| Eval layer | Cases per run | Runs | Total cases executed |
|------------|---------------|------|----------------------|
| Dataset (30 cases) | 30 | 33 | ~990 |
| Golden set (34 cases) | 34 | 11 | ~374 |
| Scenarios (47 cases) | 47 | 6 | ~282 |
| Performance targets | varies | 5 | ~50 |
| **Total** | | **55 runs** | **~1,700 cases** |

**Estimated development token usage:**

Each eval case averages ~4,500 input tokens and ~500 output tokens (system prompt + tool results + synthesis). Using the Haiku pricing:

| Metric | Value |
|--------|-------|
| Avg input tokens per case | ~4,500 |
| Avg output tokens per case | ~500 |
| Cost per case (Haiku) | ~$0.007 |
| Total eval cases | ~1,700 |
| **Estimated eval cost** | **~$12** |

Manual testing, prompt iteration, and ad-hoc queries add roughly 2x the eval volume:

| Activity | Estimated cost |
|----------|---------------|
| Eval suite runs | ~$12 |
| Manual testing / prompt iteration | ~$25 |
| **Total development LLM cost** | **~$37** |

### Infrastructure during development

| Service | Cost |
|---------|------|
| PostgreSQL | Free (local Docker) |
| Redis | Free (local Docker) |
| Ghostfolio | Free (open source, local) |
| Railway (deployment testing) | Free tier |
| yfinance | Free |
| LangSmith | Free tier (5,000 traces/month) |
| **Total infrastructure** | **$0** |

### Development cost summary

| Category | Cost |
|----------|------|
| LLM (Anthropic API) | ~$37 |
| Infrastructure | $0 |
| External APIs | $0 |
| **Total development cost** | **~$37** |

---

## 2. Production Cost Model

### Per-request cost breakdown

The agent makes 1-2 LLM calls per request (see Architecture Document). The default model is Claude Haiku 4.5.

**Anthropic pricing (per 1M tokens):**

| Model | Input | Output |
|-------|-------|--------|
| Claude Haiku 4.5 | $1.00 | $5.00 |
| Claude Sonnet 4 | $3.00 | $15.00 |

**System prompt overhead:** The ReAct system prompt is ~2,100 tokens, sent on every LLM call. This is the fixed cost floor per request.

**Typical request profiles (Haiku):**

| Query type | LLM calls | Input tokens | Output tokens | Cost |
|------------|-----------|-------------|---------------|------|
| Greeting / out-of-scope | 1 | 2,500 | 200 | $0.0035 |
| Price quote (1 tool) | 2 | 5,500 | 400 | $0.0075 |
| Portfolio overview (1-2 tools) | 2 | 6,000 | 500 | $0.0085 |
| Trade evaluation (3 tools) | 2 | 7,500 | 600 | $0.0105 |
| Tax / compliance (2-3 tools) | 2 | 7,000 | 500 | $0.0095 |
| Multi-step analysis (4-6 tools) | 2 | 9,000 | 800 | $0.0130 |

Input tokens scale with the number of tools because each tool result (truncated to 8,000 chars) is appended to the conversation before the second LLM call.

### Monthly projections

**Assumptions:** Mixed query distribution, Haiku model, no Sonnet override.

| Monthly requests | Avg cost/request | Monthly LLM cost |
|-----------------|------------------|-------------------|
| 100 | $0.009 | **$0.90** |
| 500 | $0.009 | **$4.50** |
| 1,000 | $0.009 | **$9.00** |
| 5,000 | $0.009 | **$45.00** |
| 10,000 | $0.009 | **$90.00** |

### Caching impact

In-graph caching reduces both LLM and external API costs by avoiding redundant tool calls:

| Cache | TTL | Effect |
|-------|-----|--------|
| Portfolio snapshot | 5 min | Skips `get_portfolio_snapshot` tool call; reduces input tokens by ~1,500 |
| Market regime | 30 min | Skips `detect_regime` tool call; reduces input tokens by ~1,000 |
| Market data (in-memory) | 5 min | Skips yfinance fetch; no token impact but reduces latency |

For a user making several queries in a session, caching reduces the average cost per request by roughly 20-30%. The table above uses uncached (worst-case) estimates.

### Infrastructure costs (production)

| Service | Self-hosted | Cloud-managed |
|---------|-------------|---------------|
| PostgreSQL | Free (Docker) | $7-15/month (Railway, Render) |
| Redis | Free (Docker) | $5-10/month (Railway, Upstash) |
| Ghostfolio app | Free (Docker) | Included in compute |
| Compute (agent + Ghostfolio) | Free (own server) | $5-20/month (Railway hobby) |
| **Total** | **$0** | **$15-45/month** |

### External API costs

| API | Pricing | Usage pattern | Monthly cost |
|-----|---------|---------------|-------------|
| Anthropic (Claude) | Per-token (see above) | Every request | $1-90 (scales with volume) |
| yfinance | Free | Market data tool calls | $0 |
| Financial Modeling Prep | Free tier: 250 req/day | Optional (cloud deployments) | $0 (free tier) |
| LangSmith | Free: 5K traces/month | Optional observability | $0 (free tier) or $39/month (Plus) |

---

## 3. Cost Comparison: Model Selection

The agent model is configurable via the `AGENT_MODEL` environment variable. Switching models changes the cost/quality tradeoff:

| Model | Cost per request (avg) | Monthly @ 1K req | Latency (avg) | Quality |
|-------|----------------------|-------------------|---------------|---------|
| **Haiku 4.5 (default)** | $0.009 | $9 | 2.8s | Good for structured tool-based queries |
| Sonnet 4 | $0.036 | $36 | 4-6s | Better reasoning on complex multi-step |

Haiku is the default because the agent's architecture offloads reasoning to deterministic code (verification, guardrails, compliance rules). The LLM's primary job is tool selection and natural language synthesis — tasks where Haiku performs well.

---

## 4. Cost per Eval Run

Running the eval suite has a measurable cost. Budget for this when iterating on prompts or tools.

| Eval layer | Cases | Est. cost per run (Haiku) |
|------------|-------|--------------------------|
| Golden set | 34 | ~$0.24 |
| Scenarios | 47 | ~$0.33 |
| Dataset | 30 | ~$0.27 |
| **Full suite** | **111** | **~$0.84** |

At ~$0.84 per full suite run, you can run the complete eval suite ~1,200 times for $1,000.

---

## 5. Production Cost Summary

**Single-user self-hosted deployment (typical):**

| Component | Monthly cost |
|-----------|-------------|
| Anthropic API (~200 queries) | ~$1.80 |
| Infrastructure (Docker on own machine) | $0 |
| External APIs | $0 |
| **Total** | **~$2/month** |

**Team deployment on cloud (500 req/month):**

| Component | Monthly cost |
|-----------|-------------|
| Anthropic API | ~$4.50 |
| Railway / Render compute | ~$15-20 |
| Managed Postgres + Redis | ~$10-15 |
| LangSmith (optional) | $0-39 |
| **Total** | **~$30-75/month** |

**Scaling reference (10K req/month):**

| Component | Monthly cost |
|-----------|-------------|
| Anthropic API | ~$90 |
| Compute (needs more resources) | ~$30-50 |
| Managed Postgres + Redis | ~$15-30 |
| LangSmith Plus | $39 |
| **Total** | **~$175-210/month** |
