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
| Cold-start diagnosis wall-time | Time from `prash fix` to first proposed hypothesis on the standard fixture, median of 5 runs | _TBD_ | Meaningfully lower with `watch()` warm vs cold (set exact % at M0 once baseline is known) |
| Single-source false-positive rate | On a fixture set with a known root cause, % of runs whose top hypothesis is wrong when diagnosing off one connector only | _TBD_ | Lower with 2-source correlation than single-source, on the same set |
| Parallel vs sequential read latency | Wall-time to gather state from N connectors in one pass | _TBD_ (sequential) | Approaches slowest-single-connector time, not the sum |

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
| | | | |

## 9. Open questions for Anant (resolve at M0)

1. Does the `ConnectorEvent` shape (§4c) hold across all providers, or does any need extra fields?
2. Per provider that can alert: is its alert genuinely reversible/internal (arguably SAFE) or outbound/irreversible (APPROVAL, the default)?
3. Given scope is "interface + Datadog real" (M1–M4) before all ten, what's the timeline estimate?
4. kubernetes.py: full convert to the `Connector` class, or thin adapter? (M1b — affects your connector work and Aradhya's watcher refactor.)
