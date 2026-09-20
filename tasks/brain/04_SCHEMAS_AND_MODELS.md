# Schemas & Model Client — `brain/schemas.py`, `brain/kimi_client.py`

**Owner:** Aradhya (schemas) / Aryan (model client integration)  
**Status:** Built  
**Priority:** Tier 1  

---

## Schemas (`brain/schemas.py`)

### Core Types

| Type | Purpose | Key Fields |
|---|---|---|
| `Diagnosis` | Single diagnosis result | `category`, `explanation`, `confidence`, `recommended_action`, `files_changed`, `options` |
| `DiagnosisOption` | Ranked option for ambiguous cases | `action`, `rationale`, `is_default` |
| `FileChange` | A proposed file modification | `path`, `edits` (for existing), `new_content` (for new) |
| `FileEdit` | Exact search/replace edit | `old_content`, `new_content` (exact substring match) |
| `MultiFailureResult` | N independent failures | `diagnoses`, `fixed_count`, `combined_files_changed()` |

### Tasks

#### T1. Validate schema robustness
- [ ] `Diagnosis.options` must have 2+ entries (anti-crutch guard)
- [ ] `Diagnosis.options` must have exactly one `is_default`
- [ ] `recommended_action` auto-derived from default option when unset
- [ ] `FileChange`: exactly one of `edits`/`new_content` (never both, never neither)
- [ ] `FileEdit.old_content` must match file exactly and uniquely

#### T2. Add `ConnectorEvent` integration
- [ ] `Diagnosis` can reference which `ConnectorEvent`s contributed to it
- [ ] Provenance tracking: "this diagnosis was informed by events from K8s + Datadog"

#### T3. Category enum expansion
- [ ] Add new categories as brain domain expands (see `01_DIAGNOSIS_AGENT.md`)
- [ ] Backward compatible: old categories still valid

---

## Model Client (`brain/kimi_client.py`)

### Current State
- Primary: DeepSeek v4 Flash
- Fallback chain: Kimi K2.6 → Gemini 3.5 Flash Lite → Gemini 3.1 Flash Lite
- Call-logging is optional (no Supabase dependency)
- 41K file

### Tasks

#### T4. Model selection configurability
- [ ] `prash.yaml` or `.env` configurable: `AI_MODEL=deepseek-v4-flash`
- [ ] Desktop Settings page reflects chosen model
- [ ] Fallback chain configurable: which models, in which order

#### T5. Rate limiting & cost tracking
- [ ] Token usage logged per diagnosis call
- [ ] Rate limiting to prevent runaway costs in autopilot mode
- [ ] Monthly usage summary in audit log

#### T6. Streaming support for desktop Copilot
- [ ] SSE streaming endpoint (`POST /api/chat/stream`) uses model client
- [ ] Progressive token delivery for real-time reasoning display

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_diagnosis_options_validation` | `tests/test_brain_schemas.py` | 2+ options, one default |
| `test_auto_derive_recommended` | `tests/test_brain_schemas.py` | Auto-derive from default option |
| `test_file_change_mutual_exclusion` | `tests/test_brain_schemas.py` | Can't set both edits and new_content |
| `test_file_edit_exact_match` | `tests/test_brain_schemas.py` | old_content must match exactly |
| `test_model_fallback_chain` | `tests/test_brain_kimi_client.py` | Fallback to Kimi/Gemini works |
| `test_model_configurable` | `tests/test_brain_kimi_client.py` | `.env` model selection respected |

---

## Acceptance Criteria

- [ ] All schema validations enforced
- [ ] Model client supports configuration and fallback
- [ ] Streaming works for desktop Copilot
- [ ] All existing schema tests pass (16+ in `test_brain_schemas.py`)
