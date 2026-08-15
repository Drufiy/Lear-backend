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
| Real k8s pod, brain declines (`recommended_action: none`) | `prash fix <ns>/<pod>` on a deterministically-broken pod | [x] 2026-08-15 ✅ real model call against `broken-app`, correctly read the container's actual error message, category=runtime, recommended_action=none, reasoning was accurate (deterministic missing-config failure, restart won't help) | [ ] |
| Real k8s pod, brain recommends `restart_pod` | Same, on a genuinely wedged pod | [ ] not yet — needs a purpose-built "wedged, not deterministically broken" fixture (a prior session's ConfigMap-flag trick from 2026-08-13), not rebuilt this pass | [ ] |
| Unknown/missing pod | `prash fix prash-demo/does-not-exist` — clean error, not a stack trace | [x] 2026-08-15 ✅ `pod prash-demo/does-not-exist not found`, exit 2, no traceback | [ ] |
| CI multi-failure path | `prash fix <owner>/<repo> --ci --run-id <n>` against a real GitHub Actions run (needs `GITHUB_TOKEN`) — **never tested live through the actual CLI, only as a bare function call** | [x] 2026-08-15 ❌→✅ **found the path was diagnosis-only (headline said "Fixed X of N" when nothing was ever fixed — no PR, no dispatch, mode/dry-run/noninteractive all silently ignored). Built the real fix: new `apply-ci-fix` action, logged as a CROSS-TRACK design decision in PRASH_V2.md §9 before writing code. Live-verified twice**: once diagnosing a real 2-independent-failure run, once end-to-end with a real planted bug — real branch, real commit, real PR (#4) opened with the exact correct fix, approved at the real interactive prompt, then closed without merging (throwaway verification). 146/146 passing. | [ ] |
| `--ci` without `--run-id` | Clean error, not a crash | [x] 2026-08-15 ✅ | [ ] |
| `--ci` without `GITHUB_TOKEN` set | Clean error naming what's missing | [x] 2026-08-15 ✅ `CI diagnosis needs GITHUB_TOKEN in local .env`, exit 3 | [ ] |
| `rollback` recommended | Confirm it surfaces as a manual next-step message, not a silent no-op or a guess | [ ] not reachable via `prash fix` today — Track B has no pod→Deployment lookup, so the k8s brain never actually recommends `rollback` from a pod diagnosis (by design, §10 2026-08-09). `_render_no_auto_action`'s rollback-message branch exists in code but has no live path to trigger it through `fix` specifically; `prash run rollback` directly was verified in §1 instead | [ ] |
| `--dry-run` / `--noninteractive` / `--mode` / `--env` | Same checks as 1d, but through `fix` | [x] 2026-08-15 ⚠️ partially — `--noninteractive` verified live (real CI run, real `NEEDS_APPROVAL` outcome, no hang, no crash) and covered by 2 new unit tests; `--dry-run`/`--mode`/`--env` through `fix` specifically not yet re-verified live (covered indirectly by the same dispatcher code path already proven in §1, but not re-run live through `fix` itself this pass) | [ ] |

---

## 3. `prash investigate <resource>`

| Provider | macOS | Windows |
|---|---|---|
| `--provider github` (default) | [ ] blocked — needs `GITHUB_TOKEN` in `.env` for a real authenticated call, only the no-token path tested so far | [ ] |
| `--provider vercel` | [ ] blocked — needs `VERCEL_TOKEN`, same reason | [ ] |
| No token configured for the provider | [x] 2026-08-14 ❌→✅ **found a real crash, fixed.** `cmd_investigate` printed "auth not configured" then fell through into `poll_state()` anyway with no session. GitHub's connector crashed with an unhandled `KeyError` indexing an empty API response (raw traceback, not a clean message); Vercel's connector happened not to crash but silently returned a fake "not-found" result instead of honestly stopping. Fixed: `cmd_investigate` now returns immediately after the warning for both providers. 1 regression test, 141/141 passing. | [ ] |

---

## 4. Everything else

| Command | What to verify | macOS | Windows |
|---|---|---|---|
| `prash actions` | Lists all 4 actions with correct risk tier + reversibility | [x] 2026-08-14 ✅ matches action registry exactly | [ ] |
| `prash audit` | Shows real entries after the above; `--tail N` actually limits | [x] 2026-08-14 ✅ `--tail 5` returned exactly the 5 most recent real entries | [ ] |
| `prash config` | Secrets shown as redacted, never in plaintext | [x] 2026-08-14 ✅ (see §0.4) | [ ] |
| `prash circuit status` | Shows real breaker state | [x] 2026-08-14 ✅ | [ ] |
| `prash circuit reset` (no resource) | Resets everything | [x] 2026-08-14 ✅ | [ ] |
| `prash circuit reset <resource>` | Resets only that resource | [x] 2026-08-14 ✅ | [ ] |
| `prash watch` | Detects a real new problem, notifies once, stays silent on repeat polls (§10, already verified once on macOS — re-verify after any watcher changes) | [x] 2026-08-14 ✅ re-verified against a fresh cluster session (see §0.5) | [ ] |
| `prash watch --namespace` / `--interval` | Both flags actually take effect | [x] 2026-08-14 ✅ `--namespace default` correctly overrode `.env`'s `prash-demo`; `--interval 5` measured at ~5.02s between polls via timestamped output | [ ] |
| Desktop notification actually fires (not just logged) | **macOS: verified via `osascript` fallback. Windows: never verified live — only mocked. Priority item.** | [x] 2026-08-14 ✅ macOS confirmed: direct `osascript display notification` call exits 0, and no "notification failed" warning appeared in any real watch run today (which would have logged if the fallback failed) | [ ] still the priority item |
| `--env-file` (top-level flag) | Points `prash` at a non-default `.env` location correctly | [x] 2026-08-14 ✅ pointed at an alternate file with a different `KUBE_NAMESPACE` — watcher correctly used the alternate value, not the default `.env` | [ ] |

---

## 5. Cross-platform specifics (Windows-heavy, but check both)

| Item | macOS | Windows |
|---|---|---|
| Path handling (`pathlib`, not raw string paths) breaks nothing | [x] 2026-08-14 ✅ no path issues across the entire §0/§1/§4/§5 pass; codebase uses `pathlib.Path` consistently, not raw string concatenation | [ ] |
| Shell quoting in any subprocess call (`osascript`, `kubectl` via the client lib, `kind`) | [x] 2026-08-14 ✅ `osascript` call uses `subprocess.run([...])` as a list (no `shell=True`, no shell-injection surface) plus its own `_applescript_escape()` for the AppleScript string literal itself — tested directly with a title/message containing embedded `"` and `\` characters, notification still fired correctly, no broken script | [ ] |
| `kind` / Docker Desktop cluster setup works from a clean machine | [x] 2026-08-14 ✅ **actually torn down and rebuilt from scratch** (`kind delete cluster --name prash-dev` → `kind create cluster --name prash-dev`) to verify this for real, not from memory. Node Ready in ~22s, kubectl context auto-set to `kind-prash-dev` exactly as PRASH_V2.md documents, `testdata/broken-pod.yaml` reapplied and reached `CrashLoopBackOff` within ~15s, `prash watch` smoke-tested clean against the fresh cluster immediately after | [ ] |
| Line endings don't break `.env` parsing (CRLF vs LF) | [x] 2026-08-14 ✅ built a real CRLF-terminated `.env` file (`\r\n` line endings, matching what a Windows editor would produce) and loaded it through `CredentialStore` directly — `str.splitlines()` already handles CRLF/LF/CR uniformly, confirmed no stray `\r` leaking into any parsed value | [ ] |
| Ctrl+C during a running command (`watch`, an in-progress `fix`) exits cleanly, no orphaned process | [x] 2026-08-14 ✅ verified via a direct subprocess + `SIGINT` (not a shell-backgrounded job, which masks SIGINT for background jobs by shell convention and gave a false "hung" reading on the first attempt) — exits cleanly with code 130, prints "interrupted", no orphaned process left behind | [ ] |

---

## Open issues found during this pass

Track severity/owner in GitHub Issues per `PRASH_V2.md` §0c. List them here too, just as a pointer — don't duplicate the write-up:

| Issue | Severity | Found by | Link |
|---|---|---|---|
| `--dry-run` bypasses the permission engine's REFUSE/PROMPT gate for every mode; terminal output can read e.g. "refuse / succeeded" under `--mode read-only --dry-run` (self-contradictory at a glance, though the audit log's `dry_run: true` field makes it reconstructable). No safety impact — real infra is never touched either way. | P2 | Aradhya, §1c, 2026-08-14 | [#1](https://github.com/Drufiy/prash-v2-backend/issues/1) |
| Kimi fallback's missing-credentials error names `OPENAI_API_KEY`, never `KIMI_API_KEY` — confusing when both the primary model and the fallback fail in the same run. Doesn't crash, correctly excluded that one sub-diagnosis and reported the rest honestly. | P2 | Aradhya, §2, 2026-08-15 | [#5](https://github.com/Drufiy/prash-v2-backend/issues/5) |
