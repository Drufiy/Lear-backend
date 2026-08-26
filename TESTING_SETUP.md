# Prash v2 — Testing Setup Runbook

Shareable checklist of what's configured per connector, how to force it into
a failure state on demand, and how to heal it back. Companion to
`PRASH_V2.md` (which is the dev log of what happened) — this is the
"how do I reproduce it myself" reference. Everything here uses real
infrastructure this project owns, not mocks.

Convention: each connector gets a `scripts/testing/break_<connector>.py`
(or equivalent) that is idempotent and safe to re-run. Running it prints the
exact `prash` command to check state afterward.

---

## Datadog

**Status: ready.**

`scripts/testing/break_datadog.py` owns one monitor end to end:
`prash-test-synthetic-error-rate`, alerting on a synthetic custom metric
(`prash.test.synthetic_error_rate`) this script exclusively writes to — no
real service/host is touched.

```bash
python3 scripts/testing/break_datadog.py          # force Alert
python3 scripts/testing/break_datadog.py --heal   # settle back to OK
```

After running (no `--heal`), the monitor takes ~1-5 min to evaluate into
`Alert` (Datadog's own evaluation window, `avg(last_5m)`). Confirmed live
2026-08-26: monitor id `316853860` reached real `Alert` state ~2 min after
submission.

**Update 2026-08-26**: testing this fixture found and fixed the most
serious bug in the project so far — any action needing approval (the
default posture) hung Chat forever with zero output. See PRASH_V2.md §10,
2026-08-26. Fixed; the mute flow below is now live-verified working.

**Prash prompt to test with**, once you've run the break script and waited
a couple minutes:

```
what's wrong with prash-test-synthetic-error-rate
```

or the exact command form:

```
prash investigate prash-test-synthetic-error-rate --provider datadog
```

To test `datadog-mute-monitor`, once it's in Alert:

```
mute prash-test-synthetic-error-rate for 30 minutes
```

---

## Grafana

**Status: not yet set up.**

Credentials present (`GRAFANA_API_KEY`, `GRAFANA_URL`). Note from earlier
sessions: this instance is on Grafana Cloud's free tier, which hibernates
when idle — a `503 "instance is loading"` on first touch after idle time is
expected, not a bug; it clears within ~1 min of the instance waking up.
Needs: one alert rule this script can flip via a synthetic query, same
pattern as Datadog above.

## PagerDuty

**Status: not yet set up.**

Credentials present (`PAGERDUTY_API_KEY`, `PAGERDUTY_FROM_EMAIL`,
`PAGERDUTY_ROUTING_KEY`). Needs: a test service + a script that fires a
real event via the Events API v2 (`trigger_event()` already exists in
`prash/connectors/pagerduty.py`) to create a real open incident on demand.

## Snyk

**Status: not yet set up.**

Credentials present (`SNYK_API_TOKEN`, `SNYK_ORG_ID`). Needs: a test
project with a real known-vulnerable dependency, so `poll_state()` reports
a genuine `critical`/`high` finding and `snyk-ignore-issue` has something
real to act on.

## Vercel

**Status: proven working (sprint 1), no standing fixture script yet.**

Real redeploy/rollback already live-verified against a real project in the
2026-08-24 E2E sprint. Not yet turned into a reusable
`scripts/testing/break_vercel.py` — the project id/deployment history used
then may no longer be current; needs a quick re-check before reuse.

## GitHub / GitLab

**Status: proven working (multiple sessions), fixtures are the live repos
already in use** (`Drufiy/prashv2backend` for GitHub,
`drufiyai-group/prash-ci-test` for GitLab). A broken CI run needs to be
pushed to trigger a fresh failure — no standing "always broken" branch
exists yet; consider adding one (a workflow that always fails on a
dedicated branch) so this doesn't need a fresh push each time.

## AWS

**Status: credentials present, never live-tested this connector.**

No fixture exists. Needs a real EC2 instance or equivalent the
`execute-aws` SSH-fallback path can target, plus a way to force a real
failure state.

## Azure / GCP

**Status: GCP has credentials (`GCP_PROJECT_ID`, `GCP_REGION`,
`GOOGLE_APPLICATION_CREDENTIALS`) but never live-tested. Azure has no
credentials configured at all** — `.env` has zero `AZURE_*` keys. Setting
up Azure needs an account/subscription, which is Aradhya's to create (not
something I can do on your behalf).

## Kubernetes

**Status: ready, proven, reusable.** `kind` cluster `prash-dev`,
`prash/connectors/testdata/*.yaml` fixtures (`broken-app` CrashLoopBackOff,
`oom-app` OOMKilled, `configmap-app` StuckPending, `silent-crash-pod`).
Already fully verified end to end in sprint 1.

## Gitleaks

**Status: connector logic unit-tested only. The `gitleaks` binary is not
installed on this machine** — `authenticate()` correctly reports that, but
there's no way to live-test a real scan until it's installed
(`brew install gitleaks`).

## Terraform

**Status: pending.** Anant says his connector is done, pushing tonight.
Fixture setup (a real `.tf` plan with an intentional break) to follow once
the connector lands and its shape is known.

---

## Known non-connector gap, found auditing the diagnosis brain (2026-08-26)

The June 2026 backend audit identified two systematic diagnosis weaknesses
(masked exceptions, repeated-identical-failure). Re-checked against the
current `prash/brain/diagnosis_agent.py` (this code was ported from
`drufiy-backend` into this repo):

- **Masked-exception handling: real and wired up.**
  `_detect_masked_exception_risk()` flags a log where the failing evidence
  is a downstream status assertion with no revealing exception visible;
  `diagnose_failure()` then directs the model to fetch the producing
  function's source and reason about swallowed exceptions. Working as
  designed.
- **Confidence calibration: real and wired up.**
  `_recalibrate_confidence()` caps a model's self-reported confidence at
  `verified_rate + 0.2` based on real outcome history, plus a hard
  downgrade path for low-confidence `safe_auto_apply`/`review_recommended`
  fixes.
- **Repeated-identical-failure handling: built, but dead code.**
  `compute_error_signature()` exists and is correct, and
  `diagnose_failure(..., repeated_failure=True)` correctly forces a
  different-hypothesis directive when set — but **nothing in the actual
  retry path ever calls `compute_error_signature()` or passes
  `repeated_failure=True`.** Neither `prash/fix.py` nor
  `prash/brain/multi_diagnosis.py` (the two real callers) wire it in. A
  stale comment references a `push_handler.py` retry flow that doesn't
  exist in this repo (leftover from the `drufiy-backend` port). Net
  effect: today, a second/third diagnosis attempt with the exact same
  wrong root cause will retry the same hypothesis indefinitely instead of
  being forced to reconsider — the original June bug is still live in
  practice, just hidden behind unused-but-correct machinery.
