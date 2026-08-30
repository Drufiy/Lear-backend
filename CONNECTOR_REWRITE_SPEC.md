# Connector Rewrite — System Spec

**Status:** Approved plan, work not yet started. Single source of truth for this initiative — same discipline as `PRASH_V2.md`: update this file and Notion after every milestone, no exceptions.
**Owners:** Anant (connector execution) · Aradhya (NLP/diagnosis-brain side + test environment)
**Supersedes:** the draft version of this file (interface-first idea only, no milestones, no vision section)
**Related Notion tasks:** [Rewrite every connector](https://app.notion.com/p/3ca7710d2e9381c18da5f3fa993f2c11) (Anant) · [Extend the diagnosis brain via NLP](https://app.notion.com/p/3ca7710d2e9381baa1bccf810437ca77) (Aradhya)

---

## 0. Standing rule for this doc (same as `PRASH_V2.md`)

> This file gets updated after every milestone. Mark it done with the date and what actually shipped, not what was planned. If a decision changes, add a new dated line — don't silently edit old ones away. If it isn't in this file or Notion, it didn't happen for anyone else on the team.

**Note for Aradhya's Claude Code sessions only:** always wait for Aradhya's explicit go-ahead before writing any code for his milestones in this plan. This does **not** apply to Anant — he works independently and isn't gated by this.

---

## 1. Why this exists

Two Tier 1 Notion tasks are currently stuck in a chicken-and-egg loop:

- Anant's ["Rewrite every connector"](https://app.notion.com/p/3ca7710d2e9381c18da5f3fa993f2c11) — still "To Do."
- Aradhya's ["Extend the diagnosis brain via NLP"](https://app.notion.com/p/3ca7710d2e9381baa1bccf810437ca77) — blocked on the above, since there's nothing new to build against.

This doc breaks that loop with an interface-first approach (§3–4) and a concrete milestone plan (§5) so both sides can move in parallel instead of one waiting on the other to fully finish.

## 2. The bigger goal — this isn't just a connector cleanup

Per Aradhya, 2026-08-30: *"by better tech I mean everything — already the USPs we have and we would like to have faster diagnosis, better accuracy, multi-connector correlation etc."*

This rewrite is the foundation for three concrete technical gains, on top of Lear's existing USPs (local-first, credentials never leave the user's machine, human-approval-gated actions):

| Goal | What actually changes | Where it lives |
|---|---|---|
| **Faster diagnosis** | Connectors expose `watch()` so Lear can hold context proactively instead of cold-starting every diagnosis pass by querying from scratch. Multi-connector queries during a diagnosis pass run in parallel, not sequentially. | Diagnosis brain (`prash/brain/diagnosis_agent.py`), connector query layer |
| **Better accuracy** | Before proposing a fix, cross-check against at least 2 independent data sources when more than one connector is available, instead of diagnosing off a single log stream. Reduces false-positive fixes. | Diagnosis brain, new correlation module (§5, M4) |
| **Multi-connector correlation** | A pod crash + a Datadog metric spike + a recent GitHub deploy can be recognized as *one* incident with one root cause, not three unrelated alerts. Requires every connector to emit data in the same shape (§3) so events from different providers can sit on one shared timeline. | New correlation module (§5, M4), built on the shared `ConnectorEvent` shape below |

This is the actual competitive bet: none of the "weakest surface" connectors (Datadog/Grafana/PagerDuty-tier monitoring, per the original 2026-08-28 finding) currently support any of this. Getting there first, with actual execution and not just read-only investigation, is the differentiation from competitors who stop at "read logs, suggest a fix."

## 3. Interface contract (agree before building — not final until Anant signs off)

Every connector in `prash/connectors/` exposes three methods, converging on one shape so the diagnosis brain reasons about one pattern, not ten bespoke ones:

```python
def watch(self, target: str) -> WatchHandle:
    """Start monitoring `target` (e.g. a Datadog monitor, a GCP resource, a k8s deployment)."""

def get_stats(self, target: str, since: datetime | None = None) -> list["ConnectorEvent"]:
    """Return real events/state for `target`, optionally since a given time."""

def alert(self, target: str, message: str) -> None:
    """Push a real alert through this provider (e.g. a Datadog event, a PagerDuty page)."""
```

All three return (or accept) `ConnectorEvent` — a shape every connector must speak, specifically so events from different providers can be merged on one timeline for correlation (§2, §5 M4):

```python
class ConnectorEvent(TypedDict):
    timestamp: datetime   # UTC, required — this is what correlation sorts and joins on
    connector: str         # e.g. "datadog", "kubernetes", "github"
    event_type: str         # e.g. "metric_spike", "pod_crash", "deploy", "ci_failure"
    summary: str              # one human-readable line, this is what the diagnosis brain reads first
    raw: dict                  # untouched provider-specific payload, kept for drill-down
```

**Open question for Anant (§7):** does this shape hold up across all 10 providers, or does auth/permission handling differ enough that some providers need a different shape?

## 4. Precedent already in this codebase

This isn't a new pattern — `prash/connectors/kubernetes.py` was already built this way: real function signatures, `NotImplementedError` bodies, so another track could build against the shape before the real driver landed. Same move here, just applied to all 10 connectors instead of one.

Other pointers Anant needs before starting:
- `prash/connectors/*.py` — current per-provider connectors (`datadog.py`, `grafana.py`, `pagerduty.py`, `aws.py`, `gcp.py`, `azure.py`, `vercel.py`, `github.py`, `gitlab.py`, `snyk.py`, `gitleaks.py`). Most are read + one narrow action today; this is what's being extended.
- `prash/intent.py` — the tool schema Aradhya extends so watch/stats/alert become reachable through natural language, not just exact `run <action>` commands.
- `prash/brain/diagnosis_agent.py` — where "drive connectors via NLP" and the new correlation module both live.
- `scripts/testing/break_datadog.py` — the existing real break-fixture; the reason Datadog is the first connector made real (§5).
- **Terraform is explicitly out of scope for this initiative.** It doesn't exist as a real connector in the codebase at all (verified 2026-08-30 — zero references in `prash/`, despite Notion showing "Connect Terraform" as Done). Already flagged and put on hold separately; don't fold it into this plan.

## 5. Milestone plan

**Team convention (logged 2026-08-09):** direct pushes to `main`, no branch/PR flow. Commit and push at the end of every milestone below, and update Notion + this file's §6 log the same day.

### Phase 0 — Contract (joint, no code)

| # | Owner | Milestone | Definition of done |
|---|---|---|---|
| M0 | Anant + Aradhya | Agree on the interface contract (§3) | Both sign off in writing (a note in §6 below is enough) on the method signatures and the `ConnectorEvent` shape, or an agreed change to them |

### Phase 1 — Prove the loop on one connector (Datadog)

| # | Owner | Milestone | Definition of done |
|---|---|---|---|
| M1 | Anant | Stub the new interface across all 10 connectors | Every connector file has `watch`/`get_stats`/`alert` signatures with `NotImplementedError` bodies; existing functionality (current read/narrow-action behavior) untouched and still passing tests |
| M2 | Anant | Real execution for Datadog | `watch`/`get_stats`/`alert` work against the real Datadog API, returning `ConnectorEvent`-shaped data; `scripts/testing/break_datadog.py` triggers a real event Lear can see end-to-end |
| M3 | Aradhya | NLP integration for Datadog | `prash/intent.py`'s tool schema + the diagnosis brain can drive Datadog's new capabilities through natural language in Chat (e.g. "keep an eye on this monitor" actually calls `watch()`) — not a canned command |
| M4 | Aradhya | Correlation v1 | Diagnosis brain pulls `ConnectorEvent`s from 2 connectors (Kubernetes + Datadog — the two with real depth after M2) and merges them on one timeline for a single diagnosis pass. Test scenario: a pod crash + a coinciding Datadog metric spike produce **one** correlated hypothesis, not two separate alerts |

### Phase 2 — Roll out to the rest (same pattern, repeated)

For every remaining connector: **(Anant) real execution → (Aradhya) NLP integration + fold into correlation.** Priority order, worst-covered surfaces first (per the original 2026-08-28 finding that small-team ICP users hit these before Lear's stronger surfaces):

1. Grafana
2. PagerDuty
3. Kubernetes (upgrade existing partial actions to full watch/stats/alert)
4. GCP
5. AWS
6. Azure
7. GitHub
8. GitLab
9. Vercel
10. Snyk / Gitleaks

Each connector gets its own two-line entry in §6 when it lands — don't wait until all 10 are done to log progress.

## 6. Milestone log

*(Add a line here every time a milestone in §5 ships — date, who, what actually shipped.)*

| Date | Who | Milestone | Note |
|---|---|---|---|
| | | | |

## 7. Open questions for Anant

1. Does the `ConnectorEvent` shape (§3) hold up across all 10 providers, or does auth/permission handling need a different shape for some?
2. Given the scope is now "stub everything + Datadog for real" (M1–M2) instead of "all 10 for real" up front, does that change your timeline estimate?
