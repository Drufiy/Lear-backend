# REPL & Intent Parsing — `repl.py`, `intent.py`

**Owner:** Aryan  
**Status:** Stage 1 + 2 done  
**Priority:** Tier 2 (hardening)  

---

## Current State

- **Stage 1 (done):** Persistent interactive session, no re-typing `prash` per command, context (namespace, last-diagnosed pod) carried between commands, rich live output
- **Stage 2 (done):** Free text → intent parsing ("my api pod is sick, fix it" → `fix prash-demo/api-...`), clarifying follow-ups when ambiguous

---

## Tasks

### T1. REPL session management
- [ ] Context persistence across commands (namespace, last pod, last connector)
- [ ] Session history (up-arrow recall)
- [ ] Clean exit on Ctrl+D / Ctrl+C / `exit` / `quit`
- [ ] No stale state after failed commands

### T2. Intent parsing depth
- [ ] Map natural language to CLI commands:
  - "restart the api pod" → `run restart-pod prash-demo/api-xyz`
  - "what's wrong with my k8s cluster" → `investigate default/`
  - "check the datadog monitors" → `investigate --provider datadog`
  - "scale api to 5 replicas" → `run scale prash-demo/api --replicas 5`
  - "show me the audit log" → `audit`
- [ ] Clarifying questions for ambiguous input
- [ ] `@connector` mention support: "@kubernetes what pods are failing"

### T3. Multi-step conversational flow
- [ ] Diagnosis → "want me to fix it?" → approve → execute → verify → report
- [ ] Options presentation → user picks → dispatch → verify
- [ ] Follow-up questions preserve context

### T4. Cross-platform REPL testing
- [ ] Windows PowerShell: keyboard handling, ANSI colors, signal handling
- [ ] macOS Terminal: same
- [ ] Linux: same
- [ ] Verified by Aradhya on macOS, Aryan on Windows (§6b rule)

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_repl_session_context` | `tests/test_repl.py` | Context persists between commands |
| `test_repl_clean_exit` | `tests/test_repl.py` | Ctrl+C/D exits cleanly |
| `test_intent_fix` | `tests/test_intent.py` | "fix the api pod" → correct command |
| `test_intent_ambiguous` | `tests/test_intent.py` | Ambiguous input → clarification |
| `test_intent_connector_mention` | `tests/test_intent.py` | @kubernetes routing |

---

## Acceptance Criteria

- [ ] REPL works on both Windows and macOS
- [ ] Intent parsing covers all registered commands
- [ ] Multi-step conversational flow works
- [ ] All 19K+ of intent tests pass, all 5K+ of REPL tests pass
