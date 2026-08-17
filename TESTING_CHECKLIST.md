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
| 0.1 | Fresh `git clone`, fresh venv, `pip install -e ".[dev]"` — no errors | [x] 2026-08-14 ✅ | [x] 2026-08-15 ✅ fresh `.venv` at repo root, `python -m venv .venv` + `pip install -e ".[dev]"` — installed cleanly (`kubernetes-36.0.3`, `textual-8.2.8`, etc.), editable install `prash-v2` built + installed, no errors |
| 0.2 | `prash` (bare console script) resolves and runs — not `python -m prash.cli` | [x] 2026-08-14 ✅ resolves to `.venv/bin/prash`, prints usage (no subcommand given), no traceback | [x] 2026-08-15 ✅ resolves to `.venv\Scripts\prash.exe`, prints masthead + usage (no subcommand given), exit 2, no traceback |
| 0.3 | `cp .env.example .env`, fill in only `KIMI_API_KEY` (or `DEEPSEEK_API_KEY`) + `KUBE_CONTEXT`, leave everything else blank exactly as shipped | [ ] 2026-08-14 ⚠️ `KUBE_CONTEXT`/`KUBE_NAMESPACE` set, but **neither `KIMI_API_KEY` nor `DEEPSEEK_API_KEY` filled in yet** — blocks `prash fix` / diagnosis testing until Aradhya adds one to his own `.env` | [ ] 2026-08-15 ⚠️ `.env.example` present; `prash config` runs clean with blank `GITHUB_TOKEN`/`VERCEL_TOKEN` keys in `.env` (names listed, values blank, no crash — same note as macOS) — real model/cluster keys still not filled on this machine |
| 0.4 | `prash config` — runs clean, no crash, secrets shown as redacted not blank/error | [x] 2026-08-14 ✅ "secret values are never shown"; note: "keys present" lists key *names* from the file regardless of whether the value is blank (e.g. lists `KIMI_API_KEY` even though it's currently empty) — not a bug, just worth knowing when reading the output | [x] 2026-08-15 ✅ "secret values are never shown", keys present listed (names only, incl. blank ones), no crash |
| 0.5 | `prash watch` against a real (or `kind`) cluster — no `ConfigException`, no crash from any other blank `.env` field | [x] 2026-08-14 ✅ ran 20s against live `kind-prash-dev`/`prash-demo`: detected real `broken-app` pod (CrashLoopBackOff, restart_count=97), notified once, next poll correctly said "no new problems" (dedup working). **The exact bug that started this phase is fixed.** | [ ] 2026-08-15 ⚠️ no cluster on this machine — **but found + fixed a real Windows bug in the process**: `prash watch` with no kube-config died with a raw `ConfigException` traceback (unlike `fix`, which handled it cleanly). Now stops cleanly with `watch stopped: Invalid kube-config file. No configuration found.`, exit 2, no traceback (fix + regression test in this commit). Live-cluster `watch` verification still deferred to a machine with a cluster |

---

## 1. `prash run <action> <resource>`

### 1a. Per action, default `ask` mode (answer `y`)

| Action | Risk tier | macOS | Windows |
|---|---|---|---|
| `open-pr` | SAFE | [x] 2026-08-14 ⚠️ prompt+audit correct; execution fails cleanly with "GitHub authentication failed" since no `GITHUB_TOKEN` is set yet — expected given §0.3, re-test once the token is in | [x] 2026-08-15 ⚠️ same clean auth failure as macOS: `allow / failed: GitHub authentication failed (GITHUB_TOKEN missing or ...)`, exit non-zero, no traceback (no token on this machine) |
| `request-secret` | SAFE | [x] 2026-08-14 ✅ real prompt, real password-masked value entry, stored + verified in local store (tested with a synthetic dummy value, cleaned up after) | [ ] deferred — needs an interactive session with a real value prompt |
| `restart-pod` | SAFE | [x] 2026-08-14 ✅ real cluster mutation confirmed — pod recreated with new name/reset restart count | [ ] deferred — no cluster on this machine |
| `rollback` | APPROVAL | [x] 2026-08-14 ✅ prompt correct; fails cleanly with "no rollout driver wired to act on it" — this is documented, intentional (PRASH_V2.md §10, 2026-08-09: rollback reads last-known-good but the apply driver is Tier 3, dropped this sprint), not a bug | [ ] deferred — same intentional no-op path, needs interactive prompt |

### 1b. Per action, answer `n` at the prompt — confirm it's actually skipped, nothing executes, audit still logs the decline

| Action | macOS | Windows |
|---|---|---|
| `open-pr` | [x] 2026-08-14 ✅ | [x] 2026-08-16 ✅ piped `n` → "prompt / skipped: declined by user: open-pr", exit 1, nothing executed; audit shows the `prompt/skipped` decline entry |
| `request-secret` | [x] 2026-08-14 ✅ nothing stored on decline | [ ] deferred (needs interactive session) |
| `restart-pod` | [x] 2026-08-14 ✅ pod untouched | [ ] deferred (no cluster) |
| `rollback` | [x] 2026-08-14 ✅ | [ ] deferred (no interactive session / no rollout driver) |

### 1c. Every permission mode (use `restart-pod` as the probe action — SAFE tier, cheapest to test repeatedly)

| `--mode` | Expected behavior | macOS | Windows |
|---|---|---|---|
| `read-only` | Refused outright, no prompt | [x] 2026-08-14 ✅ | [x] 2026-08-16 ✅ `open-pr --mode read-only --noninteractive` → "refuse / skipped: refused by permission engine (safe tier, mode read-only)", no prompt, nothing executed |
| `ask` (default) | Prompts every time | [x] 2026-08-14 ✅ (see 1a) | [x] 2026-08-16 ✅ see §1a/§1b open-pr (prompt appeared, decline honored) |
| `auto-safe` | SAFE tier runs without asking; APPROVAL tier (`rollback`) still prompts | [x] 2026-08-14 ✅ verified both halves with a real (non-dry-run) restart-pod | [x] 2026-08-15 ✅ SAFE-tier half confirmed on Windows via `open-pr --mode auto-safe` reaching execute() without a prompt (clean auth failure, but no gate prompt — proves the no-ask path); APPROVAL half deferred (no interactive session) |
| `environment-scoped` | Auto on `--env staging`; always prompts on `--env production` | [x] 2026-08-14 ✅ | [x] 2026-08-16 ✅ both halves via `--noninteractive`: `--env production` → "prompt / needs_approval: approval required", `--env staging` → "allow / failed" (reached execute, auth failure only) |
| `bypass` | Runs without asking, but still refuses anything in the NEVER tier outright | [x] 2026-08-14 ⚠️ SAFE-tier auto-run confirmed; NEVER-tier refusal not separately re-tested here (no NEVER-tier action currently registered to probe with — see `prash actions`) | [x] 2026-08-16 ⚠️ SAFE-tier auto-run confirmed (`open-pr --mode bypass --noninteractive` → "allow / failed" at auth, no gate); NEVER-tier refusal still not separately probed (no NEVER-tier action registered) |

**Note found while testing:** `--dry-run` bypasses the permission engine's gate entirely, for every mode including `read-only` — it still computes and displays the correct `decision` label (e.g. `refuse`) but always returns `status: succeeded` with a plan. Never touches real infra either way (upholds the flag's own contract), but the terminal output for `--mode read-only --dry-run` literally reads "refuse / succeeded" — self-contradictory to someone scanning output live, even though the audit log's `dry_run: true` field makes the full picture reconstructable. Logged as an open finding below, not fixed yet (low severity — no safety impact, just a confusing label).

### 1d. Flags

| Flag | What to verify | macOS | Windows |
|---|---|---|---|
| `--dry-run` | Produces a plan, **never touches real infrastructure** — confirm nothing actually changed | [x] 2026-08-14 ✅ never mutated the cluster in any dry-run test; see the decision-label note under 1c though | [x] 2026-08-16 ✅ `open-pr acme/widget --dry-run` → "prompt / succeeded: dry-run plan prepared (2 steps)", nothing executed; `--mode read-only --dry-run` read "refuse / skipped: refused by permission engine" (decision label reads consistently on this build — see issue #1 for the historical "refuse / succeeded" reading) |
| `--grant` | **Checklist corrected 2026-08-14** — the code's actual, documented contract (`prash/permissions.py` docstring) is the opposite of what this row used to say: `grant` is meaningless for SAFE tier (mode alone decides), and it's the intended way to pre-approve one APPROVAL-tier action without an interactive prompt. Verified: SAFE tier ignores `--grant` under `ask` mode (still prompts); APPROVAL tier (`rollback --grant`) skips the prompt and runs. | [x] 2026-08-14 ✅ (corrected understanding, not a bug) | [ ] |
| `--noninteractive` | Never prompts; a missing secret returns `NEEDS_INPUT` instead of hanging waiting for input | [x] 2026-08-14 ✅ (needs a mode that lets the action actually reach execute() — `ask` mode alone resolves to `NEEDS_APPROVAL` before ever reaching the secret check, which is correct: noninteractive doesn't force-allow a PROMPT decision, it just removes the interactive channel) | [x] 2026-08-15 ✅ no hang, no crash through the whole circuit-trip run above (auto-safe + noninteractive open-pr → immediate clean auth failure, then clean refusals once tripped) |
| `--secret-name` / `--secret-hint` | `request-secret` picks these up correctly | [x] 2026-08-14 ✅ (see 1a) | [ ] |
| `--head` / `--base` / `--title` / `--body` | `open-pr` uses these correctly, not silently ignored | [x] 2026-08-14 ✅ all four appear correctly in the rendered plan | [ ] |
| `--env staging` vs `--env production` | Actually changes behavior under `environment-scoped` (see 1c) | [x] 2026-08-14 ✅ | [ ] |
| Circuit breaker | Trip it deliberately (exceed `PRASH_CIRCUIT_MAX_ACTIONS` on one resource) — confirm it stops, escalates, and `prash circuit status`/`reset` work | [x] 2026-08-14 ✅ tripped for real at 5 actions/60s on one pod, 6th attempt correctly refused with escalation message, `circuit status` showed OPEN, per-resource `circuit reset <resource>` and global `circuit reset` (no arg) both confirmed clearing it | [x] 2026-08-15 ✅ tripped for real (temp state path, `PRASH_CIRCUIT_MAX_ACTIONS=2`): attempts 1-2 clean auth failures, 3rd refused with "CIRCUIT OPEN — STOP AND ESCALATE TO A HUMAN ... 2 actions in 60s exceeded", `circuit status` showed `OPEN acme/widget`, then per-resource `circuit reset acme/widget` and global `circuit reset` both confirmed clearing it |

**Bug found + fixed 2026-08-14:** a SAFE-tier action that reaches the interactive approval prompt with no stdin available (piped input already exhausted, Ctrl+D, or a script that forgot `--noninteractive`) crashed with an uncaught `EOFError` and a full Python traceback instead of a clean decline. Same defect existed at the `request-secret` value prompt. Fixed in `prash/cli.py` (`CliAsk.ask()` and the `secret_input` closure in `_make_context()`) — both now catch `EOFError`/`KeyboardInterrupt` and treat "no answer available" the same as an explicit "no," consistent with the existing `default="n"` behavior. Regression tests added in `tests/test_cli.py`. 140/140 passing (was 138). Commit: see PRASH_V2.md §10.

---

## 2. `prash fix`

| Case | Command shape | macOS | Windows |
|---|---|---|---|
| Real k8s pod, brain declines (`recommended_action: none`) | `prash fix <ns>/<pod>` on a deterministically-broken pod | [x] 2026-08-15 ✅ real model call against `broken-app`, correctly read the container's actual error message, category=runtime, recommended_action=none, reasoning was accurate (deterministic missing-config failure, restart won't help) | [ ] |
| **Real k8s pod, brain proposes a manifest fix as a PR** | `prash fix <ns>/<pod> --repo <owner/repo>` on a pod broken by a manifest error | [x] 2026-08-16 ✅ **the gap that made every earlier row decline, now closed** (§9). Deployed a realistic broken manifest (`sample-app.yaml`, image tag `nginx:1.27-alpinee`) → real `ImagePullBackOff` → correct diagnosis naming the typo → **real PR #6 opened with a correct one-line diff**, nothing else in the file touched. Closed without merging. This is the exact failure class the old prompt called unfixable-by-machine. | [ ] |
| Real k8s pod, brain recommends `restart_pod` | Same, on a genuinely wedged pod | [x] 2026-08-15 ⚠️ tried, got a confident decline again — new fixture (`prash/connectors/testdata/wedged-pod.yaml`: `sleep infinity` + a `tcpSocket` readiness probe on an unlistened port) reached `StuckPending` cleanly, but the brain correctly read it as a deterministic wrong-image issue (busybox has no HTTP server, so no restart could ever help) and declined — the second fixture in a row to get a well-reasoned decline instead of a restart recommendation. Not a bug; matches the 2026-08-13 finding and the reasoning behind the "ask, don't quit" options-flow decision (§9, 2026-08-14). Getting a live restart_pod recommendation needs either a genuinely-recoverable-by-restart failure (hard to construct reliably) or that options-flow work landing. | [ ] |
| Unknown/missing pod | `prash fix prash-demo/does-not-exist` — clean error, not a stack trace | [x] 2026-08-15 ✅ `pod prash-demo/does-not-exist not found`, exit 2, no traceback | [x] 2026-08-15 ⚠️ no cluster on this machine — fails cleanly at the kube-config layer instead: `pod diagnosis failed: Invalid kube-config file. No configuration found.`, exit 2, **no traceback** (the clean-stop contract holds; the pod-level "not found" itself still needs a cluster to re-verify) |
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
| `prash actions` | Lists all 4 actions with correct risk tier + reversibility | [x] 2026-08-14 ✅ matches action registry exactly | [x] 2026-08-15 ✅ all 5 registered actions (open-pr, request-secret, restart-pod, rollback, apply-ci-fix — `apply-ci-fix` added 2026-08-15, so this row's "all 4" is now 5) with correct tiers + reversibility, matches registry; [x] 2026-08-16 ✅ now **6** with `apply-manifest-fix` (added 2026-08-16) listed with correct tier (SAFE) + reversibility |
| `prash audit` | Shows real entries after the above; `--tail N` actually limits | [x] 2026-08-14 ✅ `--tail 5` returned exactly the 5 most recent real entries | [x] 2026-08-15 ✅ `--tail 5` returned exactly the 5 most recent real entries |
| `prash config` | Secrets shown as redacted, never in plaintext | [x] 2026-08-14 ✅ (see §0.4) | [x] 2026-08-15 ✅ (see §0.4) |
| `prash circuit status` | Shows real breaker state | [x] 2026-08-14 ✅ | [x] 2026-08-15 ✅ `OPEN acme/widget` shown while tripped, `closed` after reset |
| `prash circuit reset` (no resource) | Resets everything | [x] 2026-08-14 ✅ | [x] 2026-08-15 ✅ |
| `prash circuit reset <resource>` | Resets only that resource | [x] 2026-08-14 ✅ | [x] 2026-08-15 ✅ `reset acme/widget` cleared it while another tripped resource stayed open |
| `prash watch` | Detects a real new problem, notifies once, stays silent on repeat polls (§10, already verified once on macOS — re-verify after any watcher changes) | [x] 2026-08-14 ✅ re-verified against a fresh cluster session (see §0.5) | [ ] deferred (no cluster) — no-cluster path verified: clean `watch stopped: Invalid kube-config file. No configuration found.` exit 2, no traceback (the §0.5 fix) |
| `prash watch --namespace` / `--interval` | Both flags actually take effect | [x] 2026-08-14 ✅ `--namespace default` correctly overrode `.env`'s `prash-demo`; `--interval 5` measured at ~5.02s between polls via timestamped output | [ ] deferred (no cluster) — flag plumbing confirmed via the `watch stopped` clean-stop run with `--namespace prash-demo --interval 2` |
| Desktop notification actually fires (not just logged) | **macOS: verified via `osascript` fallback. Windows: never verified live — only mocked. Priority item.** | [x] 2026-08-14 ✅ macOS confirmed: direct `osascript display notification` call exits 0, and no "notification failed" warning appeared in any real watch run today (which would have logged if the fallback failed) | [x] 2026-08-16 ✅ **priority item now closed** — `_send_desktop_notification("prash test", ...)` returned True (real plyer toast fired on this machine), and the full `_notify()` path with a real `PodStatus` ran with no "Desktop notification failed" warning (that only logs if every path failed). One note: `_notify`'s ⚠-prefixed rich line needs UTF-8 stdout on Windows (handled by `prash/ui.py`'s win32 reconfigure; the only failure seen was when bypassing `prash.ui` import) |
| `--env-file` (top-level flag) | Points `prash` at a non-default `.env` location correctly | [x] 2026-08-14 ✅ pointed at an alternate file with a different `KUBE_NAMESPACE` — watcher correctly used the alternate value, not the default `.env` | [x] 2026-08-15 ✅ pointed at a temp alternate `.env` (`KUBE_NAMESPACE=altns`) — `prash config` reported the alternate file as the credentials file and read its keys; `watch` picked up the alternate value path |

---

## 5. Cross-platform specifics (Windows-heavy, but check both)

| Item | macOS | Windows |
|---|---|---|
| Path handling (`pathlib`, not raw string paths) breaks nothing | [x] 2026-08-14 ✅ no path issues across the entire §0/§1/§4/§5 pass; codebase uses `pathlib.Path` consistently, not raw string concatenation | [x] 2026-08-15 ✅ no path issues across the entire Windows pass (install, config, audit, circuit, env-file, temp `.env`/circuit state); `pathlib.Path` used consistently |
| Shell quoting in any subprocess call (`osascript`, `kubectl` via the client lib, `kind`) | [x] 2026-08-14 ✅ `osascript` call uses `subprocess.run([...])` as a list (no `shell=True`, no shell-injection surface) plus its own `_applescript_escape()` for the AppleScript string literal itself — tested directly with a title/message containing embedded `"` and `\` characters, notification still fired correctly, no broken script | [ ] N/A-ish — Windows has no `osascript`; no other subprocess call site introduced in this pass. Re-check the moment any `shell=True`/`cmd /c` call site appears |
| `kind` / Docker Desktop cluster setup works from a clean machine | [x] 2026-08-14 ✅ **actually torn down and rebuilt from scratch** (`kind delete cluster --name prash-dev` → `kind create cluster --name prash-dev`) to verify this for real, not from memory. Node Ready in ~22s, kubectl context auto-set to `kind-prash-dev` exactly as PRASH_V2.md documents, `testdata/broken-pod.yaml` reapplied and reached `CrashLoopBackOff` within ~15s, `prash watch` smoke-tested clean against the fresh cluster immediately after | [ ] deferred — no cluster / no Docker on this machine |
| Line endings don't break `.env` parsing (CRLF vs LF) | [x] 2026-08-14 ✅ built a real CRLF-terminated `.env` file (`\r\n` line endings, matching what a Windows editor would produce) and loaded it through `CredentialStore` directly — `str.splitlines()` already handles CRLF/LF/CR uniformly, confirmed no stray `\r` leaking into any parsed value | [x] 2026-08-15 ✅ same probe on Windows: wrote a real CRLF `.env` (`KUBE_NAMESPACE=prash-demo\r\nKIMI_API_KEY=abc123\r\nVERCEL_TOKEN=\r\n`), loaded through `CredentialStore`, values exact (`prash-demo`/`abc123`), blank value stayed `""`, no stray `\r` |
| Ctrl+C during a running command (`watch`, an in-progress `fix`) exits cleanly, no orphaned process | [x] 2026-08-14 ✅ verified via a direct subprocess + `SIGINT` (not a shell-backgrounded job, which masks SIGINT for background jobs by shell convention and gave a false "hung" reading on the first attempt) — exits cleanly with code 130, prints "interrupted", no orphaned process left behind | [x] 2026-08-15 ⚠️ verified clean-interrupt on the long-running interactive loop (`prash repl`: `CTRL_C_EVENT` → clean exit 0, prints "bye", no traceback, no orphan). The original probe against `prash watch` instead surfaced the §0.5 no-cluster traceback bug — after that fix `watch` exits immediately without a cluster, so watch-specific Ctrl+C still needs a machine with a cluster |

---

## 6. `prash repl` (REPL stage 1, §6b exit criterion #6)

Built by Aryan (`prash/repl.py`), tested on macOS by Aradhya per §6b's "nobody signs off on their own interface" rule.

| Item | macOS | Windows |
|---|---|---|
| Bare `help`/`?` and `exit`/`quit`/`q` | [x] 2026-08-15 ✅ `help` prints full parser usage, session stays alive; `exit` prints "bye" and returns cleanly | [x] built by Aryan on Windows (own commit) |
| A malformed/unknown command | [x] 2026-08-15 ✅ `bogus-garbage-command` → clean argparse "invalid choice" error, session stays alive (does not exit) | [x] |
| Context carried into `fix`: bare pod name resolves against the remembered namespace | [x] 2026-08-15 ✅ live-verified against the real cluster — `fix prash-demo/<pod>` then `fix <pod>` (no namespace) produced the identical real diagnosis both times | [ ] |
| Context carried into `run restart-pod`: bare pod name resolves the same way | [x] 2026-08-15 ✅ live-verified — after establishing context via `fix`, `run restart-pod <pod> --dry-run` (no namespace) correctly resolved and produced a real dry-run plan + audit id | [ ] |
| Context carried into `watch`: no `--namespace` needed if context is set | [x] 2026-08-15 ✅ live-verified — after `fix prash-demo/<pod>`, `watch --interval 5` (no `--namespace`) printed "Watching namespace 'prash-demo'", detected the real broken pod, deduped correctly on repeat polls | [ ] |
| Ctrl+C / Ctrl+D ends the session cleanly, no orphaned process | [x] 2026-08-15 ✅ confirmed no orphaned process after a forced terminate mid-`watch` (`ps aux` clean) | [x] 2026-08-15 ✅ (Aryan, `CTRL_C_EVENT` → clean exit 0, "bye", no traceback — see §5 row above) |

---

## Open issues found during this pass

Track severity/owner in GitHub Issues per `PRASH_V2.md` §0c. List them here too, just as a pointer — don't duplicate the write-up:

| Issue | Severity | Found by | Link |
|---|---|---|---|
| `--dry-run` bypasses the permission engine's REFUSE/PROMPT gate for every mode; terminal output can read e.g. "refuse / succeeded" under `--mode read-only --dry-run` (self-contradictory at a glance, though the audit log's `dry_run: true` field makes it reconstructable). No safety impact — real infra is never touched either way. | P2 | Aradhya, §1c, 2026-08-14 | [#1](https://github.com/Drufiy/prash-v2-backend/issues/1) |
| Kimi fallback's missing-credentials error names `OPENAI_API_KEY`, never `KIMI_API_KEY` — confusing when both the primary model and the fallback fail in the same run. Doesn't crash, correctly excluded that one sub-diagnosis and reported the rest honestly. | P2 | Aradhya, §2, 2026-08-15 | [#5](https://github.com/Drufiy/prash-v2-backend/issues/5) |

**Fixed this pass (2026-08-15, Windows §5 probe):** `prash watch` with no kube-config raised an unhandled `kubernetes` `ConfigException` out of `run_watch_loop` — raw traceback, unlike `fix`'s clean handling of the same condition. `cmd_watch` now catches it and stops cleanly (`watch stopped: Invalid kube-config file. No configuration found.`, exit 2, no traceback). Regression test in `tests/test_cli.py`. Not opened as a GitHub Issue since it was found and fixed in the same sitting — logged in PRASH_V2.md §10.
