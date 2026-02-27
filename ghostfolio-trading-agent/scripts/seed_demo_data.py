#!/usr/bin/env python3
"""Seed the Railway Ghostfolio instance with the demo portfolio (AAPL, TSLA, GOOG, NVDA, MSFT).

Uses GHOSTFOLIO_ACCESS_TOKEN and GHOSTFOLIO_API_URL from the environment — the same
token should be used for seeding and for evals (EVAL_USE_MOCKS=0).

This script reuses the logic and dataset from seed_ghostfolio_for_evals.py, which
seeds from tests/eval/mock_dataset.json (positions in AAPL, TSLA, GOOG, NVDA, MSFT).

Usage:
  From ghostfolio-trading-agent directory:
    python scripts/seed_demo_data.py

  With explicit env (e.g. for Railway):
    GHOSTFOLIO_API_URL=https://your-ghostfolio.up.railway.app \\
    GHOSTFOLIO_ACCESS_TOKEN=your-security-token \\
    python scripts/seed_demo_data.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_AGENT_ROOT = _SCRIPT_DIR.parent
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))

# Reuse the same seeding logic and dataset (mock_dataset.json has AAPL, TSLA, GOOG, NVDA, MSFT)
from scripts.seed_ghostfolio_for_evals import main

if __name__ == "__main__":
    sys.exit(main())
