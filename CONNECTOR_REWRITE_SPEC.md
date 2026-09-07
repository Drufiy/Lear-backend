# Connector Rewrite — System Spec

**Status:** Approved plan, work not yet started. Single source of truth for this initiative — same discipline as `PRASH_V2.md`: update this file and Notion after every milestone, no exceptions.
**Owners:** Anant (connector read-interface + real execution) · Aradhya (NLP/diagnosis-brain side, watcher refactor, correlation, test environment)
**Related Notion tasks:** [Rewrite every connector](https://app.notion.com/p/3ca7710d2e9381c18da5f3fa993f2c11) (Anant) · [Extend the diagnosis brain via NLP](https://app.notion.com/p/3ca7710d2e9381baa1bccf810437ca77) (Aradhya)

---

## 0. Standing rules for this doc

> This file gets updated after every milestone — with the date and what actually shipped, not what was planned. If a decision changes, add a new dated line; don't silently edit old ones away. If it isn't in this file or Notion, it didn't happen for anyone else on the team.

**Note for Aradhya's Claude Code sessions only:** always wait for Aradhya's explicit go-ahead before writing any code for his milestones in this plan. This does **not** apply to Anant — he works independently and isn't gated by this.

---

## 1. Why this exists

Two Tier 1 Notion tasks are stuck in a chicken-and-egg loop:

- Anant's ["Rewrite every connector"](https://app.notion.com/p/3ca7710d2e9381c18da5f3fa993f2c11) — still "To Do."
- Aradhya's ["Extend the diagnosis brain via NLP"](https://app.notion.com/p/3ca7710d2e9381baa1bccf810437ca77) — blocked on the above; nothing new to build against.

This doc breaks the loop: agree on a shared interface first (§4), then move in parallel down a milestone plan (§6) that proves the whole loop on **one** connector before scaling to all ten.

## 2. The bigger goal — this is the competitive bet, not a cleanup

Per Aradhya, 2026-08-30: *"by better tech I mean everything — already the USPs we have and we would like to have faster diagnosis, better accuracy, multi-connector correlation etc."*

On top of Lear's existing USPs (local-first, credentials never leave the user's machine, every write human-approval-gated), this rewrite is the foundation for three concrete, **measurable** gains (targets in §3):

| Goal | What actually changes | Where it lives |
|---|---|---|
| **Faster diagnosis** | Connectors expose `watch()` so Lear holds context proactively instead of cold-starting every diagnosis pass from scratch; multi-connector reads during one pass run in parallel, not sequentially. | Read interface (`base.py`), watcher (`watcher.py`), diagnosis brain |
| **Better accuracy** | Before proposing a fix, cross-check against ≥2 independent sources when more than one connector is available, instead of diagnosing off a single log stream. | Diagnosis brain, correlation module (M6) |
| **Multi-connector correlation** | A pod crash + a Datadog metric spike + a recent deploy get recognized as *one* incident with one root cause, not three unrelated alerts — because every connector emits the same `ConnectorEvent` shape onto one shared timeline. | Correlation module (M6), `ConnectorEvent` (§4) |

The differentiation: none of the "weakest surface" connectors (Datadog/Grafana/PagerDuty-tier monitoring — the 2026-08-28 finding that small-team ICP users hit these before Lear's strong CI/k8s surfaces) support any of this today. Getting there first, with **real execution** and not read-only investigation, is the edge over competitors who stop at "read logs, suggest a fix."

## 3. Success metrics (baseline measured at M0; target proven at M6)

We commit to numbers so "better tech" is provable, not asserted. **Baselines are measured, never guessed** — the cells below are filled in at M0 against the standard fixture (§7), on the same machine, before any rewrite code lands.

| Metric | How it's measured | Baseline (fill at M0) | Target (prove at M6) |
|---|---|---|---|
| Cold-start diagnosis wall-time | Time from `prash fix` to first proposed hypothesis on the standard fixture, median of 5 runs | **8.09 s** (median; min 7.18, max 11.29; n=5) — measured 2026-09-06, `kind-prash-dev` / `prash-demo`, standard fixture `broken-app` (CrashLoopBackOff, config-file-missing), `fix --dry-run --mode read-only` | Meaningfully lower with `watch()` warm vs cold (set exact % at M0 once baseline is known) |
| Single-source false-positive rate | On a fixture set with a known root cause, % of runs whose top hypothesis is wrong when diagnosing off one connector only | **0/3 (0%)** — measured 2026-09-06 on the 3 known k8s fixtures (config-missing, OOMKilled, missing-ConfigMap), all top hypotheses correct. Caveat: these are unambiguous single-signal cases where k8s events name the cause directly; the correlation gain is expected on *ambiguous multi-signal* incidents, which the M6 combined fixture (§7) provides — that harder set is the real comparison basis. **Status 2026-09-07 (measured, not guessed — first real attempt):** built `scripts/testing/measure_correlation_accuracy.py` — 2 purpose-built ambiguous scenarios (Postgres connection-pool saturation misread as network failure; a degraded downstream `payment-service` misread as a `checkout-api` problem), each run through `diagnose_failure()` twice (real LLM calls, single-source k8s context vs. k8s+correlated-Datadog context), graded against a known true cause. **Result: 0/2 wrong on both single- and multi-source — no false-positive gap materialized.** Honest reason, not a fudge: the diagnosis brain's system prompt is already conservative enough that on both scenarios it declined to guess a specific wrong action from ambiguous single-source evidence (`recommended_action: None` both times, correctly avoiding e.g. `restart_pod`) — the spec's "% wrong actions" framing assumes single-source produces a *confidently wrong* answer, but this brain's actual failure mode on ambiguous evidence is "correctly uncertain," not "confidently wrong." **A real signal did show up, just not the one the metric was built to catch:** confidence rose 0.65→0.85 in the payment-service scenario when the correlated signal was added (Postgres scenario stayed 0.85→0.85, already high). **Open finding, not closed:** either (a) redefine this metric around confidence/specificity delta rather than binary correctness, since correctness rarely differs against a conservative brain, or (b) construct harder scenarios where the brain's conservative default doesn't rescue it (e.g. where staying silent is itself the wrong call). Not deciding unilaterally which — flagging both options. | Lower with 2-source correlation than single-source, on the same set |
| Parallel vs sequential read latency | Wall-time to gather state from N connectors in one pass | **Per-connector k8s read: `poll_state` ~4 ms, `get_stats` ~3 ms** (median, n=5, 2026-09-06). Full N-connector sequential baseline is **not measurable on this machine** — only Kubernetes is live (AWS/GCP/Datadog need creds not present); the true sequential-vs-parallel comparison lands at M6 with the combined k8s+Datadog fixture. Logged as a §8 finding, not guessed | Approaches slowest-single-connector time, not the sum |

If a target turns out to be unmeasurable or the baseline shows the gain is marginal, that's a finding to log in §8 — not a number to massage.

## 4. The interface — reconciled with the code that already exists

**Read this before proposing signatures.** Lear already has a clean two-layer architecture. The rewrite extends it; it does **not** invent a parallel one.

- **Read/state layer — `prash/connectors/`.** Base class `Connector` in `connectors/base.py` (abstract `authenticate()`, `locate()`, plus `fetch_logs()`, `poll_state() -> ResourceState`, and `read_capabilities`/`write_capabilities` metadata). Every connector is a class `XConnector(Connector)` — **except `kubernetes.py`, which is module-level functions and is the odd one out** (see M1).
- **Write layer — `prash/actions/`.** Every write is already a discrete `Action` subclass with an `ActionSpec(id, summary, risk_tier, reversible, capabilities, approval_hint)`, dispatched through `prash/dispatch.py` against `prash/permissions.py`. Real examples in the tree today: `datadog_mute` (SAFE), `grafana_silence` (SAFE), `restart_pod` (SAFE), `rollback` (APPROVAL), `scale` (APPROVAL), `pagerduty_incident`, `execute_aws/gcp/azure`, `vercel_deploy`, `snyk_ignore`, `gitleaks_escalate`, `open_pr`.

So the three new capabilities land in **two different layers**, not one:

### 4a. `watch()` and `get_stats()` → read layer, on the `Connector` ABC

Added to `connectors/base.py` as concrete-default methods (raising `NotImplementedError`, same as `fetch_logs`/`poll_state` do today), then implemented per connector:

```python
def watch(self, target: str) -> "WatchHandle":
    """Begin monitoring `target`; the handle feeds the shared watcher loop (§4c)."""

def get_stats(self, target: str, since: datetime | None = None) -> list["ConnectorEvent"]:
    """Return a time series of normalized events for `target`, optionally since a time."""
```

**Reconciliation with existing methods — do not duplicate them:**
- `poll_state() -> ResourceState` stays as-is: the *point-in-time* health check ("what is the state right now").
- `get_stats()` is the *time series* ("what happened, on a shared clock"). It may call `poll_state()`/`fetch_logs()` internally; it does not replace them.
- `ResourceState`/`ConnectorState` (existing) describe current health; `ConnectorEvent` (new, below) is the cross-provider timeline row. Both coexist.

### 4b. `alert()` → write layer, a new gated `Action` per provider (NOT a loose method)

Pushing an outbound alert is a side-effecting write. It must go through the same path as every other write — an `Action` with a risk tier — or it bypasses Lear's core human-approval USP. Concretely, one new action per provider that can alert (e.g. `datadog_alert`, `pagerduty_page`), each:

```python
class PagerDutyPageAction(Action):
    spec = ActionSpec(
        id="pagerduty-page",
        summary="Page an on-call responder via PagerDuty",
        risk_tier=RiskTier.APPROVAL,   # outbound + not cleanly reversible → always asks
        reversible=False,
        capabilities=("alert",),
    )
```

Default tier for outbound alerts is **APPROVAL** (always prompts, even in bypass mode). A provider whose "alert" is genuinely reversible and internal-only may argue SAFE at M0 — decided per provider, in code, with the reasoning logged.

### 4c. Shared event shape (`ConnectorEvent`) — the thing correlation joins on

```python
class ConnectorEvent(TypedDict):
    timestamp: datetime   # UTC, required — correlation sorts and joins on this
    connector: str        # e.g. "datadog", "kubernetes", "github"
    event_type: str       # e.g. "metric_spike", "pod_crash", "deploy", "ci_failure"
    summary: str          # one human-readable line — what the diagnosis brain reads first
    raw: dict             # untouched provider-specific payload, for drill-down
```

### 4d. The existing watcher gets refactored, not duplicated

`prash/watcher.py` + the `prash watch` command already exist (owner: Aradhya) but are **hardcoded to the Kubernetes connector**. Decision (2026-08-30): refactor `watcher.py` to poll *any* connector's `watch()`/`get_stats()`, so there is **one** watch system, multi-connector — not a second one. This is an explicit milestone on Aradhya's side (M5) and it touches existing Aradhya-owned code.

### 4e. Backward-compatibility guarantee (holds for every milestone)

No connector loses a capability it has today. The existing `run <action>` commands, `poll_state`/`fetch_logs`, `datadog_mute`/`grafana_silence`/etc., and today's `prash watch` all keep working throughout the migration. "Extend, never break" — any milestone that would regress current behavior is not done.

## 5. Terraform — now real, folded into the rollout

Terraform landed 2026-08-30 (Anant, commit `0e3fd33`): `connectors/terraform.py` is a proper `TerraformConnector(Connector)` (`authenticate`/`fetch_logs`/`poll_state`), with `terraform-init` (SAFE) and `terraform-apply` (APPROVAL) as gated Actions in `prash/actions/`. It was built to exactly the two-layer pattern §4 describes — useful independent confirmation the architecture is right. It still needs the `watch()`/`get_stats()`/`alert` treatment like every other connector, so it's included in the Phase 3 rollout (§6). *(Supersedes the earlier "Terraform doesn't exist / out of scope" note — that was true at the start of the day, not after `0e3fd33`.)*

## 6. Milestone plan

**Team convention (logged 2026-08-09):** direct pushes to `main`, no branch/PR flow. Commit + push at the end of every milestone; update Notion and §8's log the same day. **Every code milestone ships with its tests** (unit test for the new method/action + the relevant fixture) and keeps CI green on Linux/Windows/macOS.

**Dependency graph:** M0 → M1, M2 (parallel) → M3 → {M4 Anant real-exec} → {M5 watcher, M6 correlation} depend on M4 + M3. Aradhya's M5/M6 need Datadog real (M4) and the k8s read-interface decision (M1) settled.

### Phase 0 — Contract + baseline (joint, no feature code)

| # | Owner | Milestone | Definition of done |
|---|---|---|---|
| **M0** | Anant + Aradhya | Sign off the interface (§4) + measure baselines (§3) + decide two owners | Both agree in writing (a note in §8 is enough) on: the `watch`/`get_stats` signatures, `ConnectorEvent`, the `alert`-as-Action model and default tier, **who owns the kubernetes.py conversion (M1b)**, and **who owns the combined correlation fixture (§7)**. The three baseline numbers in §3 are measured and filled in. |

### Phase 1 — Interface in place (unblocks Aradhya immediately)

| # | Owner | Milestone | Definition of done |
|---|---|---|---|
| **M1a** | Anant | Add `watch()`/`get_stats()` + `ConnectorEvent` + an `alert` Action skeleton to the base layers | `Connector` ABC has the two read methods (default `NotImplementedError`); `ConnectorEvent` type defined; a base/example `alert` Action stub exists. Existing behavior untouched; tests green. Gives Aradhya concrete types to build M3 against before any provider is real. |
| **M1b** | *decided at M0* | Convert `kubernetes.py` to the `Connector` class pattern (or ship a thin adapter) | k8s satisfies the same read interface as the other ten. Chosen approach (full convert vs adapter) recorded in §8. Existing k8s functions and `prash watch` still work. |

### Phase 2 — Prove the whole loop on ONE connector (Datadog)

| # | Owner | Milestone | Definition of done |
|---|---|---|---|
| **M2** | Anant | (parallel with M1) confirm Datadog auth/permission scopes for real `watch`/`get_stats`/`alert` | Documented in §8: which Datadog API scopes each of the three needs, and whether `datadog_alert` is APPROVAL or SAFE with reasoning. |
| **M3** | Aradhya | NLP integration against the M1a stubs | `prash/intent.py`'s tool schema + the diagnosis brain can route natural language to `watch()`/`get_stats()`/the alert Action (e.g. "keep an eye on this monitor" calls `watch()`), tested against the stubs — no wait on M4. |
| **M4** | Anant | Real Datadog execution | `watch`/`get_stats` hit the real Datadog API returning `ConnectorEvent`s; `datadog_alert` Action works and is permission-gated; `scripts/testing/break_datadog.py` produces an event Lear sees end-to-end. |
| **M5** | Aradhya | Refactor `watcher.py` onto the interface | `prash watch` polls via connector `watch()`/`get_stats()` instead of hardcoded k8s; works for both k8s and Datadog; old behavior preserved (§4e). |
| **M6** | Aradhya | Correlation v1 | Diagnosis brain merges `ConnectorEvent`s from Kubernetes + Datadog on one timeline. **Acceptance:** the combined fixture (§7) — a pod crash coinciding with a Datadog spike — yields **one** correlated hypothesis, not two separate alerts. §3 metrics re-measured and compared to baseline. |

### Phase 3 — Roll out to the rest (repeat M2→M4→M6 per connector)

Priority order, worst-covered surfaces first: **Grafana → PagerDuty → Kubernetes (upgrade to full watch/stats/alert) → GCP → AWS → Azure → GitHub → GitLab → Vercel → Snyk/Gitleaks → Terraform.** Each connector: Anant real-exec → Aradhya NLP + fold into correlation. Each gets its own §8 line when it lands — don't wait for the whole set.

## 7. Test fixtures (including the one that doesn't exist yet)

- **Single-connector fixtures — exist:** `scripts/testing/break_datadog.py`, `break_grafana.py`, `break_pagerduty.py`; `connectors/testdata/broken-pod.yaml` for k8s.
- **Combined correlation fixture — MUST be built for M6, owner decided at M0:** a harness that triggers a real pod crash (`broken-pod.yaml`) *and* a coinciding Datadog metric spike (`break_datadog.py`) inside the same time window, so `get_stats()` on both connectors returns overlapping `ConnectorEvent`s on one clock. Without this, M6's acceptance test can't run. This is net-new work, not an existing asset.

## 8. Milestone log

*(Add a line here every time a milestone in §6 ships — date, who, what actually shipped. Also the home for decisions: k8s convert-vs-adapter, per-provider alert tier, measured baselines.)*

| Date | Who | Item | Note |
|---|---|---|---|
| 2026-09-07 | G3 (Aradhya) | **GitLab rewrite shipped** — mirror of GitHub | `GitLabConnector.get_stats(project, since)` → pipelines as a `ConnectorEvent` timeline (dedup/mapping via single `status` field, vs GitHub's status+conclusion); `watch(project)` → `_GitLabWatchHandle` (dedup by pipeline id + status, folds into `run_watchhandle_loop`); `_request()` gained 429/Retry-After + `RateLimit-Reset` + transient-5xx backoff. `gitlab-open-issue` action (APPROVAL, reversible=True; GitLab uses `iid` + `state=="opened"`); `prash watch --provider gitlab` (targets via `--resource namespace/project,…` or `GITLAB_WATCH_PROJECTS`). 20 new tests (8 connector + 7 action + 5 watcher). **Live-verified 2026-09-07:** `get_stats` against real `drufiyai-group/prash-ci-test` returned 2 real pipelines with correct event-type mapping (read-only; `watch()` shares the same `list_pipelines()` call). **Not live-fired:** `gitlab-open-issue` creates a real issue → needs explicit human OK + a throwaway project first (same as `github-open-issue`). Suite 651 passed / 9 skipped. **CI/delivery surface now: GitHub + GitLab done; Dependabot read-only already existed. Remaining connectors: Vercel, Snyk, Gitleaks, Terraform, Azure.** |
| 2026-09-07 | G1+G2 (Aradhya) | **GitHub Actions rewrite shipped** — watch/get_stats/alert | **G1:** `GitHubConnector.get_stats(repo, since)` → workflow runs as a `ConnectorEvent` timeline (ci_failure/ci_success/ci_cancelled/ci_in_progress); `watch(repo)` → `_GitHubWatchHandle` (WatchHandle.poll() model, dedup by run-id + (status,conclusion), folds into `run_watchhandle_loop`); `_request()` gained 429/Retry-After + primary-limit (X-RateLimit-Reset) + transient-5xx backoff. **G2:** `github-open-issue` action (APPROVAL, reversible=True) — the CI escalation path (diagnosis → tracked issue) distinct from the open-pr fix flow; `prash watch --provider github` (targets via `--resource owner/repo,…` or `GITHUB_WATCH_REPOS`). **Live-verified:** `get_stats` against real `Drufiy/Lear-backend` returned 30 real runs with correct event-type mapping (read-only; `watch()` shares the same `workflow_runs()` call). **Not live-fired:** `github-open-issue` creates a real issue → needs explicit human OK + a throwaway repo before a live run. 20 new tests (8 connector + 7 action + 5 watcher). Suite 631 passed / 9 skipped. |
| 2026-09-07 | G0 (Aradhya) | GitHub Actions CI connector — API-scope audit + alert-tier decision (no code) | **Auth:** existing `GITHUB_TOKEN` (classic or fine-grained PAT), `Bearer` header, stdlib `urllib` — no new credentials. **watch()/get_stats():** both read `GET /repos/{repo}/actions/runs` (the existing `workflow_runs()` method; `_run_state()` already maps status/conclusion → `ConnectorState`). Scope: public repos need only a token; private repos need `actions:read` (fine-grained) or `repo` (classic). `get_stats(repo, since)` = recent runs as a `ConnectorEvent` timeline (event_type `ci_failure`/`ci_success`/`ci_in_progress`); `watch()` = `WatchHandle.poll()` model, dedup by run-id + conclusion (mirrors PagerDuty's id+status dedup), emitting an event only when a run newly completes as a failure. **alert() decision: `github-open-issue`, risk_tier=APPROVAL, reversible=True.** Rationale (matches long-term vision): the primary CI value is already the `open-pr`/`apply-ci-fix` fix→PR flow, so the alert slot is the *escalation* path — when Lear has a diagnosis but no safe auto-fix, it files an issue carrying that diagnosis as a durable, team-visible record (`POST /repos/{repo}/issues`, needs `issues:write` fine-grained or `repo` classic). Direct CI analog of `pagerduty-page`/`datadog-alert` (outbound + team-visible → APPROVAL); reversible=True because an issue can be closed, unlike a page. Rejected: *skip-like-k8s* (nothing external watches CI failures the way Datadog/PagerDuty watch k8s, so CI needs its own escalation artifact) and *rerun-workflow-as-alert* (`re_run_job()` already exists as a capability; re-running is remediation, not alert — belongs in the fix layer later, not the alert slot). **Code note for G1:** `_request()` has no rate-limit handling; a watch loop should honor 429 + `Retry-After`/`X-RateLimit-Reset` like the Datadog/PagerDuty connectors do. |
| 2026-09-04 | M2 | Datadog API scope audit (no OAuth scopes — raw key auth) | The connector uses `DD-API-KEY` + `DD-APPLICATION-KEY` headers, not OAuth apps, so "scopes" are app-key permission checkboxes. **watch():** app key with Monitor Read (`/v1/monitor/{id}?group_states=all`). **get_stats():** app key with Events Read + Monitor Read; API key covers nothing read. **alert():** API key only (Events API v2 intake, `POST /v2/events`); verify via `GET /v2/events/{id}` (app key, Events Read). **No new credentials required** beyond the existing `DATADOG_API_KEY`/`DATADOG_APP_KEY`. |
| 2026-09-04 | M2 | `datadog-alert` tier decision: **APPROVAL**, `reversible=False` | Outbound + team-visible: the whole point of the action is that the team sees the event, and Datadog's API has no event deletion, so it cannot be cleanly reversed — the spec's default for outbound alerts (same reasoning as `pagerduty-page`). Argued-for-SAFE counterpoint ("internal/mutable") rejected: visibility to the whole team is precisely what the approval prompt exists to surface, even though nothing is mutated beyond appending one event. |
| 2026-09-04 | M4 | Datadog `watch()`/`get_stats()`/`datadog-alert` shipped | `connectors/base.py`: `ConnectorEvent` TypedDict, `WatchHandle` ABC, `watch()`/`get_stats()` concrete defaults (M1a contract, landed early because Datadog M4 blocks on it). Connector: per-group `WatchHandle.poll()` diffing, Events API v2 timeline + metric-spike context in `get_stats()`, 429/5xx exponential backoff with `Retry-After` honored, 401 one-shot credential rotation re-read, per-endpoint timeouts (10s single-doc reads / 30s searches). Action: `datadog-alert` (APPROVAL). Watcher: `run_datadog_watch_loop` + `prash watch --provider datadog` (targets via `--resource` or `DATADOG_WATCH_MONITORS`). Brain: `monitoring` category + `mute_monitor` recommended_action, `format_datadog_context()`, eval case `monitoring_datadog_alert.json`. |
| 2026-09-04 | M4 | Decisions: connection pooling skipped; timeouts per-endpoint | Pooling: the repo's connectors are stdlib-`urllib` by convention (github.py/gitlab.py/vercel.py) and a poll cycle is 2–4 sequential calls — keep-alive machinery buys nothing measurable and adds connection-state risk to a watch loop. Revisit only if a poll cycle ever fans out. Timeouts: 30s was too generous for monitor checks and theoretically tight for big log searches → `SHORT_TIMEOUT=10` for single-document monitor/validate reads, `DEFAULT_TIMEOUT=30` kept for search endpoints. |
| 2026-09-04 | Phase 3 | PagerDuty full autonomous loop shipped | Same shape as the Datadog M4 line. `watch()`/`get_stats()` return `ConnectorEvent`s; dual auth preserved (REST token + `From` for reads/writes, routing key for Events v2); `page_oncall()` primitive (dedup-keyed Events v2 trigger) behind the new **APPROVAL**-tier `pagerduty-page` action — paging a human is irreversible and disruptive, same tier reasoning as `pagerduty-resolve`, logged here per the per-provider-tier rule. Watcher: `prash watch --provider pagerduty` (targets via `--resource` or `PAGERDUTY_WATCH_SERVICES`). Brain: PagerDuty events fold into the existing `monitoring` category with `acknowledge_incident` as the stopgap action; eval case `monitoring_pagerduty_incident.json`. Rate limit: 429 + `Retry-After` backoff honors the 900 req/min account limit; REST v2 lists paginate by limit/offset + `more` flag (not cursor-based, contrary to the sprint brief) under a hard cap. `prash investigate` now renders the `get_stats()` timeline for any connector that implements it (datadog + pagerduty). |
| 2026-09-06 | Aradhya (agent-assisted) | **M0 baselines measured** (§3) | All three §3 baselines measured live on `kind-prash-dev`/`prash-demo`, before any Aradhya rewrite code (M3+): cold-start diagnosis **8.09 s median** (n=5); single-source false-positive **0/3** on the known k8s fixtures (unambiguous cases — the correlation gain is tested on the harder M6 fixture); per-connector k8s read `poll_state`~4 ms / `get_stats`~3 ms. **Finding:** the full N-connector sequential-vs-parallel latency baseline is unmeasurable on this machine (only k8s is live), so that comparison is deferred to M6 with the combined fixture — logged here per §3 rather than guessed. |
| 2026-09-06 | Aradhya (agent-assisted) | **M1a hardening** — main was shipped red by PR #33 | PR #33 merged with the suite unable to collect: `base.py` `from datetime import datetime` shadowed the module (crashed the `ConnectorEvent` TypedDict annotation) + a stray duplicate `@dataclass ConnectorEvent`; `watcher.py` `run_terraform_watch_loop` had an empty `if` (IndentationError). Both hotfixed (`b605c47`), suite green (462→now 464 with new tests). The `ConnectorEvent` shape is settled as the **TypedDict** (§4c) — the dead dataclass is removed. |
| 2026-09-06 | Aradhya (agent-assisted) | **M1b bug fix + first tests for the new k8s surface** | `KubernetesConnector.get_stats` sorted by `x.timestamp` (attribute) on a TypedDict → `AttributeError` at runtime; only survived because PR #32 shipped the class's `get_stats`/`watch` with **zero tests**. Fixed to `x["timestamp"]` and added the first two regression tests pinning the `ConnectorEvent`-dict contract + `since` filtering. |
| 2026-09-06 | Aradhya | **M1b ownership (retroactive)** | k8s conversion was done by Agrim (PR #32, full convert not adapter) and merged 2026-09-04; recording the convert-vs-adapter decision here as the spec asks: **full convert**, backward-compat module wrappers retained. |
| 2026-09-07 | Aradhya (agent-assisted) | **Watcher cleanup** — Datadog/PagerDuty loops folded into a shared WatchHandle loop | Aryan's M4 added `run_datadog_watch_loop`/`run_pagerduty_watch_loop` as two standalone ~90/~67-line functions — the copy-paste-per-connector pattern M5 eliminated for the `poll_state`/`get_stats` family, back for the `WatchHandle.poll()` family. New `run_watchhandle_loop(handles, notify_fn, …)` is the one home for that model (dedup lives inside the connector's handle, e.g. PagerDuty's escalation tracking — genuinely different from `run_connector_watch_loop`'s loop-side dedup, so folding into *that* would have silently dropped it). Both loops are now thin wrappers: provider-specific handle-building kept separate (needs provider-specific error types), only the poll/notify/sleep body is shared. Suite: 611 passed, 9 skipped. |
| 2026-09-07 | Aradhya (agent-assisted) | **Kubernetes `watch()` test coverage closed** (Notion Tier 2) | `get_stats()` got its first tests in an earlier session (along with a real bug fix — sorting a TypedDict by attribute); `watch()` was the other half of the "Kubernetes Rewrite shipped with zero tests for the new class surface" gap, still untested. 7 new tests mock `kubernetes.watch.Watch().stream()` the same way the existing suite mocks the plain client: correct `ConnectorEvent` for CrashLoopBackOff/ImagePullBackOff/OOMKilled, healthy-pod updates correctly ignored, named-pod vs namespace-wide field-selector scoping, and authenticate-if-not-connected. Suite: 611 passed, 9 skipped. |
| 2026-09-07 | Aradhya (agent-assisted) | **§3 quantitative correlation metric — first real measurement, inconclusive result, honestly reported** | New `scripts/testing/measure_correlation_accuracy.py`: 2 purpose-built ambiguous scenarios (DB connection-pool saturation misread as network failure; a degraded downstream dependency misread as an app-side problem), each pushed through 2 real `diagnose_failure()` calls (single-source k8s context vs. k8s+correlated-Datadog context), graded against a known true cause. Deliberately used constructed-but-realistic evidence (same `PodStatus`/`ConnectorEvent` shapes real connectors produce) rather than a live cluster — this measures the brain's reasoning, not the read path, which is already covered elsewhere. **Result: 0/2 wrong single-source AND 0/2 wrong multi-source — no false-positive gap on this set.** Not a bug, not massaged: the brain's system prompt is conservative enough to answer `recommended_action: None` on ambiguous single-source evidence rather than confidently guessing wrong (e.g. never recommended `restart_pod` in either scenario) — the metric's "% wrong actions" framing assumes single-source produces confidently-wrong answers, but this brain's actual single-source failure mode is "correctly uncertain," which the metric doesn't credit. **Real signal that did show up:** confidence rose 0.65→0.85 on the harder scenario when the correlated signal was added. **Left as an open, not a closed, question** (not deciding alone): either redefine the metric around confidence/specificity delta instead of binary correctness, or build harder scenarios where staying silent is itself the wrong call. |
| 2026-09-07 | Aradhya (agent-assisted) | **M6 re-verified against real Datadog** — mixed result, one real product finding | Aryan's M4 (`647f3fa`) landed real Datadog `get_stats()` overnight. Re-ran `break_combined.py` with **both legs live** (no stubs): forced the real `prash-test-synthetic-error-rate` monitor into Alert, confirmed via `prash investigate` (state=failed) and a direct `get_stats()` call (real `metric_spike` event, real API). Combined with the live `broken-app` k8s crash-loop: **11 events across 2 real connectors correlated into ONE incident** — M6 acceptance genuinely met live, not stubbed. **Finding — window size:** the default 120s window (§ correlation.py `DEFAULT_WINDOW_SECONDS`) was too tight to catch this real pairing. Datadog's `get_stats()` doesn't emit a discrete alert-transition event for this monitor (`_monitor_events()`/Events API v2 returned 0 both times) — the only event it returns is the `_metric_spike_event()` context event, whose timestamp reflects when the metric *actually peaked* in Datadog's own timeseries (found to lag ~12-15 min behind the triggering call in practice), not call time. Needed `--window 900` (15 min) to merge. **Not deciding unilaterally** whether to change the global default — flagging as a real tuning question for whoever owns default window selection; a tight window trades false-merges for missed-real-correlations, and 120s clearly missed a genuine live one here. **Still open, unchanged from before:** the quantitative §3 single-vs-2-source false-positive number is *still* not measurable — this pairing's two legs are semantically unrelated incidents (a config-missing crash vs. an unrelated synthetic metric), so there's no "single source gets it wrong, two sources get it right" scenario to measure against. That requires a new purpose-built fixture, not just live credentials. `break_combined.py` updated to use real `DatadogConnector.get_stats()` by default (`--offline` still available for canned/no-creds runs). Datadog fixture healed back to OK after testing. Suite unaffected (correlation.py untouched): 8/8 correlation tests, 604 passed / 9 skipped overall. |
| 2026-09-06 | Aradhya (agent-assisted) | **M6 shipped** — correlation v1 + combined fixture | New `prash/brain/correlation.py`: `correlate(events, window_seconds)` merges `ConnectorEvent`s from any number of connectors onto one timeline and clusters coinciding ones into `CorrelatedIncident`s; `format_incident_context()` renders a multi-source incident as ONE unified-timeline block for the brain (mirrors the `format_*_context` style). **Acceptance met** (deterministic, 8 tests): a pod crash + a coinciding Datadog spike → **one** multi-source incident, not two; far-apart events stay separate; naive/aware timestamps join cleanly. Combined fixture `scripts/testing/break_combined.py` (§7, net-new): real k8s `get_stats` leg + **stubbed** Datadog spike leg (M4 not landed) → verified end-to-end producing one kubernetes+datadog incident (`--offline` demonstrates it with no cluster). **Honest scope:** the correlation *logic* and the brain-ready unified context are proven now; the quantitative single-source-vs-2-source false-positive comparison (§3) needs the live Datadog leg + an LLM diagnosis pass over a genuinely ambiguous incident — **gated on Aryan's M4**, not measurable today. Suite 497 passed / 9 skipped. |
| 2026-09-06 | Aradhya (agent-assisted) | **M5 shipped** — watcher on the interface, multi-connector + parallel | `watcher.py` had 4 separate loops (k8s pod-problem, terraform drift, and a copy-pasted AWS/GCP pair). New `run_connector_watch_loop(watches, …)` is the one interface-driven loop: drives `poll_state()`+`get_stats()` on *any* connector, reads every watch in a cycle **in parallel** (ThreadPoolExecutor — the §3 sequential→parallel speed lever), unified dedup + notify. AWS/GCP are now thin wrappers over it (≈100 lines of duplication gone); `prash watch --provider aws,gcp --resource i-1,vm-2` runs them together. k8s (`run_watch_loop`/`detect_changes`) and terraform stay specialized — their models aren't get_stats time-series, and §4e forbids regressing them; both still work unchanged. 6 new tests (dedup, parallel fan-out, flaky-connector resilience, NotImplementedError skip). Suite 489 passed / 9 skipped. Note: default single-provider `prash watch` behavior preserved exactly. |
| 2026-09-06 | Aradhya (agent-assisted) | **M3 shipped** — NLP reaches watch()/get_stats()/alert | Natural language now routes to all three new capabilities. New `prash stats <resource>` command is the user-facing surface for `get_stats()` (event timeline; distinct from `investigate`/`poll_state` point-in-time). `intent.py` fast path: "what's been happening / recent events / timeline" → `stats` (guarded so an explicit action verb like "diagnose" still wins); "keep an eye on X" → `watch` scoped to the target's namespace. LLM slow path: `stats` added to the command enum, `watch` enriched to carry `--provider/--resource` (non-k8s) or `--namespace` (k8s), and the schema/system-prompt now say paging/alerting = `run <*-alert>` (aws-alert/gcp-alert are registered). Built against the M1a stubs + real k8s — no wait on Datadog (M4). Interpretation note: "extend the diagnosis brain's system prompt" = the intent resolver's brain (schema+prompt), which is the NLP surface; `diagnosis_agent.py`'s failure-diagnosis tool is untouched (watch/stats/alert are reads/pages, not fixes). 13 new intent tests; live-verified `stats` against kind-prash-dev before Docker dropped. Suite: 483 passed, 9 skipped. |

## 9. Open questions for Anant (resolve at M0)

1. Does the `ConnectorEvent` shape (§4c) hold across all providers, or does any need extra fields?
2. Per provider that can alert: is its alert genuinely reversible/internal (arguably SAFE) or outbound/irreversible (APPROVAL, the default)?
3. Given scope is "interface + Datadog real" (M1–M4) before all ten, what's the timeline estimate?
4. kubernetes.py: full convert to the `Connector` class, or thin adapter? (M1b — affects your connector work and Aradhya's watcher refactor.)
