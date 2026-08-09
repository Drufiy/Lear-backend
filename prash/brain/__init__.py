"""Track D — the diagnosis brain. Owner: Aradhya. See PRASH_V2.md §6.

Ported from prash-backend/app/agent/ on 2026-08-09 (days 4-5): diagnosis_agent.py,
schemas.py (extended with a "runtime" category + recommended_action field for
Kubernetes), log_fetcher.py, kimi_client.py (Supabase logging replaced with local
logging; client construction made lazy — see kimi_client.py's docstring), and
repo_memory.py (pure formatting only, DB-backed builder dropped — v2 has no DB).

The SYSTEM_PROMPT in diagnosis_agent.py is still entirely CI-shaped — it has never
seen a Kubernetes failure. Teaching it that is Track D days 6-8, not done yet.
"""
