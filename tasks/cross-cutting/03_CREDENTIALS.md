# Credential Management — `credentials.py`, `.env`

**Owner:** Aryan (schema) / Anant (connector-specific handling)  
**Status:** Built  
**Priority:** Tier 1  

---

## Core Principle

**Credentials NEVER leave the user's machine.** This is the foundational trust model (§4 of PRASH_V2.md). Drufiy's servers never receive, store, or see credentials in transit.

---

## Current State

- `.env.example` — schema of all supported keys (owned by Aryan)
- `.env` — gitignored, user's actual credentials
- `credentials.py` — loads `.env`, provides to connectors
- `prash setup` wizard — guided `.env` configuration
- Desktop: credential masking (`mask_credential()` — first 3 + last 3 chars)

---

## Tasks

### T1. Credential loading robustness
- [ ] Blank values don't crash (the 2026-08-14 bug: `KUBECONFIG=` empty)
- [ ] Missing optional connectors gracefully skipped
- [ ] Error messages clearly state WHICH key is missing/invalid
- [ ] No credential value ever appears in logs, audit trail, or error messages

### T2. `.env.example` completeness
- [ ] Every connector's required keys documented
- [ ] Groups: AI Models, Kubernetes, Cloud (AWS/Azure/GCP), CI (GitHub/GitLab), Monitoring (Datadog/Grafana/PagerDuty), Security (Snyk/Gitleaks), Notifications (Slack/Discord/Email/WhatsApp), Deployment (Vercel/Terraform)
- [ ] Comments explain what each key is for
- [ ] `prash setup` parses this automatically

### T3. Desktop credential masking
- [ ] `mask_credential(value)` — `val[:3]...val[-3:]` or `••••••••`
- [ ] Raw secrets NEVER sent to frontend
- [ ] `GET /api/config` returns masked values only
- [ ] `POST /api/connectors/{id}/connect` returns provider identity, not credentials

### T4. Credential validation
- [ ] AWS: STS `get_caller_identity()` — cached per connector instance
- [ ] K8s: kubeconfig load + API server health check
- [ ] GitHub: `GET /user` with token
- [ ] Datadog: `GET /v1/validate` with API key
- [ ] Validate on `prash setup` (where possible) and on `prash watch` startup

### T5. Hosted-mode credential security
- [ ] When Lear runs in a Docker container or K8s pod:
  - Credentials injected via environment variables or mounted secrets
  - `.env` file on a mounted volume (not baked into image)
  - Docker image never contains credentials
  - K8s Secret or AWS Secrets Manager integration

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_blank_env_no_crash` | `tests/test_cli.py` | Empty values handled |
| `test_credential_masking` | `tests/test_service_connections.py` | Masked correctly |
| `test_no_credential_in_logs` | `tests/test_audit.py` | Credentials never in audit |
| `test_aws_auth_cached` | `tests/test_aws_connector.py` | STS not called redundantly |
| `test_env_example_complete` | `tests/test_cli.py` | All connectors have keys |

---

## Acceptance Criteria

- [ ] Credentials NEVER leave the machine
- [ ] Blank/missing values never crash
- [ ] Desktop never sees raw credentials
- [ ] All connectors validate on startup
- [ ] Docker/K8s deployment keeps credentials secure
