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
| 0.1 | Fresh `git clone`, fresh venv, `pip install -e ".[dev]"` — no errors | [ ] | [ ] |
| 0.2 | `prash` (bare console script) resolves and runs — not `python -m prash.cli` | [ ] | [ ] |
| 0.3 | `cp .env.example .env`, fill in only `KIMI_API_KEY` (or `DEEPSEEK_API_KEY`) + `KUBE_CONTEXT`, leave everything else blank exactly as shipped | [ ] | [ ] |
| 0.4 | `prash config` — runs clean, no crash, secrets shown as redacted not blank/error | [ ] | [ ] |
| 0.5 | `prash watch` against a real (or `kind`) cluster — no `ConfigException`, no crash from any other blank `.env` field | [ ] | [ ] |

---

## 1. `prash run <action> <resource>`

### 1a. Per action, default `ask` mode (answer `y`)

| Action | Risk tier | macOS | Windows |
|---|---|---|---|
| `open-pr` | SAFE | [ ] | [ ] |
| `request-secret` | SAFE | [ ] | [ ] |
| `restart-pod` | SAFE | [ ] | [ ] |
| `rollback` | APPROVAL | [ ] | [ ] |

### 1b. Per action, answer `n` at the prompt — confirm it's actually skipped, nothing executes, audit still logs the decline

| Action | macOS | Windows |
|---|---|---|
| `open-pr` | [ ] | [ ] |
| `request-secret` | [ ] | [ ] |
| `restart-pod` | [ ] | [ ] |
| `rollback` | [ ] | [ ] |

### 1c. Every permission mode (use `restart-pod` as the probe action — SAFE tier, cheapest to test repeatedly)

| `--mode` | Expected behavior | macOS | Windows |
|---|---|---|---|
| `read-only` | Refused outright, no prompt | [ ] | [ ] |
| `ask` (default) | Prompts every time | [ ] | [ ] |
| `auto-safe` | SAFE tier runs without asking; APPROVAL tier (`rollback`) still prompts | [ ] | [ ] |
| `environment-scoped` | Auto on `--env staging`; always prompts on `--env production` | [ ] | [ ] |
| `bypass` | Runs without asking, but still refuses anything in the NEVER tier outright | [ ] | [ ] |

### 1d. Flags

| Flag | What to verify | macOS | Windows |
|---|---|---|---|
| `--dry-run` | Produces a plan, **never touches real infrastructure** — confirm nothing actually changed | [ ] | [ ] |
| `--grant` | Pre-grants a SAFE action; an APPROVAL-tier action still prompts even with `--grant` | [ ] | [ ] |
| `--noninteractive` | Never prompts; a missing secret returns `NEEDS_INPUT` instead of hanging waiting for input | [ ] | [ ] |
| `--secret-name` / `--secret-hint` | `request-secret` picks these up correctly | [ ] | [ ] |
| `--head` / `--base` / `--title` / `--body` | `open-pr` uses these correctly, not silently ignored | [ ] | [ ] |
| `--env staging` vs `--env production` | Actually changes behavior under `environment-scoped` (see 1c) | [ ] | [ ] |
| Circuit breaker | Trip it deliberately (exceed `PRASH_CIRCUIT_MAX_ACTIONS` on one resource) — confirm it stops, escalates, and `prash circuit status`/`reset` work | [ ] | [ ] |

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
| | | | |
