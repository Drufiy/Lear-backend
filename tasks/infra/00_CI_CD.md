# CI/CD — GitHub Actions

**Owner:** Aradhya  
**Status:** Working  
**Priority:** Tier 1  

---

## Current State

`.github/workflows/ci.yml` runs lint + tests on Linux, Windows, macOS on every push/PR.
- Main job: 3-OS matrix, mocked tests
- `k8s-live-tests` job: Linux-only, `kind` cluster, 7 live tests
- Lenient: lint warns (doesn't fail), "no tests collected" passes

---

## Tasks

### T1. Tighten CI as codebase matures
- [ ] Lint should fail (not just warn) — codebase is past scaffolding
- [ ] "No tests collected" should fail — every module must have tests
- [ ] Type checking (mypy or pyright) — at least for `prash/connectors/base.py` types

### T2. Expand live test coverage
- [ ] `kind` cluster tests for new connector `watch()`/`get_stats()` methods
- [ ] Fixture deployment: `broken-pod.yaml` + Datadog mock + correlated scenario
- [ ] Timeout tuning: current 300s for CrashLoopBackOff, observed 15-30s locally

### T3. Desktop app CI
- [ ] Frontend: `npm run build` on all 3 OSes (currently verified manually)
- [ ] TypeScript compilation: 0 errors
- [ ] Component tests: `tests/` in desktop

### T4. Test matrix coverage
- [ ] Ensure every test file runs on all 3 OSes
- [ ] Cross-platform path handling tests
- [ ] Console encoding tests (cp1252 for Windows)

---

## Tests

| Test | What it verifies |
|---|---|
| CI matrix | All tests pass on Linux, Windows, macOS |
| `k8s-live-tests` | Live Kind cluster tests pass |
| Desktop build | `npm run build` succeeds |

---

## Acceptance Criteria

- [ ] CI catches real bugs on all 3 OSes
- [ ] No "always green" false confidence
- [ ] Desktop build integrated into CI
