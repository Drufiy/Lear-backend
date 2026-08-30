# Lear — Testing Setup Runbook

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

**Status: ready.**

`scripts/testing/break_grafana.py` manages one alert rule end to end,
`Prash E2E Test Alert` (uid `afw5nq4yyq0owb`, rule group `prash-e2e-test`)
— its condition is a pure math expression (`1 > 0` / `1 > 2`), no external
datasource involved, so there's nothing real to accidentally touch.

```bash
python3 scripts/testing/break_grafana.py          # force Alert
python3 scripts/testing/break_grafana.py --heal   # force OK
```

Unlike Datadog, there's no separate "submit a metric point" step — toggling
the rule's own query takes effect on Grafana's next evaluation cycle
(seconds, confirmed live 2026-08-26 in both directions).

Note: this instance is on Grafana Cloud's free tier, which hibernates when
idle — a `503 "instance is loading"` on first touch after idle time is
expected, not a bug; it clears within ~1 min of the instance waking up.

**Prash prompt to test with:**

```
what's wrong with Prash E2E Test Alert
```

(answer `grafana` if it asks which connector). To test `grafana-silence-alert`:

```
silence Prash E2E Test Alert for 30 minutes
```

Worth noting: silencing a firing Grafana alert changes its Alertmanager
state to `suppressed`, which `poll_state()` maps to `degraded` — so testing
the silence action also naturally exercises the DEGRADED state, unlike
Datadog where muting doesn't change `overall_state`.

## PagerDuty

**Status: ready.**

`scripts/testing/break_pagerduty.py` fires a real event at the `prash-v2`
service via the Events API v2, using a fixed `dedup_key` so repeated runs
update the same incident instead of piling up new ones.

```bash
python3 scripts/testing/break_pagerduty.py          # trigger (open incident)
python3 scripts/testing/break_pagerduty.py --heal   # resolve it
```

Both directions live-verified 2026-08-26 — trigger produces a real
`triggered` incident within seconds, resolve clears it within seconds.

**Prash prompt to test with:**

```
what's wrong with prash-v2
```

(answer `pagerduty` if it asks which connector — note the resource is the
*service* name, not the dedup key). To test the write actions, once
there's an open incident:

```
acknowledge the prash-v2 incident
```

or `resolve the prash-v2 incident` — you'll need the incident's real id
from the investigate output first, since `poll_state()`'s detail is what
surfaces it (same pattern as a pod vs. its Deployment for k8s rollback).

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

**Status: fixture added and unit-tested (`break_aws.py` + `poll_state()`
service-level health), still needs a live run against a real EC2 instance
to be marked proven. Live run is blocked on AWS credentials (see below).**

`scripts/testing/break_aws.py` owns one EC2 instance end to end — a real
instance tagged `Name=prash-test-fixture` (or the id you pass via
`EC2_INSTANCE_ID` / `--instance-id`). It forces a real failure state on
demand: it installs a fake `prash-test-fixture.service` systemd unit whose
ExecStart is a background loop — the unit reports `active (running)` while
the simulated app is genuinely wedged. The loop writes a watchdog line to
BOTH journald and `/tmp/prash-test-fixture-watchdog.log` (the on-disk file
is what `execute-aws tail` reads). `--heal` removes the unit, the marker,
and the loop, restoring the instance.

```bash
python3 scripts/testing/break_aws.py                 # force failure state
python3 scripts/testing/break_aws.py --heal          # restore the instance
```

The script requires credentials from `.env` (`AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`, `AWS_REGION`) and a running instance. It tries the
SSM path first; if the SSM agent is absent it exercises the exact
`execute-aws` SSH-fallback path via `--pem <path>`.

**Service-level health:** `poll_state()` now goes one step past instance
status checks — when a running instance has OK checks, it asks the box
itself (via SSM, or SSH if a `pem_path` is passed) whether the fixture's
break marker `/tmp/prash-test-fixture-break` exists. Present → `DEGRADED`
with `detail["marker"]` set. This is what makes `prash investigate` report
degraded after `break_aws.py` runs, instead of a misleading `healthy`.
SSM/SSH failures are swallowed (never fabricate a state we couldn't
verify).

**`fetch_logs()` reads EC2 console output** (`get_console_output`) — the
hypervisor serial console, which only captures boot messages, NOT the
watchdog file. The ONLY way to read the watchdog log is `execute-aws`
(SSM/SSH), which is what the test command below does.

**Prash prompt to test with** (after running the break script):

```
what's wrong with prash-test-fixture
```

or the exact command form:

```
prash investigate prash-test-fixture --provider aws
```

To test `execute-aws` itself (needs `--noninteractive` and the SSM agent or
a `--pem`):

```
prash run execute-aws prash-test-fixture --command "tail -n 20 /tmp/prash-test-fixture-watchdog.log" --noninteractive
```

**Live-verify script:** `scripts/verify_aws_live.py` is the "cold verify"
script — it authenticates, locates/polls/logs a real instance, asks an LLM
for a lightweight command, and runs it through the connector (SSM with SSH
fallback). The pem path is no longer hardcoded: pass `--pem <path>` or set
`PRASH_PEM_PATH` (it errors cleanly instead of prompting interactively).

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

**Status: live-verified against a real binary and a real leak (2026-08-30).**

The `gitleaks` binary is installed on this machine via winget (Gitleaks
8.30.1 — no Homebrew on Windows; `winget install Gitleaks.Gitleaks` puts
`gitleaks.exe` under
`%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gitleaks.Gitleaks_Microsoft.Winget.Source_8wekyb3d8bbwe\`,
with a `gitleaks` PATH alias in new shells).

**Live verification performed** against a real git repo fixture containing
actual committed secrets (random high-entropy `glpat_*` GitLab-style token +
`AKIA*` AWS-style key, both committed to history so a history scan finds
them):

- `authenticate()` → `True` (real binary found)
- `locate()` → correctly reports the fixture as a git repo
- `poll_state()` on the leaky repo → `FAILED`, `leak_count: 2`, findings
  scrubbed (only `rule_id` / `file` / `line` / `fingerprint` — the raw
  `Match`/`Secret` text is stripped, confirmed the secret value never
  appears in connector or `prash investigate` output)
- `fetch_logs()` → 2 real lines (`generic-api-key in config.py:1` etc.)
- `poll_state()` on a clean working tree (`no_git=True`) → `HEALTHY`
- Full CLI path: `prash investigate <path> --provider gitleaks` → `failed`
  with the scrubbed findings

Two fixture gotchas worth recording: gitleaks' default rules deliberately
skip the AWS documentation example key (`AKIAIOSFODNN7EXAMPLE` — contains
the `example` stopword) and any token containing the literal
`abcdefghijklmnopqrstuvwxyz` substring (global allowlist stopword). A
realistic live fixture needs genuinely random high-entropy secrets, not
docs-style examples.

Unit tests (`tests/test_gitleaks_connector.py`, 12) still mock the binary;
the live run above proves the connector's subprocess/report-parsing path
works against the real thing.

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
- **Repeated-identical-failure handling: wired up (2026-08-30), opt-in.**
  `compute_error_signature()` exists and is correct, and
  `diagnose_failure(..., repeated_failure=True)` correctly forces a
  different-hypothesis directive when set. **The gap that made it dead code
  was real: nothing in the actual retry path called either.** `prash/fix.py`
  and `prash/brain/multi_diagnosis.py` (the two real callers) never
  computed a signature or passed `repeated_failure=True`, and — the deeper
  issue — there was no retry loop at all: `cmd_fix --ci` was one-shot
  (diagnose → apply → exit), so a wrong hypothesis was never revisited. A
  stale comment referenced a `push_handler.py` retry flow that doesn't
  exist in this repo (leftover from the `drufiy-backend` port). **Fixed by
  adding the reconcile loop back:** `prash fix <owner>/<repo> --ci
  --run-id <n> --reconcile` now applies the fix, waits for the fix branch's
  CI run, compares `compute_error_signature()` between the original and fix
  branch runs, and re-diagnoses with `repeated_failure=True` when the
  signature is identical (forcing a different hypothesis) or normally when
  it changed. Bounded by `PRASH_CI_RECONCILE_MAX_ITERATIONS` (default 2),
  stops the moment a run passes, and never silently drops a partial fix —
  the already-open PR stays open for a human if the budget is exhausted.
  Default behavior is unchanged (one-shot) unless `--reconcile` is passed.
