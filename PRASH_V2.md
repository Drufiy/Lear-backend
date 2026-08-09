# Prash v2 — The AI DevOps Agent

**Status:** Active build. Single source of truth for the pivot from "CI/CD fixer" to "AI DevOps agent."
**Repo:** [Drufiy/prash-v2-backend](https://github.com/Drufiy/prash-v2-backend) — new, separate from the v1 hosted service.
**Owners:** Aradhya Mishra (founder), Aryan (CTO)
**Team on this build:** Aradhya + Aryan, 2 Claude Code accounts each (4 total)
**Note:** Maneesh is on a break. His earlier Docker/Kubernetes research is referenced below as prior groundwork — nothing in this doc assumes he's actively building this sprint.
**Decided:** 2026-08-03 · **Repo + work division set:** 2026-08-09

**Jump to:** [§0 the one rule](#0-the-one-rule-everyone-building-this-must-follow) · [§0b definition of done](#0b-definition-of-done-for-this-sprint) · [§0c stack/conventions](#0c-tech-stack-and-repo-conventions-read-before-writing-any-code) · [§1 why](#1-why-were-pivoting-context-for-anyone-reading-this-cold) · [§2 what it is](#2-what-prash-v2-actually-is-in-one-paragraph) · [§3 workflow](#3-the-workflow--concretely-step-by-step) · [§4 architecture](#4-architecture--the-part-that-determines-whether-anyone-trusts-this) · [§5 what it's allowed to do](#5-what-prash-is-allowed-to-do--the-inclusion-rule) · [§6 work division](#6-work-division--day-by-day-person-by-person) · [§7 out of scope](#7-explicitly-out-of-scope-for-this-sprint) · [§8 open questions](#8-open-questions) · [§9 decision log](#9-decision-log) · [§10 running log](#10-running-log--bugs-improvements-suggestions-ideas)

---

## 0. The one rule everyone building this must follow

> **This file gets updated after every session and every milestone. No exceptions.**
> New bug → log it in §10, with your name. New idea, even a half-formed one → log it in §10, with your name. Finished a milestone → mark it done in §6 with the date and a one-line note on what actually shipped (not just what was planned). Changed your mind about a design decision → add a dated entry in §9, don't silently edit old ones away.
>
> If it isn't in this file, it didn't happen — for the purposes of anyone else on this team knowing about it. Chat messages and voice calls are not documentation. This file is the only thing all four Claude Code accounts, both of you, and anyone joining later can trust as current.

---

## 0b. Definition of done for this sprint

At the end of 14 days, on a live system, this exact sequence works end to end:

> A Kubernetes pod is crash-looping. Prash's watcher notices and pings. The user runs `prash fix`. Prash reads the real pod logs and events, works out why, and says what it wants to do. Restarting the pod is a **safe-tier** action, so in `auto-safe` mode it just does it and reports what it did — but in `ask` mode it asks first. It then **re-checks the pod** and reports honestly whether the restart actually worked. Every step of that lands in the local audit log.

If that sequence works, the sprint succeeded, even if connectors are missing and the interface is plain text. If it doesn't, the sprint didn't succeed, however much code exists. Everything in §6 is in service of that sentence.

**Explicitly NOT required for "done":** AWS support, a rich TUI, rollback working on every platform, the desktop app.

---

## 0c. Tech stack and repo conventions (read before writing any code)

**Language/runtime:** Python 3.12. Package name is `prash` (so `python -m prash.cli`). This matches v1, and the brain being ported in Track D is Python.

**Cross-platform is a hard requirement, not a nice-to-have.** Aryan develops on **Windows/PowerShell**, Aradhya on **macOS**. Prash v2 is a CLI tool, so path handling, shell quoting, signal handling, and line endings all differ between your two machines. Use `pathlib` not string paths, never shell out to a Unix-only command without a Windows path, and assume the other person's machine will break your code if you don't. CI runs on Linux + Windows + macOS on every push for exactly this reason.

**Tests:** `pytest`. Aryan's existing `tests/test_permissions.py` sets the pattern.

**CI:** `.github/workflows/ci.yml` runs lint + tests on all three OSes on every push and PR. It is deliberately lenient while scaffolding (lint warns rather than fails; "no tests collected" passes) — tighten it once there's real code.

**Branching — this matters with 4 Claude Code accounts on one repo:**
- Nobody pushes directly to `main`.
- Branch names are prefixed by track: `track-a/...`, `track-b/...`, `track-c/...`, `track-d/...`, `track-e/...`. That way it's obvious at a glance whose work a branch is, and two accounts don't collide on the same name.
- Open a PR into `main`. CI must pass. The *other* person doesn't have to review every PR — that would be a bottleneck for two people — but anything touching a shared interface (the `Action` interface, `.env.example`, this file) does need the other's eyes before merge.
- Merge often. Long-lived branches across four parallel agents is how you get an unmergeable mess on day 10.

**Credentials:** `.env.example` is the schema; `.env` is gitignored and never committed. **Aryan owns the `.env.example` schema** (Track A owns config loading). Adding a key = log it in §10.

---

## 1. Why we're pivoting (context for anyone reading this cold)

Prash v1 is a hosted service: it watches GitHub Actions, diagnoses why a CI run failed, and opens a pull request with a fix. It works, and it's live at prash.drufiy.com.

We ran it against 13 real CI failures across 9 real open-source repos — not synthetic tests, actual broken builds on other people's projects. The result reframed the product:

**Only ~5 of 13 failures were fixable by editing a file.** The other 8 needed something Prash structurally couldn't do: add a secret, fix a permission, know a value a security scanner deliberately redacted, decide whether a stale submodule URL should be updated or the repo made public. Prash can only write diffs. It has no way to *act*.

This isn't a bug. It's the ceiling of the product as designed. No better prompt or model closes it, because the problem isn't diagnosis quality — it's that ~60% of real-world CI failures require doing something outside a code diff.

**The deeper finding:** an AI agent creates value when the *machine has more context than the human it's helping*. CI repair is structurally the worst possible place to test that, because the person who broke the build 30 seconds ago already knows more than any model can reconstruct. The places where the asymmetry flips — production incidents at 3am, Kubernetes failures with no obvious cause, a system nobody has fully in their head — are where an agent is actually worth something.

**The decision:** stop trying to perfect CI repair in isolation. Build Prash into a general-purpose AI DevOps agent — something that watches infrastructure the way Claude Code watches a codebase, and can *act* on what it finds, not just describe it.

---

## 2. What Prash v2 actually is, in one paragraph

Prash becomes a local agent, in the shape of Claude Code, that a developer or ops engineer installs and points at their own infrastructure. It runs quietly in the background watching what it's been given access to — CI, cloud logs, Kubernetes, deployments. The moment something looks wrong, it pings the user. The user opens the Prash interface, and Prash walks them through what it found, fixes it directly if the action is safe, or asks permission first if it isn't. All credentials stay on the user's own machine, in a file they control — Drufiy's servers never hold them.

---

## 3. The workflow — concretely, step by step

**Install & connect (once).**
The user installs Prash locally (CLI, npm/pip package, or eventually a desktop app). They point it at a local `.env`-style file holding their own credentials — GCP key, Kubernetes context, Vercel token, whatever they want it watching. Nothing is uploaded to Drufiy at this step. This is exactly the model Claude Code itself uses for API keys.

**Background watching.**
Once configured, a lightweight Prash process runs continuously — on the user's machine, or on a server they control — polling the systems it has access to: CI status, pod health, deploy state, error rates. This is the "always on" half of the product that a request/response CLI alone can't provide.

**Something breaks.**
Prash notices — a pod is crash-looping, a deploy failed, a CI run broke. It pings the user (desktop notification, Slack, whatever channel is configured). It does **not** silently act on anything above the "safe" tier without this step.

**The user opens the Prash interface.**
This is the working surface — modeled on Claude Code's own interaction pattern, not a static dashboard. Prash presents:
- what it found and why it thinks that's the cause
- what it wants to do about it
- for safe actions: it just does them, and shows what it did
- for anything riskier: it asks first, in plain language, before touching anything

**Verification.**
After any action, Prash checks whether it actually worked — re-checks the pod, re-runs the check, confirms the metric recovered — and reports back honestly if it didn't, rather than claiming success it can't verify.

**v1 interface scope:** a rich CLI/terminal interface (matching Claude Code's actual current form factor) ships this sprint. A full desktop app is a later phase, not part of the two-week build — don't scope it in now.

---

## 4. Architecture — the part that determines whether anyone trusts this

### The decision: credentials never leave the user's machine

We explicitly rejected Prash's servers holding user cloud/Kubernetes/deploy credentials directly. Reasoning:

- If Drufiy's servers held live AWS keys, kubectl access, and registry credentials for every customer, a breach of *our* infrastructure becomes a breach of *every customer's production environment simultaneously*. That's a fundamentally different risk class than the GitHub App token Prash v1 already holds (scoped to opening PRs, revocable by GitHub, bounded blast radius).
- Real engineering orgs run long security reviews before granting that kind of access to any third party. For a small team, that access model is close to unsellable to anyone with an actual security function, and a genuine liability if we're ever compromised.
- The alternative costs us nothing to build — it's an absence of infrastructure, not a feature. "Your keys never touch our servers" is a stronger trust claim than any encryption story, and Claude Code's own adoption is the existence proof that developers accept this model without friction.

**So:** credentials live in a local file, under the user's control, always. Drufiy's servers never receive them, never store them, never see them in transit for the purpose of *acting* on infrastructure.

### What's hosted vs. what's local

| | Runs where | Holds credentials? |
|---|---|---|
| The watcher (polls CI, cloud, k8s, deploys) | User's machine or their own server | No — reads local `.env` only |
| The action engine (diagnose, fix, restart, roll back) | User's machine or their own server | No — uses local credentials directly |
| The interface (what the user opens when pinged) | Local (CLI/terminal this sprint) | No |
| Notifications, cross-project history, team visibility | Can be hosted (Drufiy-run) | No — status and audit-log data only, never secrets |
| Prash v1's existing GitHub webhook service | Stays exactly as-is, untouched | GitHub App token only (existing, scoped, already how it works today) |

The existing hosted service (prash.drufiy.com, repo `Drufiy/prash-backend`) is **not being rebuilt or retired.** It keeps watching GitHub the way it does today. This repo (`prash-v2-backend`) is new and separate — not a fork, not a branch.

### What carries over from v1 (verified by inspection, not assumed)

We checked how tightly each part of the v1 codebase depends on the hosted database/web stack:

| Module (in `prash-backend`) | Depends on hosted stack? | Verdict |
|---|---|---|
| `diagnosis_agent.py` — prompts, guardrails, confidence logic, honest-refusal behavior (~1,200 lines) | **Zero** | Port to this repo unchanged |
| `log_fetcher.py` — log parsing, error filtering, per-job budgeting | **Zero** | Port unchanged |
| `schemas.py`, `repo_memory.py` | Zero | Port unchanged |
| `kimi_client.py` (model calling) | 3 minor spots (optional call-logging) | Port after a trivial fix |
| `processor.py` (orchestration) | Heavy (22 couplings) | Does not port — this repo gets its own orchestrator |
| `webhook.py`, `reconciler.py`, hosted routes | Heavy | Stay in `prash-backend`, untouched |

**The valuable IP — the actual diagnosis intelligence — has zero ties to the web stack and moves across as-is.** We are not starting over. We're keeping the brain and giving it a new body. This porting work is **Track D**, owned by Aradhya — see §6.

Also directly reusable from `prash-backend`: `vercel_client.py` as the template for every new connector (authenticate → locate resource → fetch logs → poll state), `deploy_repair.py` as existing proof the loop already works on non-CI failures, and the `evals/` harness for measuring whether changes actually help.

---

## 5. What Prash is allowed to do — the inclusion rule

"Eventually it does everything" is how scope dies. The rule for whether an action gets built:

> An action ships when it is **(1) needed often**, **(2) verifiable** — we can check afterward whether it worked — and **(3) reversible or low-risk**. Anything that fails (3) always requires explicit approval, regardless of permission mode, including any "bypass" automation mode.

### v1 capability set

**Read / investigate (no permission needed):**
GitHub Actions logs, Vercel build logs, Cloud Run logs, Kubernetes pod status/logs/events.

**Act — safe tier (can run without asking, in permissive modes):**
Re-run a failed job. Restart a crash-looping pod or service. Open a fix PR. Ask the user for a missing secret.

**Act — approval tier (always asks, even in bypass mode):**
Roll back a deployment. Scale resources up/down. Apply a config change.

**Never, in v1:**
Database migrations. Anything that destroys data. Anything touching production without an explicit, per-action grant.

### Permission modes (mirrors Claude Code's own model)

`read-only` → `ask every time` (default) → `auto-safe` (safe tier proceeds automatically, approval tier still prompts) → `environment-scoped` (auto on staging, always prompts on production) → `bypass` (for CI/automation use; still refuses the "never" list unconditionally).

**Status: this is already substantially built.** Aryan's local (unpushed as of 2026-08-09) work has all five modes implemented with passing tests covering exactly this matrix — see §9 decision log and §10 item from 2026-08-09.

---

## 6. Work division — day by day, person by person

### Ground rules for the split

- **Aryan owns Track A (CLI spine & permission engine) + Track C (write actions).**
- **Aradhya owns Track B (read connectors) + Track D (diagnosis brain port + multi-failure fix) + Track E (the watcher).**

> ⚠️ **Load warning, stated once and then left to Aradhya's judgement.** Aradhya's side is the heavier of the two: three connectors, the brain port, the evals port, the multi-failure fix, *and* the watcher. Aradhya explicitly chose to own the watcher (2026-08-09) and declined a rebalance. To make room, the **AWS connector has been demoted from committed work to a stretch goal** — it is read-only this sprint, no action depends on it, and it is the cheapest thing to drop. If the sprint starts slipping, drop AWS first, then descope the watcher to "polls one source" rather than cutting anything in Tracks B or D.
- **The `Action` interface is Aryan's to define and own.** Track B (Aradhya) writes connectors that *expose data*; Track C (Aryan) writes actions that *consume* that data through the Action interface. If Track B needs to change how it exposes something, that's a conversation, not a unilateral change on either side — log it in §10 before changing shared shape.
- **Nobody touches another track's files without saying so in §10 first.** If Aradhya needs to add a method to something Aryan owns (or vice versa), that's a flagged cross-track dependency (see the two explicit ones below), not a silent edit.
- Day numbers are **relative to when each person actually starts**, not calendar dates — this doc deliberately doesn't pin real dates so it doesn't go stale if someone starts a day late. When you start, write the actual date next to Day 1 in your own section below.

### Two explicit cross-track dependencies (the only places the tracks must talk to each other)

1. **Restart-pod (Track C) needs the Kubernetes connector (Track B) to exist first.** Aryan should build restart-pod against a documented mock/interface before Aradhya's real connector lands, then swap the mock for the real thing once it's pushed. Don't block on this — build the shape first.
2. **Rollback (Track C) needs to know "the last known-good revision."** Design decision made here, now, to avoid a shared-state headache: **this is a read query, not a new database.** Track B's connectors (Cloud Run / Vercel / k8s) should each expose a `get_previous_revision()`-shaped read call as part of their normal read scope. Track C's rollback action calls that, rather than Prash maintaining its own separate "release history" store. Aradhya: build this into each connector's read interface from the start, not as an afterthought.

3. **The watcher (Track E) consumes Track B's connectors and triggers Track A's interface.** Aradhya owns both E and B so the connector side is internal to him — but the *ping → user opens interface → Prash acts* handoff crosses into Aryan's territory. Agree that handoff shape before Day 10, not during it.

### Capacity assumption

**14 full-time working days, both people.** Confirmed 2026-08-09. If that stops being true, the priority tiers below tell you what to cut, in order.

### Priority tiers — cut from the bottom, never the top

Everything is ranked against §0b's definition of done. If the sprint slips, drop from tier 3 upward. Do not improvise this at day 10.

**Tier 1 — the demo does not exist without these.** Walking skeleton · k8s connector (read) · brain that can classify a runtime failure · restart-pod action · permission engine · verification · audit log · circuit breaker · watcher (k8s only).

**Tier 2 — known-valuable, but the demo survives without them.** Multi-failure fix · request-secret action · a usable interface beyond raw text.

**Tier 3 — drop these first.** Cloud Run connector · rollback action · AWS connector · anything Vercel.

### Day 0 (both, immediately — blocking)

**Aryan:** push current local work (action registry, permission-mode engine, dry-run execution, `tests/test_permissions.py`) to this repo as-is, even if unpolished. Day numbers below are estimated from a screenshot, not real code, until this lands.

**Aradhya:** once it lands, read the actual `Action` interface and record in §9 what's really there vs. what this doc assumed.

### Days 1–2 — the walking skeleton (BOTH, together, before anything real)

**This is the single most important change to the plan and it is not optional.**

Build the entire §0b path end to end with everything faked: a hardcoded "crash-looping pod", a hardcoded diagnosis, a **real** permission prompt, a fake restart that just prints, a **real** audit-log write. Nothing real underneath — but the whole path runs, and both of you agree on every seam where your code meets.

*Why:* as originally written, five tracks owned by two people met for the first time on day 13. If the shapes didn't fit, there was one day to fix it. That's the classic way a two-week sprint fails. With a skeleton on day 2, integration is continuous — each track swaps its own stub for the real thing, and a mismatch surfaces the day it's introduced.

*Done when:* `prash fix` runs the full fake path, prompts for permission, and writes an audit entry — on both Aryan's Windows machine and Aradhya's Mac.

### Track A + C — Aryan

*Actual start date: Day 1 = 2026-08-09*

| Day | Milestone | Depends on | Status |
|---|---|---|---|
| 0 | Push existing local work to this repo | — | **DONE 2026-08-09** |
| 1–2 | **Walking skeleton with Aradhya** (see above), then harden the `Action` interface with docstrings/types — two other tracks build against it without asking you each time | Day 0 push | Interface done; walking skeleton pending Aradhya |
| 3–4 | **request-secret** end to end: prompt, store locally, retry the failed job. No dependencies — the fastest proof Prash *finishes* work | Skeleton | **DONE 2026-08-09** — prompt/store + job re-run wired through the GitHub runner |
| 5–6 | **restart-pod** for real, against Aradhya's k8s connector (landing day 2) | Track B: k8s connector | Wired to `kubernetes.py` stub; needs Track B driver |
| 7 | **Circuit breaker.** Hard cap on actions per resource per time window; on breach, stop and escalate to a human. **Also: every action prompt must name its exact target** — "restart pod `api-7f9d` in namespace `production`", never "restart the pod" | **DONE 2026-08-09** — breaker in `prash/circuit_breaker.py` (persistent, `prash circuit status/reset`), wired into the dispatcher before execution; prompts now print the exact target. |
| 8–9 | Audit log: append-only, persisted, surfaced in the interface — every action, its risk tier, whether it was approved or auto-ran, and its outcome | — | **DONE 2026-08-09** — `prash audit` |
| 10–12 | The interface layer — how a user reviews a finding and approves/denies, using `rich` for formatted CLI output (§8) | — | **DONE 2026-08-09** — basic rich CLI (`run`/`actions`/`audit`/`config`/`circuit`) |
| 13 | Integration + fix whatever the skeleton's stubs were hiding | Both tracks | |
| 14 | **Demo, recorded.** The §0b sequence, on a live cluster, captured as a shareable video | Everything | |
| *stretch* | Cloud Run connector + **rollback** — grouped deliberately: rollback is your action and it needs `get_previous_revision()`, so you building the connector you depend on removes a cross-track dependency entirely | — | Rollback contract done, wired to `get_previous_revision()` stub |

### Track B + D + E — Aradhya

*Actual start date: Day 1 = ____*

| Day | Milestone | Depends on |
|---|---|---|
| 1–2 | **Walking skeleton with Aryan**, and in parallel ship a **minimal k8s read connector** (pod status, logs, events). Ship it rough on day 2 — **Aryan's day-5 restart-pod is blocked on this, so it's your highest-priority deliverable, ahead of your own deep work.** Refine it later | — | **DONE 2026-08-09** — real connector (all 5 functions) verified against a live `kind` cluster + real `CrashLoopBackOff` pod, 20 mocked unit tests added, `restart-pod`/`rollback` unblocked. |
| 3 | **(Track D)** Port `prash-backend/evals/` and get a baseline against the v1 brain **before touching it.** Days 9–10 rewrite diagnosis; without this baseline there's no way to tell if the rewrite made it worse | — | **DONE 2026-08-09** — baseline captured + harness ported, see §10. |
| 4–5 | **(Track D)** Port `diagnosis_agent.py` / `log_fetcher.py` / `schemas.py` standalone (no Supabase), make `kimi_client`'s call-logging optional. **Then extend the `Diagnosis` schema with runtime categories** — the current enum (`code`/`dependency`/`workflow_config`/`environment`/`flaky_test`/`unknown`) literally cannot express "a running service is unhealthy" | Day 3 evals | **DONE 2026-08-09** — ported to `prash/brain/`, schema extended, zero regression on the eval baseline. See §10. |
| 6–8 | **(Track D — the underestimated one)** Teach the brain Kubernetes. The prompt has **69 CI-specific references and zero runtime ones** — it has never seen a crash-loop. Write worked examples for `CrashLoopBackOff`, `OOMKilled`, `ImagePullBackOff`, failed readiness probes. Validate against the day-3 eval baseline: **CI diagnosis quality must not regress while adding runtime capability** | Day 4–5 port | **DONE 2026-08-09** — prompt taught, 19/19 valid on the eval (15 CI + 4 hand-authored k8s), zero CI regression, 100% recommended_action accuracy. Landed under the original estimate, not the overrun risk flagged in §9. See §10. |
| 9–11 | **(Track E)** The watcher: poll loop over the k8s connector, detection for the four states in §8 (`CrashLoopBackOff` / `OOMKilled` / `ImagePullBackOff` / stuck >2min), and a `plyer` desktop notification on the ping. **One source done properly**, not many done shallowly | k8s connector | **DONE 2026-08-09** — `prash watch`, verified against the real cluster with a real desktop notification firing. See §10. |
| 12–13 | **(Track D, tier 2)** Multi-failure fix: decompose N independent problems, attempt each, report "fixed 3 of 4" as partial success. Validate against the AgentCore case from 2026-08-03. **This is the first thing to sacrifice if days 6–8 overrun** | Day 4–8 | **DONE 2026-08-09** — days 6-8 did not overrun, so this stayed in scope. `prash/brain/multi_diagnosis.py`. See §10. |
| 14 | Demo with Aryan | Everything |
| *stretch* | AWS connector (read-only) | — |

### Running in parallel from Day 1 (Aradhya, ~30 min/day — not a day-13 task)

**Start recruiting the real outside user now.** Finding someone, getting them to trust an alpha CLI near their production Kubernetes, and scheduling it is a week of lead time minimum. Left until day 13, "get a real user" silently becomes day 20. Line up 3 candidates so one dropping out doesn't kill it.

### Testing actions without a real cluster

GitHub Actions cannot reach your cluster, so action tests won't run in CI unless you give them somewhere to run. Use **`kind`** (Kubernetes-in-Docker) in the workflow — it's standard and it spins up a throwaway cluster per run. **Owner: Aradhya, alongside the day 1–2 connector.** Untested action code is precisely the code that must not be untested.

**DONE 2026-08-09 — flagged as missed during the days 6-8 status check, closed same day before starting Track E.** New `k8s-live-tests` CI job (`.github/workflows/ci.yml`), Linux-only — macOS Actions runners can't do the nested virtualization Docker needs, kind-on-Windows is unreliable enough not to chase this sprint. Uses `helm/kind-action@v1`, deploys `broken-pod.yaml`, polls for real `CrashLoopBackOff` (up to 300s, observed ~15-30s locally), then runs `tests/test_kubernetes_connector_live.py` — 7 tests against the real API server: crash-loop detection (both list and by-name), the previous-attempt log fallback, real Events, `get_previous_revision` correctly returning `None` for a single-revision Deployment, and `restart_pod` actually deleting/recreating. Skipped by default (`PRASH_LIVE_K8S_TESTS=1` gate) so it never runs against a real cluster in local dev or the main mocked job by accident. Additive to the existing 3-OS job, not a replacement — that one still covers classification logic thoroughly and runs everywhere.


## 7. Explicitly out of scope for this sprint

- The desktop app (CLI/terminal only, this round)
- Docker-layer actions beyond what's needed to support the Kubernetes connector
- AWS **write** actions (read/investigate only — and even the read connector is a stretch goal, see §6 load warning)
- Database/migration actions of any kind
- Rebuilding or touching the v1 hosted service (`prash-backend`)
- A hosted layer of any kind for v2 — no dashboard, no cross-project history, no team visibility this sprint. Local only.
- Multi-source watching. Track E watches **one** source (Kubernetes) properly; watching everything is sprint 2.

---

## 7b. Sprint 2 — expansion roadmap (documented 2026-08-09, not started)

**Status: intent captured, not scheduled, not built.** Aradhya wants Prash to grow well beyond CI/CD + Kubernetes into a genuinely full-spectrum DevOps agent — the standing bar he gave: *"the agent should feel like magic — solving all your issues while you sit back and relax and just hit 'yes, permission granted.'"* This section exists so that intent isn't lost, not as a commitment to build all of it, or in this order.

**Explicit, deliberate sequencing (Aradhya's call, 2026-08-09):** this sprint's remaining scope — Track D tier 2 (multi-failure fix) and the recorded demo — finishes **first, unchanged**. Nothing below starts until that's done. This mirrors exactly how this pivot itself got decided: prove one thing works deeply and get real evidence before widening scope, not the other way around. Expanding *before* the demo would risk repeating the exact failure mode that ended v1's CI-only era — spreading thin instead of deep (§1).

**What "more" concretely means (Aradhya's list, not yet prioritized against each other):**

| Category | Examples given |
|---|---|
| Deepen Kubernetes (lowest risk — same vertical, more depth) | `scale`, `exec` into a pod, tail live logs, edit a ConfigMap/Secret |
| More CI providers | GitLab CI, CircleCI, Jenkins — same diagnosis brain, new log-fetching connectors |
| Infra / IaC | Terraform (drift/plan diagnosis), AWS **write** actions (currently read-only, §7), standalone Docker (non-k8s hosts) |
| Observability | Datadog, Grafana |
| Testing | k6, Cypress, Playwright |
| Incidents | PagerDuty |
| Security | Snyk, gitleaks |
| Dependencies | Dependabot |
| Team/notifications | Slack/Discord — a team seeing a ping, not just one laptop's desktop notification (§7 already flagged this as "sprint 2" for exactly this reason) |

**UI direction (decided 2026-08-09):** stays CLI/terminal-based — a richer TUI (live-updating panels, better formatting, possibly an actual TUI framework), **not** a desktop/web app. The GUI stays explicitly deferred (§7) — Aradhya confirmed this when asked directly, consistent with §4's original reasoning for why CLI-first matched developer trust expectations (the same reasoning that made "your keys never touch our servers" credible).

**What is NOT decided, and shouldn't be assumed:**
- Which of the categories above ship first, or in what order. This list is breadth-of-intent, not a priority-ranked backlog — turning it into one is a planning exercise for after the demo, informed by what the demo and any real outside user actually reveal is missing (the same evidence-driven method that produced this pivot, §1).
- Whether every category becomes a full read+write connector or some stay read-only/investigate-only (the same distinction §5's inclusion rule already draws for existing connectors).
- Timeline. This is explicitly "sprint 2" — no day-by-day breakdown exists for it, unlike §6's table for the current sprint, and none should be invented before the current sprint's demo actually lands.

---

## 8. Open questions

**Four of five resolved 2026-08-09 — see §9 for reasoning.** Only the genuinely non-blocking one remains open.

- ~~Exact shape of the local interface~~ → **RESOLVED: `rich` (Python), formatted CLI text. No TUI framework, no GUI, this sprint.**
- ~~Where the watcher process lives for a user without an always-on server~~ → **RESOLVED by existing scope: §7 already rules out any hosted layer this sprint. Runs on the user's own machine, full stop. Real answer is a sprint-2 question, not reopened here.**
- ~~Notification channel~~ → **RESOLVED: OS-level desktop notification via `plyer`** (cross-platform: Windows toast / macOS Notification Center / Linux notify-send).
- ~~What counts as "this looks wrong" for the watcher~~ → **RESOLVED: exactly the four states Track D is teaching the brain to diagnose** — `CrashLoopBackOff`, `OOMKilled`, `ImagePullBackOff`, and a pod stuck `Pending` or failing readiness for >2 minutes (starting default, tune after the first real test). Deliberately not a separate list — the watcher should never alert on something the brain can't yet explain, and vice versa.

**Still open, and fine to leave open — not a blocker:**
- Pricing/packaging implications of a local-agent model vs. the hosted v1. Doesn't block any of the 14 days; needs its own pass post-sprint.

---

## 9. Decision log

**2026-08-03** — Pivot approved: from CI/CD-only hosted service to general-purpose local AI DevOps agent, based on the 13-repo finding that ~60% of real failures require action, not diffs.

**2026-08-03** — Rejected: Drufiy servers holding user cloud/k8s/deploy credentials directly. Reason: unacceptable liability concentration and a materially harder enterprise sell, for a UX gain achievable another way.

**2026-08-03** — Adopted: local-first execution with local-only credentials, hosted layer limited to notifications/history/coordination (no secrets). Confirmed by Aradhya explicitly: "we should not store the users' creds and expect that we own everything, just like other AI coding IDEs."

**2026-08-03** — Confirmed: v1 hosted service (prash.drufiy.com) stays live and unmodified throughout this sprint. Not rebuilt, not retired, no new feature work on it during this fortnight.

**2026-08-03** — Team: Aradhya + Aryan (CTO) building, 2 Claude Code accounts each. Maneesh on a break; his Docker/Kubernetes research is credited groundwork for Track B, not assumed active-build involvement.

**2026-08-09** — New repo created: `Drufiy/prash-v2-backend`, separate from `prash-backend`. Scaffolding (README, this file, .gitignore) pushed by Aradhya.

**2026-08-09** — Work formally divided: Aryan = Track A + C, Aradhya = Track B + D. Day-by-day breakdown written into §6.

**2026-08-09** — Aryan reported (verbally, via screenshot, not yet pushed as of this entry) working local progress on Track A: an action registry with `open-pr`, `request-secret`, `restart-pod`, `rollback` registered with risk tiers and reversibility flags; a permission-mode engine with `ask`, `auto-safe`, `environment-scoped`, and `bypass` modes, 28 passing tests in `tests/test_permissions.py`; dry-run execution producing a plan and an audit id. **This is ahead of where §6's day estimates assumed Track A would be** — the day numbers above should be corrected once the actual code is pushed and reviewed. Flagged as Day 0 action: push it.

**2026-08-09** — Design decision: rollback's "last known good" state is answered by a `get_previous_revision()`-shaped read query on each Track B connector, not a separately maintained release-history store. Avoids a third piece of shared state between Track B and C.

**2026-08-09 (plan review, Opus)** — Reviewed the plan for gaps before any code was written. Found seven, all now addressed:

1. **The watcher was in the product description but in nobody's track.** §2/§3 describe background watching as the core of the product, but Tracks A–D built none of it — meaning the day 13–14 demo ("watch → ping → interface → fix → verify") was impossible as planned. **Resolution: Aradhya explicitly claimed it as Track E.** Scoped to one source (Kubernetes) done properly.
2. **Track D was rewriting the diagnosis brain with no eval harness.** Now the evals port is Day 1, before anything touches the brain, with an explicit baseline-vs-after comparison on Day 8–9.
3. **No branch strategy for 4 Claude Code accounts on one repo.** Now documented in §0c: no direct pushes to `main`, track-prefixed branch names, PRs with CI passing, cross-track interface changes need the other person's eyes.
4. **No CI on the repo.** Added `.github/workflows/ci.yml`.
5. **Cross-platform risk unflagged** — Aryan is on Windows/PowerShell, Aradhya on macOS, and this is a CLI tool. Now a stated hard requirement in §0c, with CI running on all three OSes.
6. **`.env` schema had no owner and no template.** Added `.env.example`; Aryan owns the schema.
7. **No definition of done for the sprint.** Added §0b as a single concrete sequence that either works or doesn't.

Also: runtime (Python 3.12, package `prash`) and test framework (pytest) were never written down. Now in §0c.

**2026-08-09 (second review pass, Opus)** — Stress-tested the revised plan. Four more findings, all now folded into §6:

1. **The brain is CI-*shaped*, not merely CI-coupled — the earlier "ports cleanly, zero coupling" note was true about database coupling and misleading about applicability.** Measured: `diagnosis_agent.py` contains **69** CI-specific references and **zero** runtime ones, and the `Diagnosis` schema's category enum (`code`/`dependency`/`workflow_config`/`environment`/`flaky_test`/`unknown`) **cannot express "a running service is unhealthy" at all.** A crash-looping pod would be forced into `unknown` — which is exactly the failure mode that produced `unknown`/40%-confidence/no-action on AgentCore on 2026-08-03. Track D is therefore substantially bigger than first written: port + extend the schema + teach an unseen domain. Aradhya chose to take this on (rather than retreating the demo to CI or using deterministic rules for k8s); budgeted as days 4–8.
2. **First integration was scheduled for day 13.** Five tracks, two people, meeting once, with one day of runway if the seams didn't fit. Replaced with a **walking skeleton on days 1–2** — whole path, all stubs, real permission prompt and real audit write. Highest-leverage change in either review pass.
3. **The critical path was inverted** — Aryan's day-5 restart-pod was blocked on Aradhya's day 3–5 connector, meaning the more-loaded person gated the less-loaded one. The k8s connector moved to **days 1–2, ahead of Aradhya's own deep work**, specifically to unblock Aryan early.
4. **No circuit breaker on actions.** Crash-loop → restart → crash → restart, unattended in `auto-safe` mode, is a self-inflicted outage. In v1 a wrong answer produced a reviewable PR; in v2 it takes down a service — the blast radius changed and nothing addressed it. Added as Aryan day 7, together with a requirement that every action prompt names its exact target.

Smaller: `kind` (Kubernetes-in-Docker) added to CI, since GitHub Actions can't reach a real cluster and action tests would otherwise never run. Real-user recruitment moved from day 13 to a day-1 parallel activity (a week of lead time, otherwise day 13 silently becomes day 20). Day 14 now explicitly produces a **recorded** demo.

**2026-08-09** — Capacity confirmed: 14 full-time working days, both people. Priority tiers added to §6 so that any slippage is cut in a pre-agreed order rather than improvised.

**2026-08-09** — Aradhya claimed Track E (the watcher) and declined a workload rebalance with Aryan. To create room, the **AWS connector was demoted from committed work to a stretch goal**. Documented drop-order if the sprint slips: AWS first, then narrow the watcher's scope — never cut from Tracks B or D, which the definition of done depends on.

**2026-08-09** — CI verified working, not just written: first run failed on all three OSes identically (a script bug — `bash -e` aborted before `pytest`'s expected exit-code-5 handling could run, since GitHub runs steps under `-e`). Fixed with `set +e`/`set -e` around the pytest call. Second run green on Linux, Windows, and macOS. Confirms the cross-platform CI is actually catching things, not just present.

**2026-08-09 — Four of five open questions resolved, to unblock Track A day 10-12 and Track E day 9-11 before either starts:**
- **Interface:** `rich` (Python) for formatted CLI output. No TUI framework, no GUI, this sprint — consistent with §3's existing "CLI/terminal this sprint, desktop app later."
- **Watcher hosting:** not actually a new decision — §7 already rules out any hosted layer this sprint, so "runs on the user's own machine" was already implied. Closed rather than re-litigated.
- **Notification channel:** `plyer`, for one library that covers Windows/macOS/Linux natively rather than three separate integrations.
- **Detection scope ("what counts as wrong"):** deliberately set to *exactly* the four states Track D is teaching the brain to diagnose (`CrashLoopBackOff`, `OOMKilled`, `ImagePullBackOff`, stuck-pending/failed-readiness >2min). Reasoning: the watcher and the brain must stay in lockstep — alerting on a state the brain can't yet explain would produce a ping Prash then fails to diagnose, which is worse than not watching for it at all. The 2-minute threshold is a starting default, not fixed — long enough to not fire during normal pod startup, short enough to still feel fast. Tune after the first real test.
- **Left open on purpose:** pricing/packaging. Doesn't block any of the 14 days.

**2026-08-09 — Day 0 blocker (Aryan hadn't pushed) opened and closed same day.** Flagged as the top open item, then resolved when Aryan's Day 0 push landed directly to `main`: Track A + C shipped in two commits — (1) action registry (`open-pr`, `request-secret`, `restart-pod`, `rollback`) with risk tiers/reversibility, the five-mode permission engine, dry-run execution, append-only audit log, and a `rich`-based CLI (`prash run/actions/audit/config`); (2) Track C wired to Track B's `connectors/kubernetes.py` stubs per cross-track deps #1/#2, with config-loading aligned to `.env.example`. 28 tests passing.

**2026-08-09 — Convention change: direct pushes to `main`, no PR gate.** §0c's "nobody pushes directly to main" + branch/PR flow was written for a 4-account team, but in practice Aradhya is pushing straight to `main` and both owners want the same for Track A/C. Rule now: still no force-push, still update PRASH_V2.md with every push, but branches/PRs are optional rather than mandatory.

**2026-08-09 — Cross-track alignment of Track C with Track B.** `restart-pod` now calls `connectors/kubernetes.restart_pod()` and `get_pod_status()`; `rollback` calls `get_previous_revision()`. Aryan's temporary `connectors/k8s.py` (class-based duplicate) was deleted. Both actions report honestly ("not implemented yet (Track B)") until Aradhya's driver lands — never a fake success. `open-pr` uses a small GitHub REST connector (Track A territory; GitHub is not in Track B's connector list).

**2026-08-09 — Circuit breaker shipped (Track A day 7).** `prash/circuit_breaker.py`: persistent per-resource cap (default 5 actions / 60s, configurable via `PRASH_CIRCUIT_*`), checked by the dispatcher before every execution; on breach, the run stops, is audited with `reason=circuit_open`, and the CLI escalates to a human with `prash circuit status/reset`. Every action prompt now prints its exact target (`Target: <resource> (<env>)`). This closes the last open Tier-1 item Aryan could build alone; the remaining Track A/C work is shared (walking skeleton, integration, demo) or blocked on Track B.

**2026-08-09 — Sprint 2 scope decided (breadth), sequencing decided (not yet), UI direction decided (stays CLI).** With Tracks A-E all landed and only tier-2 + the demo left, Aradhya asked to expand Prash well beyond CI/CD + Kubernetes — full breadth of the DevOps toolchain (more k8s actions, more CI providers, Terraform/IaC, AWS write actions, Docker standalone, observability, testing, incidents, security, dependency tooling, team notifications — full list in the new §7b). Three things were explicitly decided, one explicitly deferred:
- **Sequencing: current sprint finishes first, unchanged.** Tier 2 and the demo do not get displaced or rushed by this. Confirmed directly when asked.
- **UI: richer CLI/TUI, not a desktop/web app.** The GUI stays deferred exactly as §7 already had it — asked directly rather than assumed, given how much this reopens if wrong.
- **Scope: intent captured in full, not prioritized.** Every category Aradhya listed is documented in §7b so none of it gets lost, but this is breadth-of-intent, not a ranked backlog — turning it into one is explicitly left for after the demo, so it's driven by what real use actually reveals is missing rather than a list assembled from aspiration alone. This mirrors exactly how the original CI-repair-only scope got cut down to this sprint in the first place (§1) — not deciding priority order now was a deliberate choice, not an oversight.
- **Not decided:** which categories get built first, whether each becomes full read+write or stays read-only, any timeline for sprint 2 at all.

---

## 10. Running log — bugs, improvements, suggestions, ideas

Add to this table, don't rewrite it. Newest at the top. Every entry gets a name — this is a log of who found or thought of what, not an anonymous backlog.

| Date | Who | Type | Note |
|---|---|---|---|
| 2026-08-09 | Aradhya | Progress | **Track D tier 2 done: the multi-failure fix, `prash/brain/multi_diagnosis.py`.** The atomic-fix model breaks on real repos — "one root cause → one diagnosis → one PR" assumes N=1, but real broken CI is usually N independent failures (AgentCore, 2026-08-03: 4 unrelated failures across 4 jobs — backend ruff, contracts drift, frontend biome, mobile parity — old pipeline either picked one or gave up entirely with a single `manual_required` covering none of them). `_split_by_job_sections()` recovers per-job log chunks from the same `=== {header} ===` blob `diagnose_failure()` already consumes (no changes needed to `log_fetcher.py`, which stays CI-only/verbatim). `diagnose_multi_failure()` diagnoses each failing job independently and returns a `MultiFailureResult` — `fixed_count`/`total_count`, `combined_files_changed()` (deduped union across successful sub-diagnoses), `unresolved_summaries()` for whatever couldn't be fixed. Falls back to a single diagnosis when there's nothing to split, so it's a safe drop-in everywhere, not just known-multi cases. 10 new tests, including the exact "3 of 4" scenario from the plan's own done-bar (mocked, deterministic — a live run's actual fix/no-fix split depends on real model judgment call by call, not something to assert on non-deterministically). |
| 2026-08-09 | Aradhya | Bug (found live, fixed) | **`diagnose_multi_failure()` passed `call_type` to `diagnose_failure()`, which doesn't accept it — `call_type` is computed internally, not a caller-supplied kwarg.** Every sub-diagnosis failed with `TypeError` on the first live run; every mocked unit test passed anyway because the mock's `**kwargs` silently swallowed the bad argument. Fixed to pass `run_id=f"multi_failure_{job}"` instead (a real, accepted param, still enough to tell sub-calls apart in logs). Exactly the gap live verification exists to catch that mocks structurally cannot. |
| 2026-08-09 | Aradhya | Bug (found live, fixed) | **Firing all N sub-diagnoses concurrently via a bare `asyncio.gather` hit a real Kimi account rate limit ("max organization concurrency: 3") on a 4-job case, immediately.** Added `max_concurrency: int = 3` (matches `evals/run_eval.py`'s own default concurrency, same underlying constraint) via `asyncio.Semaphore`, bounding how many `diagnose_failure` calls are in flight at once. Verified: re-ran the same 4-job case clean, no rate-limit errors, all 4 sub-diagnoses completed with correctly attributed per-job fixes (`app/utils.py`, `openapi.yaml`, `src/components/Button.tsx`, `tests/parity.test.ts`) and a correct combined file list. Added a concurrency-bound regression test (6 jobs, `max_concurrency=2`, asserts peak in-flight calls never exceeds 2). |
| 2026-08-09 | Aradhya | Progress | **Track E done: `prash watch`, verified against the real cluster.** `prash/watcher.py` — pure `detect_changes(pods, previous_state)` is the core logic: only notifies on a NEW problem or a CHANGED problem for a given pod, never re-notifies for an ongoing unchanged one (the actual regression the whole module exists to prevent — spamming every poll interval), and a healthy/resolved pod is tracked but never triggers a ping. `run_watch_loop()` polls Track B's `get_pod_status()` on an interval (default 30s, `PRASH_WATCH_INTERVAL_SECONDS`), calls `_notify()` on changes. New `prash watch [--namespace] [--interval]` CLI command. 17 new tests (12 pure logic + 5 on the notification fallback below). Manually verified against the live `kind` cluster: deleted the running broken-app pod to force a fresh crash-loop cycle, ran `prash watch`, confirmed it correctly detected `CrashLoopBackOff` on first sighting, notified exactly once, then correctly stayed silent across 5 subsequent 5s polls with the pod still crash-looping. |
| 2026-08-09 | Aradhya | Bug (found live, fixed) | **`cmd_watch` read `KUBE_NAMESPACE` from `creds` (`.env`) directly instead of `os.environ` post-passthrough — a namespace set only via shell export was silently ignored, watched `'default'` instead.** Caught on the very first live run (watched the wrong namespace, saw 0 pods). Fixed to read `os.environ.get("KUBE_NAMESPACE", "default")`, matching `_export_cluster_env`'s own "shell wins" contract — same class of bug as the earlier `.env`→`os.environ` gap, this time in a new command rather than the connector. 2 regression tests added. |
| 2026-08-09 | Aradhya | Bug (found live, fixed) | **`plyer`'s macOS notification backend doesn't work from a plain CLI process, and installing `pyobjus` (the missing import) only got further, not further enough.** First failure: `ModuleNotFoundError: No module named 'pyobjus'` — added `pyobjus>=1.2.3; sys_platform == 'darwin'` to `pyproject.toml`. Second failure, after installing it: `AttributeError: 'NoneType' object has no attribute 'setDelegate_'` — `NSUserNotificationCenter.defaultUserNotificationCenter()` returns `None` for any process without a proper macOS app-bundle identity, which a plain venv CLI script never has. Not fixable by adding more packages. Added `osascript -e 'display notification'` as an explicit macOS-specific fallback in `_send_desktop_notification()` — the standard dependency-free mechanism CLI tools use for this exact reason. Verified: a real notification fired on the live-cluster run above (no fallback-to-console warning in the output, unlike the pre-fix run). Escapes AppleScript string literals properly (pod names/messages are not fully trusted input). Windows/Linux still go through plyer untouched — this is scoped to macOS only, where the failure was observed; flagging as an open cross-platform question whether Windows' plyer path has an equivalent gap, since only Aradhya's macOS setup could be tested here. |
| 2026-08-09 | Aradhya | Limitation (found live, not fixed — Track B follow-up) | **A pod that's been crash-looping for hours can transiently misclassify as `StuckPending` instead of `CrashLoopBackOff` on a single poll.** Seen live: `broken-app` (6+ hours old, 26 restarts) reported `StuckPending` on one `prash watch` poll, then `CrashLoopBackOff` normally after the pod was recreated fresh. Root cause: `_classify()`'s `StuckPending` fallback (`not ready and phase==Running and age>120s`) fires whenever `waiting.reason` isn't set to a known value at that exact instant — and a container's `state.waiting` briefly clears during the split-second it's actually mid-restart-attempt between backoff waits, which `_classify()`'s point-in-time snapshot can catch. Confirmed via raw `kubectl get pod -o json` at the moment of misclassification: `lastState.terminated` showed the real crash-loop history clearly even though `state.waiting` was momentarily unset. Narrow, low-frequency race — didn't fix now to avoid a rushed change to already-tested, already-live-verified classifier logic without proper coverage for this specific edge case. **Flagging for Track B/D follow-up**, likely fix: also weigh `restart_count > 0` and/or `lastState.terminated` as corroborating evidence before falling through to `StuckPending`, so a pod with restart history never gets that label even mid-flicker. |
| 2026-08-09 | Aradhya | Progress | **Track D days 6-8 done: brain taught Kubernetes, zero CI regression, landed under estimate.** Added a "KUBERNETES / RUNTIME FAILURES" section to `SYSTEM_PROMPT` with 4 worked examples (one per state: `CrashLoopBackOff` broken-image, `CrashLoopBackOff` wedged/uncertain, `OOMKilled`, `ImagePullBackOff`), plus updated `DIAGNOSIS_TOOL`'s JSON schema (category enum + new `recommended_action` property — separate from the pydantic schema, both needed updating) and the ROOT CAUSE RULES category list. Core teaching point, not just "here are 4 states": **restart_pod is not a universal fix** — it only helps a wedged/stuck process, never a genuinely broken image (ImagePullBackOff) or deterministic startup error. The prompt explicitly tells the model to tell these apart rather than default to recommending restart every time, matching the honesty-forcing pattern already used elsewhere (masked exceptions, suppression flagging). Added `format_k8s_context()` (pure formatter, Track B's `PodStatus` + logs + events → the prompt's expected text block) and fixed a real bug: the CI-shaped `_ERROR_RE` "no error signal" guard in `diagnose_failure()` would have rejected legitimate k8s cases outright, since a crash-looping pod's logs are frequently empty (per Track B's own `get_pod_logs` docstring) — added a k8s-context bypass, scoped narrowly (doesn't touch `log_fetcher.py`, which stays CI-only/verbatim from v1). |
| 2026-08-09 | Aradhya | Bug (found by the eval harness, fixed) | **Models emit the literal string `"null"` instead of JSON `null` for nullable tool-call fields — broke 2 k8s cases AND 3 unrelated CI cases in the same eval run.** `recommended_action: Literal[...] \| None` rejected the string `"null"` outright since it isn't one of the three action values, hit via both Kimi and DeepSeek. This is exactly why "validate against the eval baseline" was in the plan, not a hypothetical — first full 19-case run came back 73.7% valid_diagnosis (vs. 100% baseline), immediately visible as a regression rather than something that could've shipped unnoticed. Fixed with a `field_validator(mode="before")` normalizing `"null"`/`"none"`/`""` (case-insensitive) to `None`, mirroring the existing `_normalize_category` pattern. Re-ran: **19/19 valid, 100% category accuracy, 100% recommended_action accuracy on all 4 runtime cases, zero regression on the 15 CI cases** (actionability actually ticked up 93.3%→94.7%, normal variance). Diffed against `2026-08-09-post-track-d-port.json` (captured right after days 4-5, right before this work) to isolate what the Kubernetes prompt work changed specifically. |
| 2026-08-09 | Aradhya | Progress | **Track D days 4-5 done: brain ported to `prash/brain/`, schema extended, zero regression.** Ported `diagnosis_agent.py` (1472 lines, logic/SYSTEM_PROMPT unchanged — it's still 100% CI-shaped, teaching it Kubernetes is days 6-8, not this), `log_fetcher.py` (verbatim, zero coupling confirmed), `schemas.py`, and `kimi_client.py`. Ran the full 15-case eval against the ported brain and diffed against the pre-port baseline: **100/100/93.3/93.3/1.0 — identical on every accuracy metric**, latency p90 actually improved (43.7s→26.0s, normal API variance). Confirms the port changed nothing behaviorally. |
| 2026-08-09 | Aradhya | Design decision | **Diagnosis schema extended for Kubernetes** (the fix for "current enum can't express a running service is unhealthy"). Went with the minimal option, confirmed with Aradhya before writing 1500 lines of port: added `category="runtime"` plus a new optional `recommended_action: Literal["restart_pod", "rollback", "scale"] | None` field, rather than redesigning `fix_type` itself. `fix_type` naturally resolves to `manual_required` for runtime diagnoses via the existing `coerce_fix_type` validator (no `files_changed` = no code fix) — the dispatcher reads `recommended_action` instead when deciding what to propose. Doesn't touch the 3 existing `fix_type` values Aryan's action dispatch already keys off of. Also added category aliases (`k8s`/`kubernetes`/`infra`/`pod` → `runtime`), matching the existing alias pattern. |
| 2026-08-09 | Aradhya | Cross-track correction | **§4's architecture table was wrong about `repo_memory.py`: it said "Zero" coupling to the hosted stack — actually heavily Supabase-coupled** (every `_fetch_*` helper and `build_repo_memory()` itself query `supabase.table(...)` directly). Caught while actually reading the file for the port, not just trusting the earlier assessment. `diagnose_failure()` already treats `repo_memory` as fully optional everywhere it's used (defaults to `None`, every call site checks truthiness), so this needed zero changes to `diagnosis_agent.py` — just ported the pure `RepoMemory` dataclass + `as_prompt_context()`/`is_empty()` formatting into `prash/brain/repo_memory.py` and dropped the DB-backed builder entirely. v2 callers never pass `repo_memory`; the type stays importable in case a local (non-Supabase) memory source gets built later. |
| 2026-08-09 | Aradhya | Refactor | **`kimi_client.py` needed more than the "trivial fix" PRASH_V2.md §6 anticipated for optional call-logging** — turned out client construction itself was the bigger issue. v1 built its `AsyncOpenAI` clients at MODULE IMPORT TIME from a pydantic `Settings` object requiring `KIMI_API_KEY` to exist; v2 has no such Settings class (`CredentialStore` is deliberately dependency-free) and eager construction would crash on import in any environment without the key set — including every test run. Replaced with lazy singleton getters reading `os.environ` directly, matching `prash/connectors/kubernetes.py`'s `_client()` pattern exactly. `_log_agent_call`/`mark_agent_run_outcome` now log locally (`logger.info`) instead of writing to Supabase — same signatures, so `diagnosis_agent.py` needed zero changes to keep calling them. Extended `cli.py`'s `_export_cluster_env` passthrough (renamed conceptually, kept the function name) to also cover `KIMI_API_KEY`/`KIMI_BASE_URL`/`KIMI_MODEL`/`DEEPSEEK_API_KEY`/`DEEPSEEK_BASE_URL`/`DEEPSEEK_MODEL`/`PRIMARY_MODEL`. 18 new tests (`test_brain_schemas.py`, `test_brain_kimi_client.py`, plus 2 more in `test_cli.py`) — full suite 82/82. Added `pydantic`, `httpx`, `openai` to `pyproject.toml`. |
| 2026-08-09 | Aradhya | Progress | **Track D day 3 done: eval harness ported, pre-port baseline captured.** Ran the real 15-case golden benchmark (`evals/run_eval.py`) against the **unmodified v1 brain** in `prash-backend` before touching anything: 100% valid_diagnosis, 100% category accuracy, 93.3% actionability, 86.7% fix_type accuracy, file_recall 1.0. Saved as `evals/results/2026-08-09-pre-track-d-port-baseline.json` — every future run through days 4-8's schema/prompt changes diffs against this with `--baseline`. Ported `cases/` (15 golden JSONs) and `score.py` verbatim (zero external deps); `run_eval.py` ported with import paths pointed at `prash.brain.diagnosis_agent`/`prash.brain.kimi_client` — **not runnable yet**, those modules land in days 4-5, ported now so it isn't built twice. Did not port `seed_from_db.py` (Supabase-coupled, v2 has no DB by design) — new cases get hand-authored or copied from v1. Full suite still 64/64 after the port. |
| 2026-08-09 | Aradhya | Bug (fixed, v1 local env only) | **Found while running the baseline: v1's local `DEEPSEEK_API_KEY` was invalid (401), silently falling back to Kimi on every call** — meaning local runs were actually using Kimi even though `primary_model`/`deepseek_model` are already configured to prefer `deepseek-v4-flash`. Root cause: the real, working key had been mislabeled `DEEPSEEK_FLASH_EVAL_KEY` in `drufiy-backend/.env`, an orphaned name unreferenced anywhere in the code. Renamed to `DEEPSEEK_API_KEY` (value never seen or typed by me — pure variable-name rename in the local `.env`, with a `.env.bak-pre-rename` kept). Confirmed fixed: smoke test now hits DeepSeek directly, ~3-10x faster per case than the Kimi fallback path, no auth errors. This only touched Aradhya's local `.env`, not any deployed config — production's env vars are separate (Cloud Run), untouched. |
| 2026-08-09 | Aryan | Cross-track sync | **Track A/C synced onto Track B's real connector — combined suite green.** Fast-forwarded my local `main` onto Aradhya's `26682f2`/`54ac5a7` (they were already stacked on my `9b3d6f6`, so a clean ff, no merge). Verified Aradhya's real signatures match my action imports exactly (`get_pod_status(namespace, pod_name=None) -> list[PodStatus]`, `restart_pod -> bool`, `get_previous_revision -> dict|None`), and that `cli.py` now carries both her `_export_cluster_env` and my circuit commands. **Added one cross-track seam test** (`test_restart_pod_verify_consumes_track_b_pod_status_schema`): builds fixtures from Aradhya's real `PodStatus` dataclass (phase/ready/problem/restart_count) and asserts my `restart-pod` verify() reads them correctly — healthy pod verifies ok, `CrashLoopBackOff` pod fails verification. Breaks loudly the day those fields are renamed. Full combined suite: **64/64 passing** (my Track A/C + her connector + CLI tests). |
| 2026-08-09 | Aradhya | Progress | **Track B days 1-2 done: real Kubernetes connector shipped, replacing the stub.** `prash/connectors/kubernetes.py` — all five functions (`get_pod_status`, `get_pod_logs`, `get_pod_events`, `restart_pod`, `get_previous_revision`) implemented for real against the `kubernetes` PyPI client, then manually verified against the live local `kind` cluster and the real `CrashLoopBackOff` fixture (`testdata/broken-pod.yaml`) before any test was written — confirmed real crash-loop detection, real log fallback to the previous attempt (current attempt genuinely came back empty), real events, real pod deletion/recreation. Added `kubernetes>=29.0` to `pyproject.toml` dependencies. New `tests/test_kubernetes_connector.py`: 20 tests, fully mocked (no cluster needed in CI), covering all four failure states (`CrashLoopBackOff`, `OOMKilled`, `ImagePullBackOff`/`ErrImagePull`, `StuckPending`) plus edge cases (multi-container pods, 404-as-empty-list, log fallback, event sorting, revision detection ignoring other deployments' ReplicaSets). This unblocks Aryan's `restart-pod`/`rollback` (cross-track deps #1/#2) and Track E's watcher. |
| 2026-08-09 | Aradhya | Cross-track fix (flagging per "be careful about conflicts") | **Fixed two stale, unmocked tests in Aryan's `tests/test_actions.py`.** `test_restart_pod_reports_honestly_without_driver` and `test_rollback_with_grant_attempts_but_fails_until_track_b_read_exists` asserted on the old stub's "not implemented yet" string, now false since the real connector above landed. Worse: **neither test mocked the k8s connector** — both made live, unmocked calls to whatever cluster was configured on the machine running them, which only ever "passed" on my machine by accident (my `kind` cluster genuinely doesn't have those fake resource names, so it returned clean 404s) and would behave unpredictably on Aryan's Windows machine or in CI with no cluster at all. Renamed to `test_restart_pod_reports_failure_honestly_when_pod_missing` and `test_rollback_with_grant_fails_honestly_when_no_prior_revision`, each now uses `monkeypatch.setattr` to mock the connector function directly, with a docstring explaining the change and pointing back here. Not a shared-interface change — only test bodies, no signatures touched. Full suite: 59/59 passing, `ruff check` clean, verified in a clean venv matching CI before push. |
| 2026-08-09 | Aradhya | **RESOLVED** | **`.env`'s `KUBECONFIG`/`KUBE_CONTEXT`/`KUBE_NAMESPACE` never reached `os.environ`** — `CredentialStore.load()` only ever fed `ctx.credentials`, but the k8s connector (fixed signatures, no credentials param) can only read cluster config from the real process env or `~/.kube/config`'s current-context. Worked by accident locally (kind already sets a working default context), but a user setting `KUBE_CONTEXT` only in `.env` would silently hit the wrong cluster. Flagged to Aradhya as a 3-option decision rather than resolved unilaterally (cross-track interface); **Aradhya chose option (a).** `cli.py` now has `_export_cluster_env(creds)`, called at the top of `cmd_run`: copies those 3 keys into `os.environ`, **only if not already set** — a shell export still always wins over `.env`. Deliberately a narrow allow-list, not a blanket dump (`GITHUB_TOKEN` etc. untouched — already reaches actions via `ctx.credentials`). No signatures changed on the Track B/C interface. 4 new tests in `tests/test_cli.py` (first test file for `cli.py`). |
| 2026-08-09 | Aradhya | Bug (fixed) | **`main` was broken: CI failing on all 3 OSes** (`ModuleNotFoundError: No module named 'prash'`). Root cause: `ci.yml`'s install step predates `pyproject.toml` and only ever handled `requirements.txt` — it never ran `pip install -e .`, so the moment Aryan's real code landed with `from prash.actions...` imports, every test failed to even collect. Fixed by adding `pip install -e ".[dev]"` when `pyproject.toml` is present. Verified locally in a clean venv before pushing: 28/28 tests pass. (Initially logged Aryan's two code commits as suspiciously "never triggering CI" — checked the timestamps, they're normal: `git push` fires one workflow run per push, not per commit, and all three commits arrived in one push. Not a bug, correcting the record rather than leaving a wrong claim standing.) |
| 2026-08-09 | Aryan | Progress | **Circuit breaker + runner wiring done (Track A day 7, Tier 1 complete).** `prash/circuit_breaker.py` — persistent per-resource cap, dispatcher-enforced before execution, `prash circuit status/reset` to escalate/close. `request-secret` now actually re-runs the blocked GitHub job via `GitHubRunner` (`re_run_job` on the latest failed run). Exact-target prompts added (`Target: <resource> (<env>)` in every proposal). 39 tests passing. |
| 2026-08-09 | Aryan | Setup | Added `PRASH_CIRCUIT_MAX_ACTIONS` / `PRASH_CIRCUIT_WINDOW_SECONDS` / `PRASH_CIRCUIT_STATE_PATH` to `.env.example` (schema owner is Track A). Logged per the §10 rule for new keys. |
| 2026-08-09 | Aryan | Progress | **Track A + C landed on `main`.** Action registry (`open-pr`, `request-secret`, `restart-pod`, `rollback`) with risk tiers + reversibility; five-mode permission engine; append-only audit log (`.prash/audit.log`, configurable via `PRASH_AUDIT_LOG_PATH`); dry-run plans; `rich` CLI (`prash run/actions/audit/config`); 28 tests passing. `request-secret` closes the `needs_secret` dead end — asks for the value, stores it in the local `.env` only, re-triggers the job. |
| 2026-08-09 | Aryan | Setup | Added `pyproject.toml` (runtime dep: `rich`), the first packaging file in this repo — per the §10 note that whoever adds one first must log it. Package name `prash`, so `python -m prash.cli` works as the docs specify. |
| 2026-08-09 | Aryan | Cross-track | `restart-pod` + `rollback` wired to Aradhya's `connectors/kubernetes.py` stubs (cross-track deps #1/#2): restart calls `restart_pod()`/`get_pod_status()`, rollback calls `get_previous_revision()`. Deleted my duplicate `connectors/k8s.py`. Both report "not implemented yet (Track B)" honestly until the driver lands. `open-pr` uses a small GitHub REST connector kept in `connectors/github.py` (Track A; GitHub isn't in Track B's list). |
| 2026-08-09 | Aryan | Decision | Convention: direct pushes to `main` (matching how Aradhya has been working) instead of §0c's branch+PR flow. Logged in §9. |
| 2026-08-09 | Aradhya | Setup | **Local dev cluster is live.** Docker Desktop installed + running, `kind create cluster --name prash-dev` succeeded, node `Ready`. Set `.env`'s `KUBE_CONTEXT=kind-prash-dev` (kind auto-sets this as your active kubectl context too). Deployed a deliberately broken pod (`prash/connectors/testdata/broken-pod.yaml`) and confirmed it reaches real `CrashLoopBackOff` in ~15s with real events and real logs — this is the exact fixture to develop `get_pod_status`/`get_pod_logs`/`get_pod_events` against. **Track B's local blocker is now fully clear.** |
| 2026-08-09 | Aradhya | Setup | Local dev environment: `kind` + `kubectl` installed via Homebrew. **Docker Desktop still needs manual install** (macOS requires approving a system extension — can't be done non-interactively). Get it from docker.com, then `kind create cluster` gives a real, disposable local cluster to build Track B against. |
| 2026-08-09 | Aradhya | Scaffold | Added `prash/__init__.py`, `prash/connectors/__init__.py` + `kubernetes.py` (stubs, `NotImplementedError`, function signatures matching §6's spec — pod status/logs/events, restart, `get_previous_revision`), and `prash/brain/__init__.py` (empty, docstring pointing at the day 1-2 port). Deliberately narrow — nothing at repo root, nothing that could collide with wherever Aryan's action registry lands. **No `requirements.txt`/`pyproject.toml` yet** — the `kubernetes` PyPI package is needed for the connector and isn't declared anywhere. First person to need it, add it and log it here. |

*(A first pass of setup notes, plan-review findings, and same-day resolved blockers was pruned from this table on 2026-08-09 — everything in it either went stale (e.g. "Aryan hasn't pushed", resolved same day) or fully duplicated detail that's kept in §9's decision log or §6/§8's live status. Nothing unique was lost; see git history on this file if you need the exact original wording.)*

