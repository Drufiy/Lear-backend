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

*Actual start date: Day 1 = ____*

| Day | Milestone | Depends on |
|---|---|---|
| 0 | Push existing local work to this repo | — |
| 1–2 | **Walking skeleton with Aradhya** (see above), then harden the `Action` interface with docstrings/types — two other tracks build against it without asking you each time | Day 0 push |
| 3–4 | **request-secret** end to end: prompt, store locally, retry the failed job. No dependencies — the fastest proof Prash *finishes* work | Skeleton |
| 5–6 | **restart-pod** for real, against Aradhya's k8s connector (landing day 2) | Track B: k8s connector |
| 7 | **Circuit breaker.** Hard cap on actions per resource per time window; on breach, stop and escalate to a human. **Also: every action prompt must name its exact target** — "restart pod `api-7f9d` in namespace `production`", never "restart the pod" | — |
| 8–9 | Audit log: append-only, persisted, surfaced in the interface — every action, its risk tier, whether it was approved or auto-ran, and its outcome | — |
| 10–12 | The interface layer — how a user reviews a finding and approves/denies, using `rich` for formatted CLI output (§8) | — |
| 13 | Integration + fix whatever the skeleton's stubs were hiding | Both tracks |
| 14 | **Demo, recorded.** The §0b sequence, on a live cluster, captured as a shareable video | Everything |
| *stretch* | Cloud Run connector + **rollback** — grouped deliberately: rollback is your action and it needs `get_previous_revision()`, so you building the connector you depend on removes a cross-track dependency entirely | — |

### Track B + D + E — Aradhya

*Actual start date: Day 1 = ____*

| Day | Milestone | Depends on |
|---|---|---|
| 1–2 | **Walking skeleton with Aryan**, and in parallel ship a **minimal k8s read connector** (pod status, logs, events). Ship it rough on day 2 — **Aryan's day-5 restart-pod is blocked on this, so it's your highest-priority deliverable, ahead of your own deep work.** Refine it later | — |
| 3 | **(Track D)** Port `prash-backend/evals/` and get a baseline against the v1 brain **before touching it.** Days 9–10 rewrite diagnosis; without this baseline there's no way to tell if the rewrite made it worse | — |
| 4–5 | **(Track D)** Port `diagnosis_agent.py` / `log_fetcher.py` / `schemas.py` standalone (no Supabase), make `kimi_client`'s call-logging optional. **Then extend the `Diagnosis` schema with runtime categories** — the current enum (`code`/`dependency`/`workflow_config`/`environment`/`flaky_test`/`unknown`) literally cannot express "a running service is unhealthy" | Day 3 evals |
| 6–8 | **(Track D — the underestimated one)** Teach the brain Kubernetes. The prompt has **69 CI-specific references and zero runtime ones** — it has never seen a crash-loop. Write worked examples for `CrashLoopBackOff`, `OOMKilled`, `ImagePullBackOff`, failed readiness probes. Validate against the day-3 eval baseline: **CI diagnosis quality must not regress while adding runtime capability** | Day 4–5 port |
| 9–11 | **(Track E)** The watcher: poll loop over the k8s connector, detection for the four states in §8 (`CrashLoopBackOff` / `OOMKilled` / `ImagePullBackOff` / stuck >2min), and a `plyer` desktop notification on the ping. **One source done properly**, not many done shallowly | k8s connector |
| 12–13 | **(Track D, tier 2)** Multi-failure fix: decompose N independent problems, attempt each, report "fixed 3 of 4" as partial success. Validate against the AgentCore case from 2026-08-03. **This is the first thing to sacrifice if days 6–8 overrun** | Day 4–8 |
| 14 | Demo with Aryan | Everything |
| *stretch* | AWS connector (read-only) | — |

### Running in parallel from Day 1 (Aradhya, ~30 min/day — not a day-13 task)

**Start recruiting the real outside user now.** Finding someone, getting them to trust an alpha CLI near their production Kubernetes, and scheduling it is a week of lead time minimum. Left until day 13, "get a real user" silently becomes day 20. Line up 3 candidates so one dropping out doesn't kill it.

### Testing actions without a real cluster

GitHub Actions cannot reach your cluster, so action tests won't run in CI unless you give them somewhere to run. Use **`kind`** (Kubernetes-in-Docker) in the workflow — it's standard and it spins up a throwaway cluster per run. **Owner: Aradhya, alongside the day 1–2 connector.** Untested action code is precisely the code that must not be untested.


## 7. Explicitly out of scope for this sprint

- The desktop app (CLI/terminal only, this round)
- Docker-layer actions beyond what's needed to support the Kubernetes connector
- AWS **write** actions (read/investigate only — and even the read connector is a stretch goal, see §6 load warning)
- Database/migration actions of any kind
- Rebuilding or touching the v1 hosted service (`prash-backend`)
- A hosted layer of any kind for v2 — no dashboard, no cross-project history, no team visibility this sprint. Local only.
- Multi-source watching. Track E watches **one** source (Kubernetes) properly; watching everything is sprint 2.

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

**2026-08-09** — New repo created: `Drufiy/prash-v2-backend`, separate from `prash-backend`. Scaffolding (README, this file, .gitignore) pushed by Claude at Aradhya's direction.

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

**2026-08-09 — The one blocker that remains: Aryan has still not pushed.** Checked directly against the repo — only Aradhya's commits exist. Every date in Aryan's Track A/C schedule (§6) is still an estimate from a screenshot, not a confirmed number. This is the single highest-priority open item and supersedes everything else in this log.

---

## 10. Running log — bugs, improvements, suggestions, ideas

Add to this table, don't rewrite it. Newest at the top. Every entry gets a name — this is a log of who found or thought of what, not an anonymous backlog.

| Date | Who | Type | Note |
|---|---|---|---|
| 2026-08-09 | Claude (Sonnet) | Blocker | **Aryan still hasn't pushed** (checked directly against the repo, commit history is Aradhya-only). Highest-priority open item — everything in Aryan's §6 schedule is still an estimate until this lands. |
| 2026-08-09 | Claude (Sonnet) | Decision | Closed 4 of 5 open questions from §8 to unblock Track A day 10-12 and Track E day 9-11: `rich` for the interface, `plyer` for notifications, watcher stays local per §7 (not a new decision), and watcher detection scope set to exactly Track D's four Kubernetes categories so the watcher and brain never drift apart. Pricing left open on purpose — not a sprint blocker. |
| 2026-08-09 | Claude (Sonnet) | Verification | CI confirmed actually working, not just present: first run failed identically on all 3 OSes (a real script bug — `bash -e` swallowing pytest's exit code 5 before the handling for it could run), fixed, second run green on all 3. |
| 2026-08-09 | Claude (Opus, review 2) | Bug (plan) | **The `Diagnosis` schema cannot represent a runtime failure.** Category enum has no value for "running service unhealthy". Must be extended before the k8s demo can work — this is on the critical path, not a nice-to-have. Track D days 4–5. |
| 2026-08-09 | Claude (Opus, review 2) | Risk | **The brain has never seen a Kubernetes problem.** 69 CI references, 0 runtime references in the diagnosis prompt. Teaching it is budgeted at days 6–8 and is the most likely source of overrun in the sprint. If it overruns, drop the multi-failure fix (tier 2) — do not drop the watcher or connector. |
| 2026-08-09 | Claude (Opus, review 2) | Improvement | Walking skeleton on days 1–2 replaces day-13 big-bang integration. |
| 2026-08-09 | Claude (Opus, review 2) | Improvement | Circuit breaker added — unattended restart loops are a real outage scenario now that actions touch live systems. |
| 2026-08-09 | Aradhya | Decision | Claimed Track E (watcher) personally; declined rebalancing Track B/D load with Aryan. AWS connector demoted to stretch to compensate. |
| 2026-08-09 | Claude (Opus, plan review) | Improvement | Seven gaps found and fixed before code was written — see the full entry in §9. Biggest: the watcher existed in the product description but in nobody's track, making the planned day-13 demo undeliverable. |
| 2026-08-09 | Claude (Opus) | Risk | **Aradhya's load is the sprint's main risk.** Three connectors + brain port + evals port + multi-failure fix + watcher, against Aryan's Track A/C. Drop order if it slips is written into §6 — follow it rather than improvising. |
| 2026-08-09 | Claude (Opus) | Risk | **Cross-platform.** Aryan on Windows, Aradhya on macOS, building a CLI. CI now covers all three OSes, but expect this to bite at least once — most likely on path handling or shelling out. |
| 2026-08-09 | Aradhya | Idea | Repo created (`prash-v2-backend`), work split into day-by-day plan, this file established as the single source of truth with a mandatory update-after-every-session rule. |
| 2026-08-09 | Claude (for Aryan, from screenshot) | Progress note | Track A action registry + permission engine + dry-run already working locally, unpushed. Needs Aryan to add real detail here once he's pushed and can speak to it directly — this entry is secondhand. |

