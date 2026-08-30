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

**Status: fixture script added + fixture repo live (2026-08-30); full
live run blocked — no Snyk credentials on this machine.**

`scripts/testing/break_snyk.py` owns a Snyk test project end to end, the
same way `break_datadog.py` owns its monitor. The resource is the git repo
**`ALavent/prash-snyk-fixture`** (created live 2026-08-30 via the ALavent
token; verified containing the vulnerable manifest), whose `package.json`
toggles a **real known-vulnerable dependency**:

- **break** → `lodash@4.17.20` (CVE-2021-23337, prototype pollution, high
  severity) pushed to the fixture repo → Snyk scan reports critical/high →
  `poll_state()` reports `FAILED`
- **`--heal`** → `lodash@4.17.21` (patched) pushed → next scan clean →
  `poll_state()` reports `HEALTHY`

```bash
python3 scripts/testing/break_snyk.py [--repo <owner/repo>]           # break
python3 scripts/testing/break_snyk.py [--repo <owner/repo>] --heal    # heal
```

Requires `GITHUB_TOKEN` (to push the fixture repo) plus
`SNYK_API_TOKEN` + `SNYK_ORG_ID` (to trigger the Snyk re-import; without
them the script still toggles the manifest and tells you to import
manually). **Credential status:** this machine has no Snyk credentials —
`~/.prash/.env` holds only empty `GITHUB_TOKEN`/`VERCEL_TOKEN`, no repo
`.env`, no env vars (the earlier "Credentials present" note was stale, same
as GCP/Vercel). The GitHub half (repo create + push) was verified live;
the Snyk import/scan half needs a real `SNYK_API_TOKEN` + `SNYK_ORG_ID`.

Resource name to investigate with: the Snyk project name is the repo path,
`prash investigate ALavent/prash-snyk-fixture --provider snyk` (after
importing the repo into Snyk once).

## Vercel

**Status: fixture script added (`break_vercel.py`, 2026-08-30); live re-run
blocked on credentials — the 2026-08-24 sprint token is gone.**

`scripts/testing/break_vercel.py` is the reusable fixture: Vercel has no
"incident" toggle, so the natural break/heal pair is the two write actions
the connector already live-verified in the 2026-08-24 E2E sprint —
**redeploy (break)** creates a fresh deployment (real churn, makes
`poll_state()` briefly non-READY), **rollback (`--heal`)** re-points
production at the pre-break deployment. Same API endpoints the connector
uses (`/v13/deployments`, `/v9/projects/{id}/rollback/{deploymentId}`).

```bash
python3 scripts/testing/break_vercel.py --project <name>          # redeploy (break)
python3 scripts/testing/break_vercel.py --project <name> --heal   # rollback (heal)
```

Requires `VERCEL_TOKEN` (and optionally `VERCEL_PROJECT`, or `--project`)
in `.env`. The 2026-08-24 sprint's project id may no longer be current —
confirm the project first with `prash investigate <project> --provider vercel`.

**Re-check result (2026-08-30):** no valid `VERCEL_TOKEN` exists on this
machine anymore — `~/.prash/.env` has both `VERCEL_TOKEN` and
`GITHUB_TOKEN` as **empty placeholders** (len=0), `test.env` is empty too,
and no env var is set. The script's failure paths were verified (clean
"VERCEL_TOKEN not set" / "No project given" exits); the live redeploy/
rollback run needs a fresh token from the account owner before reuse.

## GitHub / GitLab

**Status: proven working (multiple sessions), fixtures are the live repos
already in use** (`Drufiy/Lear-backend` for GitHub,
`drufiyai-group/prash-ci-test` for GitLab).

**Standing always-broken CI fixture added (2026-08-30):** branch
`prash-broken-ci` on `Drufiy/Lear-backend` carries a workflow
(`.github/workflows/always-broken.yml`) that **always fails** — a
"Simulate a broken step" that prints a realistic error and `exit 1`. It is
gated to `on: push: branches: [prash-broken-ci]`, so it never runs on main
or PRs and never affects real CI signal. Verified live: pushing the branch
and an empty-commit re-trigger both produced `conclusion=failure` runs with
the intended step failing (checkout/setup all green).

To use the fixture (no fresh push needed — the branch's last run stays
failed, and an empty commit re-triggers anytime):

```
prash fix <owner>/<repo> --ci --run-id <run-id> --noninteractive
prash investigate <owner>/<repo> --ci
git commit --allow-empty -m "re-trigger" && git push origin prash-broken-ci
```

GitLab's `drufiyai-group/prash-ci-test` still needs a fresh pipeline
push to trigger a new failure — the always-broken fixture is GitHub-only
for now.

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

**Status (2026-08-30): GCP connector unit-tested (gcloud-fallback path) +
fixture script added; live run still blocked — this machine has no GCP
credentials. Azure has no credentials configured at all.**

The earlier "GCP has credentials" note is **stale for this machine** —
re-checked 2026-08-30: no `GCP_PROJECT_ID`/`GCP_REGION`/
`GOOGLE_APPLICATION_CREDENTIALS` anywhere (`~/.prash/.env` has only empty
`GITHUB_TOKEN`/`VERCEL_TOKEN`, no repo `.env`, no env vars, no service-
account JSON, no `gcloud` on PATH). The google API libs aren't installed
either, so the connector runs entirely through its `gcloud` CLI fallback
here.

**Added:** `scripts/testing/break_gcp.py` — the reusable fixture. GCP's
natural break/heal is stop/start: **break** stops the instance
(`gcloud compute instances stop` → `poll_state()` reports STABLE),
**`--heal`** starts it again (→ HEALTHY). Requires `GCP_PROJECT_ID` +
`GCP_ZONE` (or `GCP_REGION`) and either `GOOGLE_APPLICATION_CREDENTIALS`
or `gcloud auth`.

**Added:** `tests/test_gcp_connector.py` — 10 unit tests mocking the
`gcloud` fallback path (auth gate, locate, state mapping RUNNING→HEALTHY /
STOPPED→STABLE / PROVISIONING→DEPLOYING, not-found, fetch_logs serial
output). The connector previously had zero test coverage.

Live run (blocked): needs a real project + service-account JSON or
`gcloud auth`, then `break_gcp.py` → `prash investigate <name>
--provider gcp` → `--heal`.

Azure still needs an account/subscription, which is Aradhya's to create
(not something I can do on your behalf).

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
