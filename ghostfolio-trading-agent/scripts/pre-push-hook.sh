#!/bin/sh
# MVP requirements pre-push hook.
# Install: cp ghostfolio-trading-agent/scripts/pre-push-hook.sh .git/hooks/pre-push && chmod +x .git/hooks/pre-push
# From repo root, run the MVP check before allowing push.

set -e
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT/ghostfolio-trading-agent" 2>/dev/null || { echo "ghostfolio-trading-agent not found"; exit 0; }
if [ -f scripts/run_mvp_requirements.py ]; then
  echo "Running MVP requirements check..."
  if python3 scripts/run_mvp_requirements.py; then
    echo "MVP requirements passed."
  else
    echo "MVP requirements check failed. See ghostfolio-trading-agent/reports/mvp-requirements-report.json"
    exit 1
  fi
fi
exit 0
