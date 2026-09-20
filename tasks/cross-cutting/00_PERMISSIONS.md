# Permission Engine — `permissions.py`

**Owner:** Aryan  
**Status:** Built (5 modes, 28 tests)  
**Priority:** Tier 1  

---

## Five Permission Modes (mirrors Claude Code)

| Mode | Behavior |
|---|---|
| `read-only` | No actions at all |
| `ask` (default) | Always prompts before any action |
| `auto-safe` | SAFE tier proceeds automatically, APPROVAL tier prompts |
| `environment-scoped` | Auto on staging, always prompts on production |
| `bypass` | For CI/automation; still refuses NEVER-tier unconditionally |

---

## Tasks

### T1. Verify all 29 actions respect permission modes
- [ ] Every action goes through `Dispatcher.run()` → `permissions.check()`
- [ ] No action bypasses the permission system
- [ ] NEVER-tier actions always refused, even in `bypass` mode
- [ ] `--grant` flag works for scripting (overrides prompt)
- [ ] `--noninteractive` + APPROVAL-tier → refuses (no human to ask)

### T2. Options-based permission flow
- [ ] User picks an option from a menu → still goes through permission check
- [ ] Option picking is NOT the same as clearing an APPROVAL gate
- [ ] Picked action checked against its own risk tier independently

### T3. Environment-scoped precision
- [ ] Staging namespace/project → auto-safe
- [ ] Production namespace/project → always ask
- [ ] Environment detection: K8s namespace labels, AWS tags, Vercel project settings
- [ ] Fallback: if environment unknown, treat as production (safe default)

### T4. `--dry-run` handling
- [ ] `--dry-run` produces plan without executing
- [ ] Plan shows what WOULD happen, including permission level
- [ ] Dry run logged in audit as `dry_run=True`

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_read_only_blocks_all` | `tests/test_permissions.py` | No actions in read-only |
| `test_ask_prompts` | `tests/test_permissions.py` | Prompt shown for every action |
| `test_auto_safe_allows_safe` | `tests/test_permissions.py` | SAFE tier proceeds |
| `test_auto_safe_blocks_approval` | `tests/test_permissions.py` | APPROVAL tier prompts |
| `test_bypass_blocks_never` | `tests/test_permissions.py` | NEVER tier always refused |
| `test_environment_scoped` | `tests/test_permissions.py` | Staging auto, prod asks |
| `test_options_permission` | `tests/test_fix.py` | Option pick → permission check |

---

## Acceptance Criteria

- [ ] All 5 modes work correctly for all 29 actions
- [ ] Options flow respects permissions
- [ ] Environment-scoped detection works
- [ ] All 28+ permission tests pass
