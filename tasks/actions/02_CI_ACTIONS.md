# CI Actions — `apply_ci_fix.py`, `apply_gitlab_ci_fix.py`, `open_pr.py`, `missing_secret.py`

**Owner:** Aryan  
**Status:** Built  
**Priority:** Tier 1  

---

## Existing Actions

| Action ID | File | Risk Tier | Key Design |
|---|---|---|---|
| `apply-ci-fix` | `apply_ci_fix.py` | SAFE | Writes AI-generated code via Git Data API, no local clone |
| `apply-gitlab-ci-fix` | `apply_gitlab_ci_fix.py` | SAFE | Same pattern for GitLab |
| `open-pr` | `open_pr.py` | SAFE | Opens PR between existing branches |
| `request-secret` | `missing_secret.py` | SAFE | Prompts for secret, stores locally, retries failed job |

---

## Tasks

### T1. File-fidelity enforcement
- [ ] `_ApplyFixBase.execute()` fetches real file content before applying edits
- [ ] `FileChange.edits` (exact search/replace) is default for existing files
- [ ] `FileChange.new_content` only for genuinely new files
- [ ] Non-match and non-unique-match both fail loudly

### T2. Multi-failure combined PR
- [ ] `MultiFailureResult.combined_files_changed()` consumed correctly
- [ ] One combined PR per CI run, not one per failure
- [ ] "Fixed X of N" means PRs actually opened, not just proposed

### T3. GitLab CI fix path
- [ ] Phantom multi-diagnosis failure bug (found 2026-08-18) stays fixed
- [ ] GitLab MR creation matches GitHub PR pattern

### T4. `request-secret` flow
- [ ] Prompts user for missing secret value
- [ ] Stores in local `.env` (never uploaded)
- [ ] Retries the failed CI job after storing

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_file_change_apply` | `tests/test_brain_schemas.py` | Edit mechanism |
| `test_combined_pr` | `tests/test_fix.py` | Multi-failure → one PR |
| `test_fixed_count_honest` | `tests/test_fix.py` | "Fixed X of N" accuracy |
| `test_request_secret_flow` | `tests/test_actions.py` | Prompt → store → retry |
| `test_gitlab_ci_fix` | `tests/test_gitlab_connector.py` | GitLab MR creation |

---

## Acceptance Criteria

- [ ] File-fidelity: no unrequested content changes in PRs
- [ ] "Fixed X of N" honestly reflects reality
- [ ] Both GitHub and GitLab CI fix paths work
