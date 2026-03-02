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
- [x] **Output validation (schema)** — Pydantic v2 `AgentResponse` model validates all output in `format_output_node()` and error handler; fallback on validation failure
- [x] **Human-in-the-loop escalation** — Low-confidence/guardrail/guarantee-language responses flagged `escalated: true`, queued in Postgres with review endpoints (`GET /api/escalations`, `POST /api/escalations/{id}/resolve`, `GET /api/escalations/summary`)
- [x] **Seed default admin & demo users** — `prisma/seed.mts` now creates admin user (ANONYMOUS provider, ADMIN role, hashed access token), demo user (DEMO role), accounts, settings, and `DEMO_USER_ID`/`DEMO_ACCOUNT_ID` properties. Enables out-of-the-box login and "Try Demo" button. Idempotent via upserts. Reads `ACCESS_TOKEN_SALT` and optional `DEFAULT_ADMIN_TOKEN` from env.

---

## Known Issues

- [x] **Golden tests 34/34 passing** — Fixed gs-023 (sector concentration), gs-012 (gibberish), gs-014 (ambiguous tax), gs-030 (tax computation). System prompt now correctly routes proactive tool use while preserving edge-case clarification.
- [x] **Hallucination rate below 5% target** — Was 7.8%, now 4.7%. Fixed two false-positive sources in `verification.py`: (1) `_check_facts` no longer flags user-provided numbers on no-tool queries (empty `tool_results` early return), (2) `_check_authoritative_consistency` accepts 90-day wash-sale analysis windows alongside 30/60/61. All 6 PRD §3.7 performance targets now pass.
