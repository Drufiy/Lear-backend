# Lear — the AI DevOps agent

A local-first agent that watches your infrastructure — CI, Kubernetes, deployments —
and **acts** on what it finds, not just diagnoses it. Credentials stay in your own
environment; nothing is uploaded to Drufiy's servers.

This is the ground-up rebuild. The original hosted CI-repair service
([`prash-backend`](https://github.com/Drufiy/prash-backend)) stays live and unmodified
at prash.drufiy.com — this repo is not replacing it in the current sprint.

**Read [`PRASH_V2.md`](./PRASH_V2.md) before writing any code.** It is the single source
of truth — architecture, task division, decisions, and the running bug/idea log. If
something isn't in that file, treat it as undecided, not assumed.

---

## Setup

Requires **Python 3.10+**. Takes about two minutes.

```bash
git clone https://github.com/Drufiy/prashv2backend.git
cd prashv2backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Confirm the `prash` command resolved:

```bash
prash --help
```

Then create your local config from the template:

```bash
cp .env.example .env
```

Open `.env` and fill in **one model key** — either `DEEPSEEK_API_KEY` or
`KIMI_API_KEY`. Everything else can stay blank to start. `.env` is gitignored and
never leaves your machine.

> **Read this before you edit `.env`.** Leave unused keys *completely blank*
> (`KUBECONFIG=`), never a placeholder like `KUBECONFIG=none`. Prash treats a blank
> value as "not configured" and falls back to the sensible default; a placeholder is
> taken literally and will break in confusing ways. This exact thing broke the very
> first real install (`PRASH_V2.md` §10, 2026-08-14).

Check it loaded — this never prints secret values, only which keys it found:

```bash
prash config
```

Run the test suite (should be **182 passed, 7 skipped** — the skips are live-cluster
tests that only run in CI):

```bash
pytest -q
```

That's enough to develop against. Everything below is only needed for the
Kubernetes features.

---

## Optional: a local Kubernetes cluster

Needed for `prash fix`, `prash watch`, and `restart-pod`. Requires Docker Desktop
running, plus [`kind`](https://kind.sigs.k8s.io) and `kubectl`
(`brew install kind kubectl` on macOS).

```bash
kind create cluster --name prash-dev
kubectl apply -f prash/connectors/testdata/broken-pod.yaml
```

`kind` sets your kubectl context automatically. Put these in `.env`:

```
KUBE_CONTEXT=kind-prash-dev
KUBE_NAMESPACE=prash-demo
```

The fixture pod reaches a real `CrashLoopBackOff` in about 15 seconds — verify with
`kubectl get pods -n prash-demo`. Tear it all down with
`kind delete cluster --name prash-dev`.

---

## Trying it

```bash
prash repl                    # persistent session — best place to start
prash actions                 # every action, with its risk tier
prash config                  # local config, secrets redacted
prash tui                     # dashboard-style terminal UI
```

Once a cluster is up:

```bash
prash watch                                    # poll for broken pods, notify on new ones
prash fix prash-demo/<pod-name>                # diagnose a pod, act on the verdict
prash fix prash-demo/<pod-name> --repo <owner/repo>   # ...and propose a manifest fix as a PR
```

For CI failures:

```bash
prash fix <owner>/<repo> --ci --run-id <n>     # needs GITHUB_TOKEN
```

**Safety, worth knowing before you run anything:** every action goes through a
permission engine (`read-only` / `ask` / `auto-safe` / `environment-scoped` /
`bypass`, default `ask`), a circuit breaker that halts repeated action on one
resource, and an append-only audit log (`prash audit`). Add `--dry-run` to any
command to see the plan without touching anything real.

---

## The commands

| Command | What it does |
|---|---|
| `prash repl` | Persistent interactive session; remembers namespace/pod between commands |
| `prash tui` | Dashboard-style terminal UI |
| `prash fix` | Diagnose a k8s pod or CI run, then run the recommended action through the permission pipeline |
| `prash run <action> <resource>` | Execute one action directly |
| `prash watch` | Poll a namespace, notify on newly broken pods |
| `prash investigate <resource>` | Read-only connector probe |
| `prash actions` | List registered actions and risk tiers |
| `prash audit` | Show the append-only audit log |
| `prash config` | Show local config (secrets redacted) |
| `prash circuit` | Inspect or reset the circuit breaker |

Run `prash <command> --help` for flags — that output is generated from the real
parser, so it's never out of date.

---

## Who's building this

- **Aradhya** (founder) — read connectors, diagnosis brain, the watcher
- **Aryan** (CTO) — CLI spine, permission engine, write actions, REPL/TUI
- **Anant** — onboarding & packaging, AWS
- **Maneesh** — distribution, marketing, fundraising (development as needed)

Day-by-day breakdown in `PRASH_V2.md` §6 and §6b.

---

## Status

Working end to end today: the `prash` CLI and REPL, a five-mode permission engine,
circuit breaker and audit log, a real Kubernetes connector (status/logs/events/restart),
the diagnosis brain with a golden-case eval harness, the background watcher, and six
actions — `open-pr`, `request-secret`, `restart-pod`, `rollback`, `apply-ci-fix`,
`apply-manifest-fix`.

Both fix paths are **live-verified against real infrastructure**, not mocks: a real CI
failure and a real broken Kubernetes manifest each produced a real pull request with a
correct diff.

Currently in a **hardening phase** (`PRASH_V2.md` §6b) — real-user testing on both macOS
and Windows before any new platform work starts. 182 tests passing. Known gaps and open
questions are tracked honestly in `PRASH_V2.md` §9/§10 and in GitHub Issues.
