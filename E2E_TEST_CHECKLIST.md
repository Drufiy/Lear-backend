# Prash v2 — End-to-End Test Checklist

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
| Datadog | `DATADOG_API_KEY` + `DATADOG_APP_KEY` | APP_KEY missing — get before testing monitors/mute |
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

## 5. Datadog (needs `DATADOG_APP_KEY` first)

- [ ] Get `DATADOG_APP_KEY` from org settings → Application Keys
- [ ] Create or use a real monitor, trip it into ALERT (or pick one already alerting)
- [ ] `prash investigate <monitor> --provider datadog` — confirm FAILED/DEGRADED mapped correctly
- [ ] `prash run datadog-mute-monitor <monitor> --provider datadog --minutes 10`
- [ ] Confirm mute actually shows in Datadog UI, and unmutes after the window

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
