# Lear — End-to-End Test Checklist

Goal: prove Prash actually solves problems, from a cold user's point of view —
no pre-known answers, no hand-holding. Seed a real failure → run CLI/REPL →
Prash diagnoses → Prash fixes (or proposes a fix) → we verify the fix actually
worked, not just that a command exited 0.

Run everything through the CLI/REPL exactly as a new user would. Don't call
connector methods directly in a Python shell — that only proves the plumbing,
not the product.

Waiting on: Anant's Azure, GCP, Terraform connectors (WhatsApp: "azure google
cloud done, only terraform left" — not yet merged to `main`, no open PR as of
2026-08-22). Add rows for those once his PR lands. Config wizard is confirmed
done on his side.

---

## 0. Setup sanity (5 min)

- [ ] `.env` has every key filled for every connector under test (see table below)
- [ ] `gitleaks` on PATH (`which gitleaks`)
- [ ] Fresh terminal, no stale env vars shadowing `.env`
- [ ] `git status` clean before starting (so we can tell Prash's edits apart from ours)

| Connector  | Keys required | Status (as of 2026-08-22) |
|---|---|---|
| GitHub | `GITHUB_TOKEN` | ✓ set |
| GitLab | `GITLAB_TOKEN` | ✓ set |
| Vercel | `VERCEL_TOKEN` | ✓ set, live-verified |
| AWS | `AWS_ACCESS_KEY_ID/SECRET/REGION` | blank — skip unless needed tonight |
| Kubernetes | `KUBECONFIG`/`KUBE_CONTEXT`/`KUBE_NAMESPACE` | ✓ set (kind-prash-dev) |
| Datadog | `DATADOG_API_KEY` + `DATADOG_APP_KEY` | ✓ set + live-verified 2026-09-07 (note: this org's API key is denied Events v2 intake — connector falls back to v1, see §5b) |
| Grafana | `GRAFANA_URL` + `GRAFANA_API_KEY` | ✓ set |
| PagerDuty | `PAGERDUTY_API_KEY` + `FROM_EMAIL` + `ROUTING_KEY` | ✓ set |
| Snyk | `SNYK_API_TOKEN` + `SNYK_ORG_ID` | ✓ set |
| Gitleaks | binary on PATH | ✓ installed |
| Azure/GCP/Terraform | — | **not merged yet, blocked on Anant** |

---

## 1. GitHub CI (diagnose + fix loop)

- [ ] In a scratch repo, break a real workflow (bad YAML, or a failing unit test)
- [ ] Push, let CI actually fail
- [ ] `prash investigate <owner/repo> --ci` — cold, no hints
- [ ] Confirm diagnosis correctly names the real cause
- [ ] Let Prash open the fix PR (`open-pr` action)
- [ ] Review the PR diff — is it a real fix or a plausible-looking guess?
- [ ] Merge it, confirm CI goes green
- [ ] Check `.prash/audit.log` recorded the action

## 2. GitLab CI (already live-verified once — re-confirm with new write-action code)

- [ ] Break `prash-ci-test` pipeline again (new failure mode, not the same one as before)
- [ ] `prash investigate --ci` against pipeline
- [ ] Confirm single coherent diagnosis — **specifically re-check the phantom
      "2 of 2" bug is still fixed** (`include_raw_tail=False`) now that write
      actions have touched this path
- [ ] Let it open the fix MR, merge, confirm pipeline green

## 3. Gitleaks → PagerDuty escalate (cross-connector action — highest-risk one to verify)

- [ ] `prash investigate . --provider gitleaks` — confirm it (still) finds the
      7 known findings in `tests/test_gitleaks_connector.py`
- [ ] Confirm secrets are stripped from all output (no `Secret`/`Match` fields visible)
- [ ] **Ask before firing** — `prash run gitleaks-escalate . --provider gitleaks`
- [ ] Open PagerDuty dashboard, confirm a real incident appeared
- [ ] Confirm the incident payload does NOT contain actual secret text
- [ ] Resolve the incident afterward so it doesn't page anyone by mistake

## 4. Vercel (read + both write actions)

- [ ] Break a real deployment (bad env var or a build-breaking commit) in a scratch Vercel project
- [ ] `prash investigate <project> --provider vercel` — confirm FAILED state detected
- [ ] `prash run vercel-redeploy <project> --provider vercel` — confirm it redeploys and succeeds if root cause is fixed
- [ ] Separately test `vercel-rollback` — confirm it refuses without `--deployment-id`, then succeeds with one
- [ ] Confirm site is actually reachable/correct after either action, not just "readyState: READY"

## 5. Datadog (live-verified 2026-09-07)

- [x] Get `DATADOG_APP_KEY` from org settings → Application Keys — set in local `.env`, both keys validated live
- [x] Create or use a real monitor, trip it into ALERT — `scripts/testing/break_datadog.py` trips `prash-test-synthetic-error-rate` (id 319727487)
- [x] `prash investigate <monitor> --provider datadog` — Alert → `failed`, OK → `healthy`, and the get_stats timeline renders below the state
- [x] `prash run datadog-mute-monitor <monitor> --minutes 10 --mode auto-safe` — muted + verified (`overall_state=OK`, auto-expires). Correction to this row as originally written: `prash run` takes NO `--provider` flag (connectors are always built from .env), and SAFE tier still prompts in ask mode — `--grant` only pre-approves APPROVAL-tier actions; use `--mode auto-safe` (or answer the prompt) for SAFE ones.
- [x] Confirm mute actually shows — confirmed via the API verify line + audit id; the 10-minute window auto-expires

### 5b. Datadog autonomous loop (watch → diagnose → act → verify → notify, M4)

- [x] `python scripts/testing/break_datadog.py --heal` — fixture monitor settled OK (note: with sparse single points Datadog's evaluation is sticky — if the state doesn't settle, re-run `--heal` to put a fresh point in the 5m window)
- [x] `prash watch --provider datadog --resource prash-test-synthetic-error-rate` — ran bounded (max_iterations), polls clean
- [x] First poll reports baseline with no notifications (no duplicate pings on unchanged state)
- [x] `python scripts/testing/break_datadog.py` — watch caught OK→Alert within one poll cycle: "⚠ Monitor 'prash-test-synthetic-error-rate' entered Alert state"
- [x] The same Alert state does NOT re-notify on the next poll (dedup) — 8 consecutive Alert polls, one notification
- [x] `python scripts/testing/break_datadog.py --heal` — recovery (Alert → OK) is notified too: "⚠ Monitor ... recovered to OK"
- [x] `prash investigate prash-test-synthetic-error-rate --provider datadog` — timeline shows the alert events ([Triggered]/[Recovered] monitor_alert entries + metric_spike context). Found live + fixed 2026-09-07: monitor-alert events need the `@monitor_id:` facet (bare `monitor_id:` matched ZERO events) and nest title/transition under attributes.attributes — `_monitor_events` now parses the real shape.
- [ ] Brain: `diagnose_datadog_monitor('prash-test-synthetic-error-rate')` (REPL/chat route) yields category `monitoring` with `mute_monitor` as a labeled stopgap, files_changed empty — **BLOCKED 2026-09-07: no valid LLM key on this machine** (test.env's DEEPSEEK_API_KEY is an invalid placeholder, KIMI_API_KEY empty). Needs one real DEEPSEEK_API_KEY or KIMI_API_KEY in local .env; the code path itself is unit- + eval-covered.
- [x] `prash run datadog-alert <target> --text "Prash E2E test"` — shows the APPROVAL prompt ("This will create a visible alert in Datadog"), declines work (no stdin → clean decline, audit recorded)
- [x] Re-run with the approval accepted (`--grant`) — event posted (via v1 fallback; this org's API key is denied v2 intake), `✓` verify line confirms it after the intake→searchability propagation retry, audit id printed
- [x] `prash watch --provider datadog` with no targets and no `DATADOG_WATCH_MONITORS` — clean error naming the env var, exit 2
- [x] `DATADOG_WATCH_MONITORS=prash-test-synthetic-error-rate` (no `--resource`) — same watch behavior as the flag

## 6. Grafana (read + silence-alert)

- [ ] Trip a real alert rule into firing state (or use an existing one)
- [ ] `prash investigate <alert> --provider grafana` — confirm state detected via Alertmanager cross-reference
- [ ] `prash run grafana-silence-alert <alert> --provider grafana --minutes 10`
- [ ] Confirm silence appears in Grafana's Alerting → Silences UI

## 7. PagerDuty (read + ack/resolve)

- [ ] Trigger a real incident on a test service (manually, or via the gitleaks-escalate above)
- [ ] `prash investigate <service> --provider pagerduty` — confirm FAILED (triggered) vs DEGRADED (acked) distinction works
- [ ] `prash run pagerduty-acknowledge <service> --provider pagerduty`
- [ ] Confirm state flips to acknowledged in PagerDuty UI
- [ ] `prash run pagerduty-resolve <service> --provider pagerduty` — confirm this one prompts (APPROVAL tier) even in auto-safe mode
- [ ] Confirm resolved in UI

### 7b. PagerDuty autonomous loop (watch → diagnose → act → verify → notify, Phase 3)

- [ ] `python scripts/testing/break_pagerduty.py --heal` — confirm the fixture incident (dedup key `prash-test-fixture`) is closed before starting
- [ ] `prash watch --provider pagerduty --resource prash-v2` — leave it running
- [ ] `python scripts/testing/break_pagerduty.py` — within one poll cycle the watcher detects the new trigger: desktop toast + console ⚠ + team channels if configured
- [ ] The same open incident does NOT re-notify on the next poll (dedup by incident id + status + assignments)
- [ ] Acknowledge the incident in the PagerDuty UI — the acknowledgment transition is detected and notified
- [ ] `python scripts/testing/break_pagerduty.py --heal` — the resolution transition is notified too (stand-down signal)
- [ ] `prash investigate prash-v2 --provider pagerduty` — output now includes the `get_stats()` timeline (incident + change events), not just point-in-time state
- [ ] Brain: `diagnose_pagerduty_incident('prash-v2')` (REPL/chat route) yields category `monitoring` with `acknowledge_incident` as a labeled stopgap, files_changed empty
- [ ] `prash run pagerduty-page <service>` — shows the APPROVAL prompt ("This will wake up the on-call engineer"), declines cleanly
- [ ] Re-run with the approval accepted — a real incident appears in PagerDuty (visible in the UI), the `✓` verify line matches it by dedup key, audit id printed; then resolve the paged incident by hand
- [ ] `prash watch --provider pagerduty` with no targets and no `PAGERDUTY_WATCH_SERVICES` — clean error naming the env var, exit 2
- [ ] `PAGERDUTY_WATCH_SERVICES=prash-v2` (no `--resource`) — same watch behavior as the flag

## 8. Snyk (read + ignore-issue)

- [ ] Use a real project with at least one known vulnerability
- [ ] `prash investigate <project> --provider snyk` — confirm severity mapped to state correctly
- [ ] `prash run snyk-ignore-issue <project_id>/<issue_id> --provider snyk --reason "test suppression"`
- [ ] Confirm it refuses without `--reason`
- [ ] Confirm issue shows as ignored (not "wont-fix") in Snyk dashboard, with expiry ~30 days out

## 9. Kubernetes (re-verify after all the new action code — regression pass)

- [ ] Re-run the OOM and configmap-mismatch stress fixtures from `track-b/manifest-fix-stress-fixtures`
- [ ] `restart-pod`, `scale`, `edit-configmap`, `edit-secret`, `exec` — one real run each
- [ ] Confirm nothing regressed from the write-action refactor

## 10. AWS (skip tonight unless credentials are ready)

- [ ] `execute-aws` action + config wizard — Anant's PR #23, confirm still working post-refactor

## 11. Azure / GCP / Terraform — BLOCKED

- [ ] Wait for Anant's PR
- [ ] Same read → diagnose → write → verify loop as above, once merged
- [ ] Confirm his config wizard integrates cleanly with the existing `.env` schema

## 12. REPL — user-facing pass, not scripted

- [ ] Open `prash repl` cold, no prior context
- [ ] Talk to it like a real engineer would: contractions, vague phrasing, one open-ended question ("what's broken right now")
- [ ] Walk it through 2–3 of the scenarios above conversationally instead of via `prash run` — does context (namespace/pod/ci target) persist correctly across turns?
- [ ] Confirm no crash on apostrophes/unusual input (already fixed once — regression check)

## 13. Audit trail + circuit breaker (cross-cutting, check once at the end)

- [ ] `.prash/audit.log` has an entry for every write action run above
- [ ] Deliberately trip the circuit breaker (run one action 6x fast on the same resource) — confirm it stops and escalates instead of silently retrying
- [ ] `prash circuit status` and `prash circuit reset` both work

---

## What "done" means

Every checked box above is a **real state change confirmed in the actual
external dashboard** (GitHub, Vercel, Datadog, Grafana, PagerDuty, Snyk) — not
just a clean CLI exit code. A green CLI run with a stale/wrong dashboard is a
fail, not a pass.
