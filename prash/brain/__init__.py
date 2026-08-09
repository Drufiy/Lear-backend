"""Track D — the diagnosis brain. Owner: Aradhya. See PRASH_V2.md §6.

This package doesn't exist yet on purpose — it's where
`diagnosis_agent.py`, `log_fetcher.py`, and `schemas.py` get ported
from `prash-backend` (days 1-2), stripped of Supabase coupling.

Order matters: port `prash-backend/evals/` FIRST (day 1) and get a
baseline running against the unmodified v1 brain, before this package
has any real content. Days 4-8 extend the `Diagnosis` schema with
runtime categories and teach the prompt Kubernetes (it currently has
zero runtime references — see PRASH_V2.md §9, 2026-08-09 second
review). Re-run the eval baseline after that work, not just before it.
"""
