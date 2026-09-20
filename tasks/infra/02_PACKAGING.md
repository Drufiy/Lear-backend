# Packaging & Distribution — `setup.py`, `pyproject.toml`

**Owner:** Anant  
**Status:** Partially built (`prash setup` exists)  
**Priority:** Tier 3  

---

## Tasks

### T1. pip packaging
- [ ] `pyproject.toml` properly configured for `pip install prash`
- [ ] Entry point: `prash = prash.cli:main`
- [ ] All dependencies declared (boto3, kubernetes, rich, plyer, etc.)
- [ ] Optional dependency groups: `[aws]`, `[gcp]`, `[azure]`, `[all]`

### T2. `prash setup` wizard hardening
- [ ] Groups all `.env` keys by category
- [ ] Masks secrets during input (terminal history safety)
- [ ] Preserves existing values on skip
- [ ] Validates keys where possible (e.g., AWS STS call)
- [ ] Non-destructive: existing comments and values preserved

### T3. First-run experience
- [ ] `prash` with no config → helpful message pointing to `prash setup`
- [ ] Blank `.env` values don't crash (the 2026-08-14 bug — `KUBECONFIG=` empty)
- [ ] Missing optional connectors gracefully skipped

### T4. Desktop app distribution
- [ ] Tauri build for macOS (`.dmg`)
- [ ] Tauri build for Windows (`.msi`)
- [ ] Auto-start backend `prash/server.py` when desktop opens

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_setup_parses_env_example` | `tests/test_cli.py` | Wizard reads `.env.example` |
| `test_blank_env_no_crash` | `tests/test_cli.py` | Empty values handled |
| `test_first_run_message` | `tests/test_cli.py` | Helpful message shown |
| `test_pip_install` | CI | `pip install .` succeeds |

---

## Acceptance Criteria

- [ ] `pip install prash` works
- [ ] `prash setup` → `prash watch` works in < 5 minutes
- [ ] Blank/missing config never crashes
