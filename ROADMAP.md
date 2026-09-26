# Lear — Production Transformation Roadmap

**Period:** 2026-09-29 → 2026-10-17 (3 weeks, 15 working days)
**Goal:** Transform Lear from a functional prototype into a production-grade, secure, reliable, and performant platform.

---

## Team

| Person | Strengths | Primary Focus Areas |
|---|---|---|
| **Anant** | Systems architecture, infra, low-level perf | Architecture, Rust migration, security protocols, infra |
| **Aryan** | Full-stack engineering, big-picture integration | Backend refactoring, server.py decomposition, API hardening |
| **Agrim** | ML engineering | Brain/diagnosis pipeline, model optimization, eval framework |
| **Avi** | LLMs, meticulous delivery, frontend skills | UI overhaul, chat/copilot UX, LLM prompt engineering |
| **Parv** | New hire, learning the stack | Testing, documentation, CI/CD, guided tasks |

---

## Architecture Overview — What Exists Today

```
┌─────────────────────────────────────────────────────────────────────┐
│  Desktop App (Tauri + React + Vite + TailwindCSS)                  │
│  25 components, pure SVG widgets, WebSocket live streaming          │
├─────────────────────────────────────────────────────────────────────┤
│  FastAPI Backend (server.py — 3,896 lines, monolith)               │
│  REST + WebSocket + SSE endpoints                                   │
├──────────────┬──────────────┬──────────────┬────────────────────────┤
│ Connectors   │ Actions      │ Brain        │ Watcher               │
│ 14 providers │ 29 actions   │ diagnosis    │ multi-provider        │
│ base.py ABC  │ dispatch.py  │ agent + LLM  │ poll + notify         │
├──────────────┴──────────────┴──────────────┴────────────────────────┤
│  Cross-Cutting: permissions · audit · circuit_breaker · credentials │
└─────────────────────────────────────────────────────────────────────┘
```

**Critical Numbers:**
- `server.py`: **165 KB / 3,896 lines** — needs decomposition
- `cli.py`: **65 KB** — needs splitting
- `diagnosis_agent.py`: **146 KB** — needs modularization
- 14 connectors, 29 actions, 41 test files, 800+ passing tests
- Desktop: 25 React components, Tauri shell, Vite build

---

## Sprint Principles

1. **Every task has an exit criterion** — not "done when it feels done"
2. **PR-per-task** — no mega-PRs, review within 24h
3. **No task starts without its test plan written first**
4. **Daily 15-min standup** — blockers surface same-day
5. **Friday demos** — end of each week, show what shipped

---

# WEEK 1 — Foundation and Security (Sep 29 – Oct 3)

**Theme:** _"Make it safe and make it clean."_
**Goal:** Security protocols in place, server.py decomposed, UI redesign started, test coverage baseline established.

---

## Security Hardening

| ID | Task | Owner | Priority | Exit Criteria |
|---|---|---|---|---|
| S-01 | **Input validation and sanitization on all API endpoints** — audit every `Body()`, `Query()`, `Path()` param in `server.py`. Add Pydantic request models with field validators. Reject malformed input with 422, not 500. | Aryan | P0 | Every endpoint has a typed Pydantic request model. Zero raw `dict` bodies accepted. Fuzz test with 50 malformed payloads — 0 crashes. |
| S-02 | **Rate limiting middleware** — add `slowapi` or custom token-bucket middleware to FastAPI. Per-IP rate limits on auth-sensitive endpoints (`/connect`, `/chat/stream`, `/chat/execute`). Global rate limit on all endpoints. | Parv | P0 | Rate limiter active. Exceeding limit returns 429 with `Retry-After` header. Integration test proves it. |
| S-03 | **CORS lockdown** — replace the current `allow_origins=["*"]` with explicit origin allowlist. Desktop app origin only in production, `localhost:*` only in dev. | Parv | P0 | `CORSMiddleware` configured with explicit origins. Test: cross-origin request from unauthorized origin is blocked. |
| S-04 | **Credential rotation and expiry detection** — add TTL tracking to credentials in `.env`. `ConnectorForm` shows expiry warnings. Backend `/api/connectors/{id}/validate` returns `expires_at` when detectable (AWS STS, GitHub PAT). | Aryan | P1 | At least AWS + GitHub connectors report credential age/expiry. UI shows amber warning when less than 7 days from expiry. |
| S-05 | **Secrets audit: scan codebase for leaked patterns** — run `gitleaks` against the full git history. Fix any findings. Add pre-commit hook to block future leaks. | Parv | P0 | `gitleaks detect --source .` returns 0 findings on HEAD. Pre-commit hook installed and documented. |
| S-06 | **Secure HTTP headers middleware** — add `X-Content-Type-Options`, `X-Frame-Options`, `Strict-Transport-Security`, `Content-Security-Policy` headers to all responses. | Parv | P1 | All 6 headers present on every response. `curl -I` test script in CI validates. |
| S-07 | **WebSocket authentication** — `/ws/events` currently has no auth. Add token-based handshake (query param JWT or first-message auth). | Aryan | P1 | Unauthenticated WebSocket connection attempt is rejected with 4001. Authenticated proceeds. Test proves both paths. |

---

## Backend Decomposition

| ID | Task | Owner | Priority | Exit Criteria |
|---|---|---|---|---|
| B-01 | **Split `server.py` into route modules** — extract into: `routes/connectors.py`, `routes/watcher.py`, `routes/chat.py`, `routes/dashboard.py`, `routes/settings.py`, `routes/notifications.py`, `routes/projects.py`, `routes/widgets.py`, `routes/activity.py`, `routes/system.py`. Keep `server.py` as the FastAPI app factory only. | Aryan | P0 | `server.py` under 200 lines. Each route module is a `FastAPI.APIRouter`. All existing tests pass without modification. Zero endpoint behavior changes. |
| B-02 | **Split `cli.py` into command modules** — extract into: `cli/commands/fix.py`, `cli/commands/watch.py`, `cli/commands/investigate.py`, etc. Keep `cli.py` as the entry-point parser builder. | Aryan | P1 | `cli.py` under 200 lines. All CLI tests pass. `prash --help` output unchanged. |
| B-03 | **Extract shared state from `server.py`** — the global variables (`_notifications`, `_activity_log`, `_watch_handles`, `_ws_clients`, `_last_verified`, etc.) into a proper `AppState` class with thread-safe access. | Aryan | P0 | Zero global mutable state in route modules. All state accessed through `request.app.state`. Race condition test with concurrent requests passes. |
| B-04 | **API versioning** — prefix all endpoints with `/api/v1/`. Add version negotiation header. Prepare the pattern for future `/api/v2/` without breaking existing clients. | Parv | P2 | All endpoints respond under both `/api/v1/...` (canonical) and `/api/...` (legacy redirect). Desktop app updated to use `/api/v1/`. |

---

## UI Overhaul — Phase 1 (Design System and Core Shell)

| ID | Task | Owner | Priority | Exit Criteria |
|---|---|---|---|---|
| U-01 | **Design system audit and token overhaul** — review `index.css`, define a comprehensive design token system: spacing scale, typography scale (Inter/Outfit from Google Fonts), color palette (current neon pink `#FF3A89` + proper neutral scale + semantic colors for status), elevation/shadow system, border-radius scale, motion/easing tokens. | Avi | P0 | `design-tokens.css` file with all tokens as CSS custom properties. Every component references tokens, not raw values. Visual diff: before/after screenshots. |
| U-02 | **Sidebar and navigation redesign** — the current `Sidebar.tsx` (16 KB) needs: smoother transitions, better active state indication, collapsible mode for more workspace, keyboard navigation support. | Avi | P0 | Sidebar collapses/expands with animation. Active page highlighted with accent. Keyboard nav works. Width transition under 200ms. |
| U-03 | **Dashboard redesign** — current `Dashboard.tsx` (50 KB) is bloated. Extract into composable sub-components: `HealthBar`, `KPIStrip`, `ActivityFeed`, `QuickActions`. Add micro-animations on data updates. | Avi | P0 | Dashboard loads in under 500ms. Each sub-component is independently testable. Stale data shows loading skeleton, not old numbers. Health score animates on change. |
| U-04 | **Component library foundation** — create reusable primitives: `Button`, `Card`, `Badge`, `Input`, `Modal`, `Dropdown`, `Tooltip`, `Skeleton`, `EmptyState`. Every future component builds on these. | Avi | P1 | `components/ui/` directory with all primitives. Each has: TypeScript types, dark-mode support, size variants, loading states. Storybook-like preview page. |

---

## Testing and Quality Baseline

| ID | Task | Owner | Priority | Exit Criteria |
|---|---|---|---|---|
| T-01 | **Measure current test coverage** — run `pytest --cov` and `vitest --coverage`. Establish baseline numbers. Identify the 10 lowest-covered modules. | Parv | P0 | Coverage report artifact in CI. Baseline numbers documented. |
| T-02 | **Add missing integration tests for `server.py` endpoint contracts** — every endpoint in the current `server.py` must have at least one happy-path and one error-path test. Cross-reference with `test_desktop_api.py`. | Parv | P1 | Every REST endpoint has 2+ tests (happy + error). Coverage for `server.py` routes at or above 70%. |
| T-03 | **Frontend test infrastructure** — set up `vitest` properly with React Testing Library. Add tests for the 5 most critical components: `Dashboard`, `Chatbot`, `Integrations`, `ServiceWidget`, `Sidebar`. | Parv | P1 | 5 component test files, each with 3+ test cases. `npm test` in CI runs them. |

---

### Week 1 — SCRUM Board Summary

| Category | Tasks | Owners |
|---|---|---|
| Security | S-01 through S-07 | Aryan, Parv |
| Backend | B-01 through B-04 | Aryan, Parv |
| UI | U-01 through U-04 | Avi |
| Testing | T-01 through T-03 | Parv |
| Architecture | Anant reviews all PRs, defines Rust migration targets | Anant |
| ML/Brain | Agrim onboards, reads codebase, maps diagnosis_agent.py | Agrim |

**Friday Demo (Oct 3):** Decomposed server running all tests green. Security middleware active. First design system tokens applied to Sidebar + Dashboard.

---

# WEEK 2 — Reliability and Performance (Oct 6 – Oct 10)

**Theme:** _"Make it fast and make it unbreakable."_
**Goal:** Error handling hardened, graceful degradation everywhere, Rust hot-path POC, UI overhaul continues, brain pipeline optimized.

---

## Reliability Engineering

| ID | Task | Owner | Priority | Exit Criteria |
|---|---|---|---|---|
| R-01 | **Global error handling middleware** — catch all unhandled exceptions in FastAPI. Return structured error responses (`{"error": str, "code": str, "request_id": str}`). Never leak stack traces to clients. Log full traces server-side with request context. | Aryan | P0 | Zero raw 500 responses in normal operation. Every error response has a `request_id`. Error logs include request method, path, duration, user context. |
| R-02 | **Connector resilience: timeout + retry + circuit breaker per-connector** — every connector's `authenticate()`, `poll_state()`, `fetch_logs()`, `get_stats()` must have: configurable timeout (default 10s), retry with exponential backoff (max 3), per-connector circuit breaker (open after 5 consecutive failures, half-open after 30s). | Anant | P0 | Each connector wrapped with timeout/retry/breaker. Test: mock a connector that fails 6 times, breaker opens, subsequent calls fail-fast without network hit, after 30s half-open, next success closes it. |
| R-03 | **Graceful degradation on the dashboard** — if a connector is down, its widgets show a clear "unavailable" state with last-known-good data + timestamp, not a crash or blank. | Avi | P0 | Manually disconnect a connector, its dashboard widgets show "Last data: 2m ago - Connector unavailable" with a muted visual state. No React error boundaries triggered. |
| R-04 | **WebSocket reconnection with backoff** — desktop `useWatcher.ts` must handle: server restart, network blip, token expiry. Reconnect with exponential backoff (1s, 2s, 4s, 8s, max 30s). Show connection status indicator in the UI. | Avi | P1 | Kill the backend server, UI shows "Reconnecting..." indicator, restart server, UI reconnects automatically within 10s, status returns to "Connected". |
| R-05 | **Health check endpoint** — `GET /api/health` returns `{"status": "ok", "uptime_seconds": N, "connectors": {...}, "version": "..."}`. This is the load balancer probe target. | Parv | P0 | Endpoint returns 200 when healthy, 503 when critical connectors are down. Response time under 50ms (no connector calls, just cached state). |
| R-06 | **Structured logging with correlation IDs** — replace all `print()` and ad-hoc `logger.info()` calls with structured JSON logging. Every request gets a UUID correlation ID propagated through all log entries. | Aryan | P1 | All logs are JSON. `grep` for a correlation ID returns the full request lifecycle. Zero `print()` statements in `prash/` (except CLI user-facing output). |
| R-07 | **Watcher crash recovery** — if a watcher poll loop crashes, it must: log the error, send a notification about the crash itself, restart the loop after a backoff, never silently die. | Anant | P1 | Kill a watcher thread mid-poll, notification fires about watcher failure, loop restarts within 10s, normal operation resumes. Audit log captures the event. |

---

## Performance and Rust Migration — Phase 1

| ID | Task | Owner | Priority | Exit Criteria |
|---|---|---|---|---|
| P-01 | **Profile the hot paths** — instrument `server.py` request handling, connector `poll_state()`, brain `diagnose_failure()`, and watcher poll loops. Identify the top 5 latency bottlenecks. | Anant | P0 | Flame graph / profiling report. Top 5 bottlenecks identified with measured times. |
| P-02 | **Rust POC: log parser** — rewrite `log_fetcher.py`'s log parsing (regex-heavy, runs on every diagnosis) in Rust using PyO3. Expose as a Python module (`lear_core.log_parser`). Benchmark: Python vs Rust on 10K-line log input. | Anant | P0 | Rust module compiles, passes the same test cases as the Python version. Benchmark shows 3x+ speedup on 10K-line input. Python fallback works when Rust module unavailable. |
| P-03 | **Rust POC: credential encryption at rest** — encrypt `.env` secrets at rest using Rust + `ring` crate (AES-256-GCM). Python calls Rust module for encrypt/decrypt. Machine-bound key derivation (PBKDF2 from machine ID). | Anant | P1 | `.env` file encrypted on disk. `prash setup` transparently encrypts. All connectors transparently decrypt. Benchmark: under 1ms overhead per decrypt call. |
| P-04 | **Async connector calls** — convert connector `poll_state()` and `get_stats()` to `async` where the underlying SDK supports it (httpx-based connectors: GitHub, GitLab, Datadog, Grafana, PagerDuty, Vercel, Snyk). Parallel gathering in the dashboard. | Aryan | P1 | Dashboard summary endpoint gathers from N connectors in parallel. Measured: latency approximately equals slowest single connector, not sum of all. Benchmark comparison before/after. |

---

## UI Overhaul — Phase 2 (Pages and Interactions)

| ID | Task | Owner | Priority | Exit Criteria |
|---|---|---|---|---|
| U-05 | **Chatbot / Copilot UX redesign** — `Chatbot.tsx` (32 KB) and `ChatMessage.tsx` (10 KB) need: better message threading, code block syntax highlighting, action card redesign, typing indicator, message reactions, copy-to-clipboard on all code blocks. | Avi | P0 | Chat feels responsive (messages render under 100ms). Code blocks have language-specific syntax highlighting. Action cards show clear status progression (pending, executing, success/fail). |
| U-06 | **Integrations page polish** — `Integrations.tsx` (26 KB): add connector health sparklines, last-sync timestamps, quick-action buttons (test / disconnect / reconfigure) that don't require expanding the card. | Avi | P1 | Each connector card shows health trend (last 1h sparkline). Card actions work without expand. Filter/search is instant (under 50ms). |
| U-07 | **Settings page cleanup** — `Settings.tsx` (28 KB): organize into tabbed sections (General, AI Models, Notifications, Security, About). Add unsaved-changes indicator and confirm-before-leave. | Avi | P1 | Settings organized into 4+ tabs. Unsaved changes show dot indicator. Navigate away with unsaved changes triggers confirm dialog. |
| U-08 | **Loading states and skeleton screens everywhere** — audit every component that fetches data. Replace blank/spinner states with skeleton screens matching the layout shape. | Avi | P1 | Every data-fetching component has a skeleton state. No "flash of empty content" on any page. Skeleton to real data transition is smooth (fade, not jump). |

---

## Brain and Diagnosis Pipeline

| ID | Task | Owner | Priority | Exit Criteria |
|---|---|---|---|---|
| M-01 | **Modularize `diagnosis_agent.py`** — this 146 KB file needs splitting: `prompts/` directory for system prompts, `formatters/` for context formatting functions, `strategies/` for diagnosis strategies. Keep the orchestrator thin. | Agrim | P0 | `diagnosis_agent.py` under 500 lines (orchestration only). Prompts in separate files. Formatter functions in separate module. All eval tests pass. |
| M-02 | **Model abstraction layer** — `kimi_client.py` (41 KB) handles multiple LLM providers but is tightly coupled. Extract into a proper provider-agnostic interface: `ModelProvider` ABC with `DeepSeekProvider`, `KimiProvider`, `GeminiProvider`, `OpenAIProvider`. | Agrim | P0 | Any model can be swapped via config without code changes. Provider failover chain: primary, fallback1, fallback2 with logged reasoning. |
| M-03 | **Diagnosis caching** — repeated diagnosis of the same failure within a time window should hit a cache instead of re-calling the LLM. Key: hash of (connector_id, resource, context_hash). TTL: configurable, default 5 min. | Agrim | P1 | Same `prash fix` on an unchanged failure within TTL returns instant cached response. Cache miss triggers normal LLM call. Cache stats in `/api/system/version`. |
| M-04 | **Eval framework hardening** — `evals/run_eval.py` never loads `.env` (known bug). Fix it. Add CI job that runs evals on every brain/ change and fails if accuracy regresses. | Agrim | P1 | `evals/run_eval.py` loads `.env` automatically. CI job runs evals on brain changes. Regression causes CI failure with diff report. |

---

### Week 2 — SCRUM Board Summary

| Category | Tasks | Owners |
|---|---|---|
| Reliability | R-01 through R-07 | Aryan, Anant, Avi, Parv |
| Performance | P-01 through P-04 | Anant, Aryan |
| UI | U-05 through U-08 | Avi |
| Brain | M-01 through M-04 | Agrim |
| Testing | Parv continues coverage expansion from Week 1 | Parv |

**Friday Demo (Oct 10):** Rust log parser benchmarked. Dashboard loads connectors in parallel. Chat UX visibly improved. Diagnosis pipeline modularized with eval CI running.

---

# WEEK 3 — Polish, Scale, and Ship (Oct 13 – Oct 17)

**Theme:** _"Make it ready for real users."_
**Goal:** Load balancing prep, end-to-end flows tested, UI pixel-perfect, Rust modules integrated, documentation complete.

---

## Infrastructure and Deployment

| ID | Task | Owner | Priority | Exit Criteria |
|---|---|---|---|---|
| I-01 | **Dockerize the backend** — create `Dockerfile` for the FastAPI backend. Multi-stage build: Rust compilation stage, then Python runtime stage. Image size under 500 MB. | Anant | P0 | `docker build` succeeds. `docker run` starts the server. All API endpoints respond correctly. Image size measured and documented. |
| I-02 | **Docker Compose for local dev** — `docker-compose.yml` with: backend (FastAPI), frontend (Vite dev server), optional Redis (for future session/cache needs). One `docker compose up` starts everything. | Parv | P1 | `docker compose up` results in full stack running. Frontend proxies to backend. Hot-reload works for both frontend and backend. README documents the setup. |
| I-03 | **Production deployment config** — Kubernetes manifests or Railway/Render config for the backend. Health check probes configured. Resource limits set. Graceful shutdown (SIGTERM handling) implemented. | Anant | P0 | Backend handles SIGTERM: stops accepting new requests, finishes in-flight ones (30s grace), closes WebSocket connections cleanly, exits 0. K8s readiness/liveness probes hit `/api/health`. |
| I-04 | **Load balancing readiness** — backend must be stateless enough for horizontal scaling. Session state (WebSocket connections, watcher handles) must be per-instance with clean reconnection. Document what is shared vs. per-instance. | Anant | P1 | Architecture doc: "Stateless API Tier" section documenting what can scale horizontally and what is pinned. WebSocket reconnection tested across instance restart. |
| I-05 | **CI/CD pipeline hardening** — GitHub Actions: add stages for lint, test, coverage, security scan, build, deploy. Fail fast on security findings. Cache dependencies. | Parv | P0 | Full pipeline runs in under 10 min. Security scan (gitleaks + pip-audit) blocks merge on findings. Coverage report posted as PR comment. |

---

## Performance and Rust Migration — Phase 2

| ID | Task | Owner | Priority | Exit Criteria |
|---|---|---|---|---|
| P-05 | **Rust: event correlation engine** — the `correlation.py` module (joins events across connectors by timestamp) is a perfect Rust target. Rewrite with PyO3. | Anant | P1 | Rust correlation module passes all `test_correlation.py` tests. Benchmark: 5x+ speedup on 1000-event correlation. Python fallback when Rust unavailable. |
| P-06 | **Rust: circuit breaker** — `circuit_breaker.py` is small (3.4 KB) but called on every action dispatch. Rewrite for zero-overhead in the hot path. | Anant | P2 | Rust circuit breaker passes all `test_circuit_breaker.py` tests. Overhead per check: under 1 microsecond. |
| P-07 | **Response compression** — add gzip/brotli compression middleware for API responses over 1 KB. | Parv | P2 | Responses over 1 KB are compressed. `Content-Encoding` header present. Measured: 50%+ size reduction on JSON responses. |

---

## UI Overhaul — Phase 3 (Polish and Delight)

| ID | Task | Owner | Priority | Exit Criteria |
|---|---|---|---|---|
| U-09 | **Micro-animations and transitions** — add page transitions (framer-motion), widget data update animations, button hover/press states, notification slide-in/out. The app should feel *alive*. | Avi | P0 | Every page transition animated (fade/slide, under 300ms). Widget data updates animate (number counting, chart morphing). Button press has scale feedback. |
| U-10 | **Responsive layout** — test and fix layout at: 1280px (laptop), 1440px (desktop), 1920px (widescreen), 2560px (4K). Sidebar collapse breakpoint. | Avi | P1 | No horizontal scroll at any resolution. Sidebar auto-collapses at under 1280px. Grid layouts adapt (3-col to 2-col to 1-col). |
| U-11 | **Accessibility pass** — WCAG 2.1 AA: focus indicators, ARIA labels, keyboard navigation, color contrast at or above 4.5:1 on all text, screen reader support for status changes. | Avi | P1 | axe-core audit: 0 critical violations. Tab through every page without mouse. Status changes announced to screen readers. |
| U-12 | **Onboarding experience** — first-run flow: welcome screen, quick connector setup (pick top 2-3), dashboard with real data. No blank states on first launch. | Avi | P1 | New user (no `.env`) sees welcome screen, guided setup, first connector connected, dashboard shows real data. Total flow under 3 min. |

---

## Brain and LLM Optimization

| ID | Task | Owner | Priority | Exit Criteria |
|---|---|---|---|---|
| M-05 | **Prompt optimization** — the system prompt in `diagnosis_agent.py` is massive (the file is 146 KB). Audit and compress: remove redundant examples, use few-shot instead of many-shot, structured output format. Measure token usage before/after. | Agrim | P0 | Token usage per diagnosis call reduced by 30%+. Eval accuracy maintained or improved. Cost-per-diagnosis documented. |
| M-06 | **Streaming diagnosis** — diagnosis currently blocks until the full LLM response arrives. Switch to streaming: partial hypotheses appear in the UI as they are generated, same pattern as `chat/stream` SSE endpoint. | Agrim | P1 | `prash fix` in the REPL shows reasoning tokens as they arrive. Desktop copilot shows streaming diagnosis. Time-to-first-token under 2s. |
| M-07 | **Multi-connector correlation** — when 2+ connectors observe the same incident, the brain should cross-reference their signals before proposing a fix. Wire `correlation.py` into the diagnosis pipeline. | Agrim | P1 | Trigger a k8s pod crash + Datadog metric spike simultaneously, brain's diagnosis references both signals. Eval test for correlated vs. single-source accuracy. |

---

## Documentation and Handoff

| ID | Task | Owner | Priority | Exit Criteria |
|---|---|---|---|---|
| D-01 | **API documentation** — auto-generate OpenAPI docs from FastAPI. Add descriptions to every endpoint. Publish at `/docs` (Swagger UI) and `/redoc`. | Parv | P0 | `/docs` shows all endpoints with descriptions, request/response schemas, and example values. Every endpoint has at least one example. |
| D-02 | **Architecture decision records (ADRs)** — document the top 5 architecture decisions: why local-first, why Rust for hot paths, why FastAPI not Django, why Tauri not Electron, why permission-tier model. | Parv | P1 | `docs/adr/` directory with 5 ADR files. Each follows the standard template (context, decision, consequences). |
| D-03 | **Contributor setup guide** — step-by-step guide for a new team member to go from clone to running tests to running the full stack. Covers: Python env, Node env, Rust toolchain, Tauri prerequisites. | Parv | P0 | A brand-new team member (or clean machine) can follow the guide and have the full stack running in under 30 min. Parv validates by following it himself. |
| D-04 | **Runbook: common operations** — how to: add a new connector, add a new action, modify a diagnosis prompt, deploy the backend, roll back a deployment. | Parv | P1 | `docs/runbooks/` with 5+ runbooks. Each has numbered steps and expected outputs. |

---

### Week 3 — SCRUM Board Summary

| Category | Tasks | Owners |
|---|---|---|
| Infra | I-01 through I-05 | Anant, Parv |
| Performance | P-05 through P-07 | Anant, Parv |
| UI | U-09 through U-12 | Avi |
| Brain | M-05 through M-07 | Agrim |
| Docs | D-01 through D-04 | Parv |

**Friday Demo (Oct 17):** Dockerized backend deployed. UI polished with animations. Rust modules integrated. Full E2E demo: connect a service, watcher detects issue, notification, copilot diagnoses, user approves fix, verification.

---

## Cross-Week Task Matrix

| Person | Week 1 | Week 2 | Week 3 |
|---|---|---|---|
| **Anant** | Architecture review, define Rust targets, security protocol design | Connector resilience (R-02), profiling (P-01), Rust log parser (P-02), Rust credential encryption (P-03), watcher recovery (R-07) | Dockerize (I-01), deployment config (I-03), load balance readiness (I-04), Rust correlation (P-05), Rust circuit breaker (P-06) |
| **Aryan** | Server.py decomposition (B-01, B-03), input validation (S-01), WebSocket auth (S-07), credential expiry (S-04) | Error handling (R-01), structured logging (R-06), async connectors (P-04), CLI split (B-02) | Final integration testing, API versioning polish, production readiness review |
| **Agrim** | Codebase onboarding, map diagnosis_agent.py, understand eval framework | Modularize diagnosis_agent (M-01), model abstraction (M-02), diagnosis caching (M-03), eval fix (M-04) | Prompt optimization (M-05), streaming diagnosis (M-06), multi-connector correlation (M-07) |
| **Avi** | Design system (U-01), Sidebar redesign (U-02), Dashboard redesign (U-03), component library (U-04) | Chatbot UX (U-05), Integrations polish (U-06), Settings cleanup (U-07), skeleton screens (U-08), graceful degradation UI (R-03), WebSocket reconnect UI (R-04) | Micro-animations (U-09), responsive layout (U-10), accessibility (U-11), onboarding flow (U-12) |
| **Parv** | Rate limiting (S-02), CORS (S-03), secrets audit (S-05), HTTP headers (S-06), test coverage baseline (T-01), integration tests (T-02), frontend tests (T-03) | Health check endpoint (R-05), continued test expansion | Docker Compose (I-02), CI/CD hardening (I-05), compression (P-07), API docs (D-01), ADRs (D-02), setup guide (D-03), runbooks (D-04) |

---

## Success Criteria — End of 3 Weeks

| Dimension | Measurable Target |
|---|---|
| **Security** | 0 leaked secrets in git history. All endpoints validated. Rate limiting active. CORS locked. WebSocket authenticated. |
| **Reliability** | Zero unhandled 500s in 1 hour of normal operation. Connectors degrade gracefully (no cascading failures). Watcher self-heals after crash. |
| **Performance** | Dashboard loads in under 2s with 5 connectors. Diagnosis with warm cache: under 3s. Rust log parser: 3x+ faster than Python. |
| **UI** | Design system applied consistently. All pages have skeleton/loading states. Micro-animations on interactions. Responsive at 1280px to 2560px. |
| **Code Quality** | `server.py` under 200 lines. Test coverage at or above 70% backend, at or above 50% frontend. Zero `print()` in backend (except CLI). |
| **Infrastructure** | Dockerized. CI pipeline under 10 min. Health check endpoint. Graceful shutdown. Deployment documented. |
| **Documentation** | API docs auto-generated. Setup guide tested by new hire. 5+ runbooks. 5+ ADRs. |

---

## Explicitly Out of Scope (These 3 Weeks)

- User tracking / analytics / statistical inference — revisit after production stability
- Data collection pipelines — not a priority now
- Agent guardrails (LLM safety) — separate initiative
- New connector integrations — stabilize existing 14 first
- Mobile app / PWA — desktop-first
- Multi-tenancy / team accounts — single-user local-first for now
- Pricing / billing — post-launch concern

---

## Daily Standup Template

```
## Standup — [Date]

### [Name]
**Yesterday:** [What was completed]
**Today:** [Task ID + what's planned]
**Blockers:** [Any blockers, who can unblock]
**PR Status:** [Any PRs waiting for review]
```

---

## Retrospective Questions (End of Each Week)

1. What shipped that we're proud of?
2. What slipped and why?
3. What should we cut from next week to make room?
4. Are the task priorities still correct?
5. Any cross-team dependencies that weren't anticipated?

---

> **Last updated:** 2026-09-26
> **Next review:** 2026-09-29 (Sprint kickoff)
