# Brain (Diagnosis Engine) — Overview

**Owner:** Aradhya  
**Status:** Core built, domain expansion ongoing  
**Priority:** Tier 1  

---

## Architecture

```
User runs `prash fix` or watcher detects issue
         │
         ▼
┌─────────────────────┐
│  Context Formatter   │  format_k8s_context(), format_aws_context(), etc.
│  (per connector)     │  Converts connector data → structured prompt context
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│  Diagnosis Agent     │  diagnosis_agent.py (~146K, the core IP)
│  (LLM-powered)      │  System prompt + worked examples + tool schema
│                      │  Emits: Diagnosis (single) or options (ambiguous)
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│  Schemas             │  Diagnosis, DiagnosisOption, FileChange, FileEdit
│  (brain/schemas.py)  │  Validated, typed, enforced
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│  Multi-Diagnosis     │  Decompose N independent failures, attempt each
│  (multi_diagnosis.py)│  Report "fixed 3 of 4" as partial success
└─────────────────────┘
```

### Model Client (`kimi_client.py`)
- Primary: DeepSeek v4 Flash
- Fallback: Kimi K2.6 → Gemini 3.5 Flash Lite → Gemini 3.1 Flash Lite
- Call-logging is optional (no Supabase dependency)

### Eval Harness (`evals/run_eval.py`)
- 19 test cases (15 CI + 4 K8s)
- Baseline: `valid_diagnosis` 94.7%, `category_acc` 100%, `file_recall` 1.0
- **Known issue:** `evals/run_eval.py` never loads `.env` — silently depends on shell having model keys exported

---

## Submodule Task Files

1. [`01_DIAGNOSIS_AGENT.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/brain/01_DIAGNOSIS_AGENT.md) — Prompt engineering, new domain support
2. [`02_MULTI_DIAGNOSIS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/brain/02_MULTI_DIAGNOSIS.md) — Multi-failure decomposition
3. [`03_CORRELATION.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/brain/03_CORRELATION.md) — Cross-connector event correlation
4. [`04_SCHEMAS_AND_MODELS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/brain/04_SCHEMAS_AND_MODELS.md) — Data types and model client
