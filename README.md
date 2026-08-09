# Prash v2 — the AI DevOps agent

A local-first agent that watches your infrastructure — CI, cloud, Kubernetes,
deployments — and acts on what it finds, not just diagnoses it. Credentials
stay in your own environment; nothing is uploaded to Drufiy's servers.

This is the ground-up rebuild. The original hosted CI-repair service
([`prash-backend`](https://github.com/Drufiy/prash-backend)) stays live and
unmodified at prash.drufiy.com — it is not being replaced by this repo, at
least not in the current sprint.

**Start here: [`PRASH_V2.md`](./PRASH_V2.md).** It is the single source of
truth for this project — architecture, task division, decisions, open
questions, and the running bug/idea log. If something isn't in that file,
treat it as undecided, not assumed.

## Who's building this

- **Aryan** (CTO) — Track A (CLI spine & permission engine) + Track C (write actions)
- **Aradhya** (founder) — Track B (read connectors) + Track D (diagnosis brain + multi-failure fix)

Full task breakdown, day by day, is in `PRASH_V2.md` section 6.

## Status

Track A + C are landed on `main`: the `prash` CLI spine, five-mode permission
engine, append-only audit log, and the `open-pr`, `request-secret`,
`restart-pod`, and `rollback` actions (28 tests passing). Track B (`k8s`
connector stubs) and Track D scaffolding are on `main` too. `restart-pod` and
`rollback` are wired to Track B's connector stubs and report honestly until the
real drivers land. See `PRASH_V2.md` for the decision log and current state.
