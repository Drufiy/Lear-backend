# Infrastructure Actions — Terraform & Vercel

**Owner:** Anant  
**Status:** Built  
**Priority:** Tier 3  

---

## Existing Actions

| Action ID | File | Risk Tier |
|---|---|---|
| `terraform-init` | `terraform_init.py` | SAFE |
| `terraform-apply` | `terraform_apply.py` | APPROVAL (dynamic) |
| `vercel-redeploy` | `vercel_deploy.py` | SAFE |
| `vercel-rollback` | `vercel_deploy.py` | APPROVAL |

---

## Tasks

### T1. Wire into watcher loop
- [ ] Terraform drift detected → brain → `terraform-apply` recommended (APPROVAL)
- [ ] Vercel deploy failed → brain → `vercel-redeploy` or `vercel-rollback` recommended

### T2. Terraform-apply dynamic risk tier
- [ ] Default APPROVAL, but configurable per workspace
- [ ] `terraform plan` output included in approval prompt so user sees what will change
- [ ] Verify: `terraform plan` shows no drift after apply

### T3. Vercel rollback safety
- [ ] `get_previous_revision()` called to find rollback target
- [ ] Verify: deployment is healthy after rollback

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_terraform_apply_approval` | `tests/test_actions.py` | APPROVAL enforced |
| `test_terraform_missing_state` | `tests/test_terraform_connector.py` | Graceful degradation |
| `test_vercel_rollback_verify` | `tests/test_actions.py` | Post-rollback health check |

---

## Acceptance Criteria

- [ ] Both Terraform and Vercel actions wired into watcher loop
- [ ] `terraform-apply` shows plan in approval prompt
- [ ] Missing `.tfstate` handled gracefully
