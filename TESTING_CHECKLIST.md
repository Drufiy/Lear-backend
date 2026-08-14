# Prash v2 — Hardening Phase Test Checklist

Shared by Aradhya (macOS) and Aryan (Windows) — see `PRASH_V2.md` §6b for why this
phase exists and the exit criteria this checklist exists to satisfy (specifically
#2: "every registered command has been run at least once on both platforms, with
the result written down").

**How to use this:** check the box, fill in date + result. `✅` pass, `⚠️` pass with
a note, `❌` fail (open a GitHub Issue per `PRASH_V2.md` §0c, link it here). Don't
mark something done from memory days later — do it and log it in the same sitting.
A blank row is honest; a wrong ✅ is worse than no data at all.

Generated from `prash/cli.py`'s actual `build_parser()` output on 2026-08-14
(commit `ed670ab`) — every flag below is real, not a guess. If the CLI surface
changes, regenerate this list rather than letting it drift from the code.

---

## 0. First-run setup (the exact gap that started this phase)

The most important row in this whole document — this is the path that broke on
first real use and zero tests ever exercised.

| # | Step | macOS | Windows |
|---|---|---|---|
| 0.1 | Fresh `git clone`, fresh venv, `pip install -e ".[dev]"` — no errors | [x] 2026-08-14 ✅ | [ ] |
| 0.2 | `prash` (bare console script) resolves and runs — not `python -m prash.cli` | [x] 2026-08-14 ✅ resolves to `.venv/bin/prash`, prints usage (no subcommand given), no traceback | [ ] |
| 0.3 | `cp .env.example .env`, fill in only `KIMI_API_KEY` (or `DEEPSEEK_API_KEY`) + `KUBE_CONTEXT`, leave everything else blank exactly as shipped | [ ] 2026-08-14 ⚠️ `KUBE_CONTEXT`/`KUBE_NAMESPACE` set, but **neither `KIMI_API_KEY` nor `DEEPSEEK_API_KEY` filled in yet** — blocks `prash fix` / diagnosis testing until Aradhya adds one to his own `.env` | [ ] |
| 0.4 | `prash config` — runs clean, no crash, secrets shown as redacted not blank/error | [x] 2026-08-14 ✅ "secret values are never shown"; note: "keys present" lists key *names* from the file regardless of whether the value is blank (e.g. lists `KIMI_API_KEY` even though it's currently empty) — not a bug, just worth knowing when reading the output | [ ] |
| 0.5 | `prash watch` against a real (or `kind`) cluster — no `ConfigException`, no crash from any other blank `.env` field | [x] 2026-08-14 ✅ ran 20s against live `kind-prash-dev`/`prash-demo`: detected real `broken-app` pod (CrashLoopBackOff, restart_count=97), notified once, next poll correctly said "no new problems" (dedup working). **The exact bug that started this phase is fixed.** | [ ] |

---

## 1. `prash run <action> <resource>`

### 1a. Per action, default `ask` mode (answer `y`)

| Action | Risk tier | macOS | Windows |
|---|---|---|---|
| `open-pr` | SAFE | [x] 2026-08-14 ⚠️ prompt+audit correct; execution fails cleanly with "GitHub authentication failed" since no `GITHUB_TOKEN` is set yet — expected given §0.3, re-test once the token is in | [ ] |
| `request-secret` | SAFE | [x] 2026-08-14 ✅ real prompt, real password-masked value entry, stored + verified in local store (tested with a synthetic dummy value, cleaned up after) | [ ] |
| `restart-pod` | SAFE | [x] 2026-08-14 ✅ real cluster mutation confirmed — pod recreated with new name/reset restart count | [ ] |
| `rollback` | APPROVAL | [x] 2026-08-14 ✅ prompt correct; fails cleanly with "no rollout driver wired to act on it" — this is documented, intentional (PRASH_V2.md §10, 2026-08-09: rollback reads last-known-good but the apply driver is Tier 3, dropped this sprint), not a bug | [ ] |

### 1b. Per action, answer `n` at the prompt — confirm it's actually skipped, nothing executes, audit still logs the decline

| Action | macOS | Windows |
|---|---|---|
| `open-pr` | [x] 2026-08-14 ✅ | [ ] |
| `request-secret` | [x] 2026-08-14 ✅ nothing stored on decline | [ ] |
| `restart-pod` | [x] 2026-08-14 ✅ pod untouched | [ ] |
| `rollback` | [x] 2026-08-14 ✅ | [ ] |

### 1c. Every permission mode (use `restart-pod` as the probe action — SAFE tier, cheapest to test repeatedly)

| `--mode` | Expected behavior | macOS | Windows |
|---|---|---|---|
| `read-only` | Refused outright, no prompt | [x] 2026-08-14 ✅ | [ ] |
| `ask` (default) | Prompts every time | [x] 2026-08-14 ✅ (see 1a) | [ ] |
| `auto-safe` | SAFE tier runs without asking; APPROVAL tier (`rollback`) still prompts | [x] 2026-08-14 ✅ verified both halves with a real (non-dry-run) restart-pod | [ ] |
| `environment-scoped` | Auto on `--env staging`; always prompts on `--env production` | [x] 2026-08-14 ✅ | [ ] |
| `bypass` | Runs without asking, but still refuses anything in the NEVER tier outright | [x] 2026-08-14 ⚠️ SAFE-tier auto-run confirmed; NEVER-tier refusal not separately re-tested here (no NEVER-tier action currently registered to probe with — see `prash actions`) | [ ] |

**Note found while testing:** `--dry-run` bypasses the permission engine's gate entirely, for every mode including `read-only` — it still computes and displays the correct `decision` label (e.g. `refuse`) but always returns `status: succeeded` with a plan. Never touches real infra either way (upholds the flag's own contract), but the terminal output for `--mode read-only --dry-run` literally reads "refuse / succeeded" — self-contradictory to someone scanning output live, even though the audit log's `dry_run: true` field makes the full picture reconstructable. Logged as an open finding below, not fixed yet (low severity — no safety impact, just a confusing label).

### 1d. Flags

| Flag | What to verify | macOS | Windows |
|---|---|---|---|
| `--dry-run` | Produces a plan, **never touches real infrastructure** — confirm nothing actually changed | [x] 2026-08-14 ✅ never mutated the cluster in any dry-run test; see the decision-label note under 1c though | [ ] |
| `--grant` | **Checklist corrected 2026-08-14** — the code's actual, documented contract (`prash/permissions.py` docstring) is the opposite of what this row used to say: `grant` is meaningless for SAFE tier (mode alone decides), and it's the intended way to pre-approve one APPROVAL-tier action without an interactive prompt. Verified: SAFE tier ignores `--grant` under `ask` mode (still prompts); APPROVAL tier (`rollback --grant`) skips the prompt and runs. | [x] 2026-08-14 ✅ (corrected understanding, not a bug) | [ ] |
| `--noninteractive` | Never prompts; a missing secret returns `NEEDS_INPUT` instead of hanging waiting for input | [x] 2026-08-14 ✅ (needs a mode that lets the action actually reach execute() — `ask` mode alone resolves to `NEEDS_APPROVAL` before ever reaching the secret check, which is correct: noninteractive doesn't force-allow a PROMPT decision, it just removes the interactive channel) | [ ] |
| `--secret-name` / `--secret-hint` | `request-secret` picks these up correctly | [x] 2026-08-14 ✅ (see 1a) | [ ] |
| `--head` / `--base` / `--title` / `--body` | `open-pr` uses these correctly, not silently ignored | [x] 2026-08-14 ✅ all four appear correctly in the rendered plan | [ ] |
| `--env staging` vs `--env production` | Actually changes behavior under `environment-scoped` (see 1c) | [x] 2026-08-14 ✅ | [ ] |
| Circuit breaker | Trip it deliberately (exceed `PRASH_CIRCUIT_MAX_ACTIONS` on one resource) — confirm it stops, escalates, and `prash circuit status`/`reset` work | [x] 2026-08-14 ✅ tripped for real at 5 actions/60s on one pod, 6th attempt correctly refused with escalation message, `circuit status` showed OPEN, per-resource `circuit reset <resource>` and global `circuit reset` (no arg) both confirmed clearing it | [ ] |

**Bug found + fixed 2026-08-14:** a SAFE-tier action that reaches the interactive approval prompt with no stdin available (piped input already exhausted, Ctrl+D, or a script that forgot `--noninteractive`) crashed with an uncaught `EOFError` and a full Python traceback instead of a clean decline. Same defect existed at the `request-secret` value prompt. Fixed in `prash/cli.py` (`CliAsk.ask()` and the `secret_input` closure in `_make_context()`) — both now catch `EOFError`/`KeyboardInterrupt` and treat "no answer available" the same as an explicit "no," consistent with the existing `default="n"` behavior. Regression tests added in `tests/test_cli.py`. 140/140 passing (was 138). Commit: see PRASH_V2.md §10.

---

## 2. `prash fix`

| Case | Command shape | macOS | Windows |
|---|---|---|---|
| Real k8s pod, brain declines (`recommended_action: none`) | `prash fix <ns>/<pod>` on a deterministically-broken pod | [ ] | [ ] |
| Real k8s pod, brain recommends `restart_pod` | Same, on a genuinely wedged pod | [ ] | [ ] |
| Unknown/missing pod | `prash fix prash-demo/does-not-exist` — clean error, not a stack trace | [ ] | [ ] |
| CI multi-failure path | `prash fix <owner>/<repo> --ci --run-id <n>` against a real GitHub Actions run (needs `GITHUB_TOKEN`) — **never tested live through the actual CLI, only as a bare function call** | [ ] | [ ] |
| `--ci` without `--run-id` | Clean error, not a crash | [ ] | [ ] |
| `--ci` without `GITHUB_TOKEN` set | Clean error naming what's missing | [ ] | [ ] |
| `rollback` recommended | Confirm it surfaces as a manual next-step message, not a silent no-op or a guess | [ ] | [ ] |
| `--dry-run` / `--noninteractive` / `--mode` / `--env` | Same checks as 1d, but through `fix` | [ ] | [ ] |

---

## 3. `prash investigate <resource>`

| Provider | macOS | Windows |
|---|---|---|
| `--provider github` (default) | [ ] | [ ] |
| `--provider vercel` | [ ] | [ ] |
| No token configured for the provider | Clean "not configured" message, not a crash — [ ] | [ ] |

---

## 4. Everything else

| Command | What to verify | macOS | Windows |
|---|---|---|---|
| `prash actions` | Lists all 4 actions with correct risk tier + reversibility | [ ] | [ ] |
| `prash audit` | Shows real entries after the above; `--tail N` actually limits | [ ] | [ ] |
| `prash config` | Secrets shown as redacted, never in plaintext | [ ] | [ ] |
| `prash circuit status` | Shows real breaker state | [ ] | [ ] |
| `prash circuit reset` (no resource) | Resets everything | [ ] | [ ] |
| `prash circuit reset <resource>` | Resets only that resource | [ ] | [ ] |
| `prash watch` | Detects a real new problem, notifies once, stays silent on repeat polls (§10, already verified once on macOS — re-verify after any watcher changes) | [ ] | [ ] |
| `prash watch --namespace` / `--interval` | Both flags actually take effect | [ ] | [ ] |
| Desktop notification actually fires (not just logged) | **macOS: verified via `osascript` fallback. Windows: never verified live — only mocked. Priority item.** | [ ] | [ ] |
| `--env-file` (top-level flag) | Points `prash` at a non-default `.env` location correctly | [ ] | [ ] |

---

## 5. Cross-platform specifics (Windows-heavy, but check both)

| Item | macOS | Windows |
|---|---|---|
| Path handling (`pathlib`, not raw string paths) breaks nothing | [ ] | [ ] |
| Shell quoting in any subprocess call (`osascript`, `kubectl` via the client lib, `kind`) | [ ] | [ ] |
| `kind` / Docker Desktop cluster setup works from a clean machine | [ ] | [ ] |
| Line endings don't break `.env` parsing (CRLF vs LF) | [ ] | [ ] |
| Ctrl+C during a running command (`watch`, an in-progress `fix`) exits cleanly, no orphaned process | [ ] | [ ] |

---

## Open issues found during this pass

Track severity/owner in GitHub Issues per `PRASH_V2.md` §0c. List them here too, just as a pointer — don't duplicate the write-up:

| Issue | Severity | Found by | Link |
|---|---|---|---|
| `--dry-run` bypasses the permission engine's REFUSE/PROMPT gate for every mode; terminal output can read e.g. "refuse / succeeded" under `--mode read-only --dry-run` (self-contradictory at a glance, though the audit log's `dry_run: true` field makes it reconstructable). No safety impact — real infra is never touched either way. | P2 | Aradhya, §1c, 2026-08-14 | *(GitHub Issue not yet opened — open before end of session per §0c if still unfixed)* |
