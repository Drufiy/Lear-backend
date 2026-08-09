# Prash Eval Harness — Golden Benchmark

Ported from `prash-backend/evals/` (2026-08-09, Track D day 3). A reproducible
benchmark built from real production runs. Use it to gate every prompt / model /
schema change to the diagnosis brain: run before and after, compare scorecards.

## Why this exists

Track D (days 4-8) extends the `Diagnosis` schema with runtime categories and
teaches the brain Kubernetes — a domain it has never seen (69 CI-specific
references in the prompt, zero runtime ones). Without this harness there is no
way to tell whether that work made CI diagnosis quality better, worse, or just
different. Every change to `prash/brain/` gets run through this before it's
considered done.

## Layout

```
evals/
  cases/            # golden cases (one JSON per run), ported from v1 verbatim
  score.py          # scoring rubric + scorecard rendering (zero external deps)
  run_eval.py       # replay cases through diagnose_failure(), score, write results
  results/          # scorecards per run (gitignored, except the baseline below)
```

## The pre-Track-D baseline

`results/2026-08-09-pre-track-d-port-baseline.json` was captured against the
**unmodified v1 brain** (still running in `prash-backend`, not yet ported here),
model `deepseek-v4-flash`, on 2026-08-09 — before any Track D schema/prompt
changes. 15/15 cases, 100% valid_diagnosis, 100% category accuracy, 93.3%
actionability, 86.7% fix_type accuracy, file_recall 1.0. Diff every future run
against this to catch regressions from the schema extension and Kubernetes
prompt work:

```bash
python -m evals.run_eval --baseline evals/results/2026-08-09-pre-track-d-port-baseline.json
```

## Not runnable yet

`run_eval.py` imports `prash.brain.diagnosis_agent` / `prash.brain.kimi_client`,
which don't exist until Track D days 4-5 port the brain (see `PRASH_V2.md` §6).
Ported now, checked in, and wired to the right import paths so it's ready to run
the moment the brain lands — porting the harness twice would be wasted work.

## What did NOT get ported

`seed_from_db.py` — it pulls new golden cases from v1's Supabase, and v2 has no
database by design (§4). Cases are portable data (just JSON), so they moved over;
the seeding mechanism stays a v1-only operational tool. To add a new case here,
either hand-author one (see v1's `evals/README.md` for the exact JSON shape) or
run v1's `seed_from_db.py` there and copy the resulting file into `evals/cases/`.

## Running

```bash
# full run against the ported brain, once Track D lands it
python -m evals.run_eval

# quick smoke (2 cases)
python -m evals.run_eval --limit 2

# compare against the pre-port baseline
python -m evals.run_eval --baseline evals/results/2026-08-09-pre-track-d-port-baseline.json
```

By default the harness runs the **single-shot path** (files supplied in-prompt,
no GitHub calls) — reproducible and isolates model + prompt + schema quality.
`--live` adds the real investigation loop, matching how `prash fix` actually
runs, but needs `GH_TOKEN`.

`agent_calls`-equivalent logging is monkeypatched to a no-op before import, so
eval runs never write to anywhere persistent.

## Known limitations (inherited from v1, still true here)

1. **Category coverage is biased.** The golden set only has ground truth for
   `code` and `dependency` (13 of 15 cases) plus one `workflow_config` case.
   `environment` has zero cases. This harness cannot yet measure whether the
   Kubernetes work (a brand-new category Track D is adding) is any good —
   **hand-authoring `environment`/runtime-category cases is part of days 6-8,
   not optional polish.**
2. **~60-70% of v1's production traffic was internal smoke testing** (per v1's
   README) — the case set reflects that skew.
3. **Single-shot ≠ the real `prash fix` path**, which runs the full investigation
   loop. Use `--live` periodically to catch loop-specific regressions.
