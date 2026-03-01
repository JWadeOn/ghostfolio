# Ghostfolio Trading Agent — TODO

**Last updated:** 2026-03-01

---

## Submission Deliverables (Friday/Saturday deadline)

- [ ] **Demo video (3–5 min)** — Record walkthrough showing agent capabilities, tool usage, eval results, and deployed app
- [ ] **Agent Architecture Document (1–2 pages)** — Describe ReAct pipeline, tool registry, verification layer, memory, and orchestration
- [ ] **Pre-Search Document** — Phase 1–3 checklist covering research, design, and implementation decisions
- [ ] **AI Cost Analysis** — Development costs to date + projected production costs (tokens, hosting, API calls)
- [ ] **Social post tagging @GauntletAI** — Publish on Twitter/LinkedIn showcasing the project

---

## Open Source / finagent-evals

- [ ] **Publish finagent-evals to PyPI** — Package is built (111 cases, Apache-2.0); needs `pip install finagent-evals` to work publicly
- [ ] **Create public GitHub repo for finagent-evals** — Standalone repo or publish from monorepo

---

## Engineering (Lower Priority / Phase 2)

- [x] **Persistent session storage** — Redis 24hr TTL + Postgres cold storage (AsyncPostgresSaver) connected and running on Railway
- [x] **User feedback API** — Postgres-backed `POST /api/feedback` with thumbs up/down, correction input on thumbs down, summary endpoint. Verified on Railway
- [x] **Integration smoke test** — `tests/eval/run_smoke_test.py` built; runs eval cases against live Railway deployment via Ghostfolio proxy with JWT auth
- [ ] **Output validation (schema)** — Validate agent output against JSON schema before returning
- [ ] **Human-in-the-loop escalation** — Route low-confidence or high-risk responses for manual review

---

## Known Issues

- [x] **Golden tests 34/34 passing** — Fixed gs-023 (sector concentration), gs-012 (gibberish), gs-014 (ambiguous tax), gs-030 (tax computation). System prompt now correctly routes proactive tool use while preserving edge-case clarification.
