# Prash v2 — The AI DevOps Agent

**Status:** Active build. Single source of truth for the pivot from "CI/CD fixer" to "AI DevOps agent."
**Repo:** [Drufiy/prash-v2-backend](https://github.com/Drufiy/prash-v2-backend) — new, separate from the v1 hosted service.
**Owners:** Aradhya Mishra (founder), Aryan (CTO)
**Team on this build:** Aradhya + Aryan, 2 Claude Code accounts each (4 total)
**Note:** Maneesh is on a break. His earlier Docker/Kubernetes research is referenced below as prior groundwork — nothing in this doc assumes he's actively building this sprint.
**Decided:** 2026-08-03 · **Repo + work division set:** 2026-08-09

---

## 0. The one rule everyone building this must follow

> **This file gets updated after every session and every milestone. No exceptions.**
> New bug → log it in §10, with your name. New idea, even a half-formed one → log it in §10, with your name. Finished a milestone → mark it done in §6 with the date and a one-line note on what actually shipped (not just what was planned). Changed your mind about a design decision → add a dated entry in §9, don't silently edit old ones away.
>
> If it isn't in this file, it didn't happen — for the purposes of anyone else on this team knowing about it. Chat messages and voice calls are not documentation. This file is the only thing all four Claude Code accounts, both of you, and anyone joining later can trust as current.

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
- **Aradhya owns Track B (read connectors) + Track D (diagnosis brain port + multi-failure fix).**
- **The `Action` interface is Aryan's to define and own.** Track B (Aradhya) writes connectors that *expose data*; Track C (Aryan) writes actions that *consume* that data through the Action interface. If Track B needs to change how it exposes something, that's a conversation, not a unilateral change on either side — log it in §10 before changing shared shape.
- **Nobody touches another track's files without saying so in §10 first.** If Aradhya needs to add a method to something Aryan owns (or vice versa), that's a flagged cross-track dependency (see the two explicit ones below), not a silent edit.
- Day numbers are **relative to when each person actually starts**, not calendar dates — this doc deliberately doesn't pin real dates so it doesn't go stale if someone starts a day late. When you start, write the actual date next to Day 1 in your own section below.

### Two explicit cross-track dependencies (the only places the tracks must talk to each other)

1. **Restart-pod (Track C) needs the Kubernetes connector (Track B) to exist first.** Aryan should build restart-pod against a documented mock/interface before Aradhya's real connector lands, then swap the mock for the real thing once it's pushed. Don't block on this — build the shape first.
2. **Rollback (Track C) needs to know "the last known-good revision."** Design decision made here, now, to avoid a shared-state headache: **this is a read query, not a new database.** Track B's connectors (Cloud Run / Vercel / k8s) should each expose a `get_previous_revision()`-shaped read call as part of their normal read scope. Track C's rollback action calls that, rather than Prash maintaining its own separate "release history" store. Aradhya: build this into each connector's read interface from the start, not as an afterthought.

### Day 0 (both, immediately — this is blocking)

**Aryan:** push current local work (action registry, permission-mode engine, dry-run execution, `tests/test_permissions.py`) to `prash-v2-backend` as-is, even if not fully polished. Nothing below can be planned precisely until this lands — the day numbers in Track A/C below are estimates against what was visible in a screenshot, not the real code.

**Aradhya:** once Aryan's push lands, read the actual `Action` interface and update this file's §9 decision log with what's actually there vs. what was assumed. Do not start Track B/D connector code that needs to *conform* to the Action interface until this is confirmed — but Track D's brain-porting work (below) has no dependency on Track A and can start immediately in parallel.

### Track A + C — Aryan

*Fill in your actual start date here: Day 1 = ____*

| Day | Milestone | Depends on |
|---|---|---|
| 0 | Push existing local work (registry, permission engine, dry-run, tests) to this repo | — |
| 1–2 | Harden the `Action` interface based on real usage from Track D's port (once that starts) and Track B's first connector; make sure it's documented in code (docstrings/types), since two other tracks build against it without asking you each time | Day 0 push |
| 3–4 | Wire **request-secret** for real: prompt the user, store the value locally, retry the originally-failed job. This is the no-dependency action — get it fully working end to end first | — |
| 5–6 | Wire **restart-pod** for real, against Track B's Kubernetes connector once it exists (build against a mock first if B isn't ready yet) | Track B: k8s connector (read + restart capability) |
| 7–8 | Audit log: append-only, persisted, and surfaced in the interface — every action taken, its risk tier, whether it was approved or ran automatically | — |
| 9–10 | Wire **rollback** for real, calling Track B connectors' `get_previous_revision()` | Track B: `get_previous_revision()` on relevant connectors |
| 11–12 | The interface layer itself — how a user actually reviews a finding and approves/denies, beyond raw CLI text. Resolve the open question in §8 about interface richness before this starts | — |
| 13–14 | Integration testing with Track D's decomposed multi-failure output (each independent fix becomes its own Action going through your permission engine) — coordinate directly with Aradhya on this day | Track D: multi-failure decomposition |

### Track B + D — Aradhya

*Fill in your actual start date here: Day 1 = ____*

| Day | Milestone | Depends on |
|---|---|---|
| 1–2 | **(Track D, no dependency, start immediately)** Extract `diagnosis_agent.py`, `log_fetcher.py`, `schemas.py` from `prash-backend` into this repo as a standalone package, no Supabase coupling. Confirm it's importable and callable on its own | — |
| 1–2 | *(parallel)* Confirm Track A's real `Action` interface once Aryan's Day 0 push lands; note any gap vs. what this doc assumed | Aryan: Day 0 push |
| 3–5 | **(Track B)** Kubernetes connector: pod status, logs, events (read), plus restart capability and `get_previous_revision()`-equivalent if it applies to k8s deployments. Highest priority connector — Track C's restart-pod depends on it | — |
| 6–7 | **(Track B)** Cloud Run connector: logs, deployment status, `get_previous_revision()` | — |
| 7–9 | **(Track D)** Fix the multi-failure bug: decompose N independent problems, attempt each through the (now-standalone) brain, report partial success ("fixed 3 of 4") instead of one all-or-nothing result. Validate against the real AgentCore case from 2026-08-03 (4 independent CI failures) | Track D Day 1-2 port |
| 9–10 | **(Track B)** AWS connector, read-only only this sprint (see §7 — AWS writes are explicitly out of scope) | — |
| 11–12 | Wire Track D's decomposed output into Track A's Action interface — each independent fix goes through the permission engine as its own action | Track A's Action interface finalized |
| 13–14 | Get one real outside setup (not a fork, not our own test infra) running the full watch → ping → interface → fix → verify loop | Both tracks substantially working |

### Days 13–14 (both, together)

Get this in front of at least one real outside user on their own infrastructure. **As of 2026-08-03, this has never happened even once** for Prash v1 — everything known is from testing on copies of other people's repos, which fail for reasons a real user's own repo often won't hit. This is the first real signal either version of Prash will have had.

---

## 7. Explicitly out of scope for this sprint

- The desktop app (CLI/terminal only, this round)
- Docker-layer actions beyond what's needed to support the Kubernetes connector
- AWS write actions (read/investigate only this sprint — AWS write actions are a later phase)
- Database/migration actions of any kind
- Rebuilding or touching the v1 hosted service (`prash-backend`)

---

## 8. Open questions — not yet decided

- Exact shape of the local "interface" beyond terminal output — how much richer than plain CLI text does it need to be in v1? *(Blocks Track A day 11-12 — resolve before then.)*
- Where does the watcher process live for a user without their own always-on server — does it need a lightweight hosted option, or is "runs on your laptop" acceptable for v1?
- What's the actual notification channel — OS-level, Slack, email, all three?
- Pricing/packaging implications of a local-agent model vs. the hosted v1 — not addressed in this document, needs its own pass.

---

## 9. Decision log

**2026-08-03** — Pivot approved: from CI/CD-only hosted service to general-purpose local AI DevOps agent, based on the 13-repo finding that ~60% of real failures require action, not diffs.

**2026-08-03** — Rejected: Drufiy servers holding user cloud/k8s/deploy credentials directly. Reason: unacceptable liability concentration and a materially harder enterprise sell, for a UX gain achievable another way.

**2026-08-03** — Adopted: local-first execution with local-only credentials, hosted layer limited to notifications/history/coordination (no secrets). Confirmed by Aradhya explicitly: "we should not store the users' creds and expect that we own everything, just like other AI coding IDEs."

**2026-08-03** — Confirmed: v1 hosted service (prash.drufiy.com) stays live and unmodified throughout this sprint. Not rebuilt, not retired, no new feature work on it during this fortnight.

**2026-08-03** — Team: Aradhya + Aryan (CTO) building, 2 Claude Code accounts each. Maneesh on a break; his Docker/Kubernetes research is credited groundwork for Track B, not assumed active-build involvement.

**2026-08-09** — New repo created: `Drufiy/prash-v2-backend`, separate from `prash-backend`. Scaffolding (README, this file, .gitignore) pushed by Claude at Aradhya's direction.

**2026-08-09** — Work formally divided: Aryan = Track A + C, Aradhya = Track B + D. Day-by-day breakdown written into §6.

**2026-08-09** — Aryan reported (verbally, via screenshot, not yet pushed as of this entry) working local progress on Track A: an action registry with `open-pr`, `request-secret`, `restart-pod`, `rollback` registered with risk tiers and reversibility flags; a permission-mode engine with `ask`, `auto-safe`, `environment-scoped`, and `bypass` modes, 28 passing tests in `tests/test_permissions.py`; dry-run execution producing a plan and an audit id. **This is ahead of where §6's day estimates assumed Track A would be** — the day numbers above should be corrected once the actual code is pushed and reviewed. Flagged as Day 0 action: push it.

**2026-08-09** — Design decision: rollback's "last known good" state is answered by a `get_previous_revision()`-shaped read query on each Track B connector, not a separately maintained release-history store. Avoids a third piece of shared state between Track B and C.

---

## 10. Running log — bugs, improvements, suggestions, ideas

Add to this table, don't rewrite it. Newest at the top. Every entry gets a name — this is a log of who found or thought of what, not an anonymous backlog.

| Date | Who | Type | Note |
|---|---|---|---|
| 2026-08-09 | Aradhya | Idea | Repo created (`prash-v2-backend`), work split into day-by-day plan, this file established as the single source of truth with a mandatory update-after-every-session rule. |
| 2026-08-09 | Claude (for Aryan, from screenshot) | Progress note | Track A action registry + permission engine + dry-run already working locally, unpushed. Needs Aryan to add real detail here once he's pushed and can speak to it directly — this entry is secondhand. |

