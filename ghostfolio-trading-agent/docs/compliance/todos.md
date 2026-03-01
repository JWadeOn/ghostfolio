Here's a practical checklist in order of priority:

1. Local dev smoke test

cd ghostfolio-trading-agent

# Start the agent (assumes Ghostfolio/Postgres/Redis already running or use docker compose)

uvicorn agent.app:app --host 0.0.0.0 --port 8000

Then hit it with a few representative queries:

# Simple (1 tool)

curl -s -X POST http://localhost:8000/api/chat \
 -H "Content-Type: application/json" \
 -d '{"message": "Show me my portfolio"}' | python3 -m json.tool | head -20

# Multi-tool

curl -s -X POST http://localhost:8000/api/chat \
 -H "Content-Type: application/json" \
 -d '{"message": "Should I sell GOOG?"}' | python3 -m json.tool | head -20

# Health check

curl -s http://localhost:8000/api/health | python3 -m json.tool

What you're looking for: HTTP 200, non-empty summary, tools_used populated, and latency feels snappy
(check observability.node_latencies.total_latency_seconds in the response).

2. Run the eval layers (mocked, no live services needed)

# Golden set first — this is your "did I break anything?" gate

python3 tests/eval/run_golden.py

# Then scenarios for coverage

python3 tests/eval/run_scenarios.py --report

# Then dataset for weighted scoring + regression baseline

python3 tests/eval/run_evals.py

The golden set is the one that matters most. If it passes, your architecture changes didn't break core
behavior. The dataset run will establish a new baseline report in reports/ since the case count changed
from 60 to 30.

3. Check latency improvement specifically

Since you made architecture changes for latency, compare before/after:

# Golden set has per-case latency in its report

python3 tests/eval/run_golden.py --report

# Check the report

python3 -c "
import json, glob
f = sorted(glob.glob('reports/golden-results-\*.json'))[-1]
data = json.load(open(f))
for c in data['per_case']:
print(f\"{c['id']:10s} {c['latency_seconds']:5.1f}s {'PASS' if c['passed'] else 'FAIL'}\")
"

4. Deploy and test the live instance

Once local checks look good:

# Push your branch (assuming Railway auto-deploys from branch, or merge to main)

git push origin trading-agent

After deployment completes:

# Health check

curl -s https://your-ghostfolio.up.railway.app/api/health | python3 -m json.tool

# Smoke test (same queries as local)

curl -s -X POST https://your-ghostfolio.up.railway.app/api/chat \
 -H "Content-Type: application/json" \
 -d '{"message": "Show me my portfolio"}' | python3 -m json.tool | head -20

5. (Optional) Live evals against deployed instance

If you want to validate evals against the real deployment:

# Seed first if portfolio data isn't already there

GHOSTFOLIO_API_URL=https://your-ghostfolio.up.railway.app \
 GHOSTFOLIO_ACCESS_TOKEN=your-token \
 python3 scripts/seed_ghostfolio_for_evals.py

# Run live evals

EVAL_USE_MOCKS=0 python3 tests/eval/run_evals.py

Order of operations

Do steps 1-3 before pushing anything. Step 2 (golden set) is the most important — if that passes, you're
safe to deploy. Step 4 is deploy + sanity check. Step 5 is optional polish.

The gs-019 latency flake (3.1s vs 3s limit) you saw earlier is worth keeping an eye on — if your latency
improvements landed, it might resolve itself. If it's still flaky, consider bumping that case's
max_latency_seconds by 1s.
