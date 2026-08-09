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

Scaffolding only as of this commit. Aryan has working local progress on
Track A/C (action registry, permission-mode engine, dry-run execution) not
yet pushed — see the decision log in `PRASH_V2.md` for the latest state.
