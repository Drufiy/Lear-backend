# Feature 05 — Service Connection Flow

**Priority:** P0 — credential validation is the trust-building moment  
**Owner:** TBD  
**Depends on:** `01_BACKEND_API_BRIDGE.md`, `02_CONNECTOR_REGISTRY.md`  
**Target files:**  
- `prash/server.py` — connection endpoints  
- `desktop/src/components/ConnectorForm.tsx` (new)  
- `desktop/src/hooks/useConnectorStatus.ts` (new)  
**Test file:** `tests/test_service_connections.py` (new), `desktop/src/__tests__/ConnectorForm.test.tsx` (new)

---

## Product Spec

The Service Connection Flow is the exact sequence from "user enters credentials" to "service is verified and live." This is the **trust-building moment** — the user is giving Lear their cloud API keys. Every step must be transparent, real, and honest.

### What Happens When You Click "Connect"

```
User enters credentials in the form
    │
    ▼
Frontend sends POST /api/connectors/{id}/connect
    │
    ▼
Backend receives credentials
    │
    ├─► Saves to .env via dotenv.set_key()
    │
    ├─► Instantiates the connector class
    │
    ├─► Calls connector.authenticate()
    │       │
    │       ├─► AWS: STS get_caller_identity()
    │       ├─► GitHub: GET /user with token
    │       ├─► GCP: google.auth.default() + list instances
    │       ├─► Azure: ClientSecretCredential + list VMs
    │       ├─► K8s: list namespaces with kubeconfig
    │       ├─► Datadog: validate API key endpoint
    │       ├─► etc.
    │       │
    │       ▼
    │   Returns True/False
    │
    ▼
Backend returns {success: bool, message: str}
    │
    ├─► success: true  → "AWS STS authentication successful! Account: 123456789012"
    │                     (real account info, not generic)
    │
    └─► success: false → "InvalidClientTokenId: The security token included in 
                          the request is invalid." (REAL provider error)
```

### Authentication Methods Per Connector

| Connector | Auth Method | Verification Call | Success Detail |
|---|---|---|---|
| AWS | STS `get_caller_identity()` | Boto3 STS call | Account ID, ARN |
| Azure | `ClientSecretCredential` | List resource groups | Subscription name |
| GCP | Service account JSON | List projects | Project name |
| K8s | Kubeconfig + context | List namespaces | Cluster name, namespace count |
| Vercel | Bearer token | `GET /v1/user` | Username, team name |
| GitHub | PAT | `GET /user` | Username, scopes |
| GitLab | PAT | `GET /api/v4/user` | Username, instance URL |
| Datadog | API key + App key | `GET /api/v1/validate` | Valid/Invalid |
| Grafana | API key | `GET /api/org` | Org name |
| PagerDuty | REST API key | `GET /users/me` | User name, email |
| Snyk | Auth token | `GET /rest/self` | Org name |
| Gitleaks | Local binary | `gitleaks version` | Version string |
| Terraform | Local state | Check `.tfstate` exists | Resource count |

### Security Rules

1. **Credentials saved to `.env` ONLY** — never in memory longer than the request, never logged
2. **Masked in API responses** — `GET /api/config` shows `"AKI...789"` not the full key
3. **No credential round-trip** — frontend sends credentials once, backend saves them, frontend never receives them back
4. **No credential in URL params** — always in POST body
5. **Validation before save** — if `authenticate()` fails, credentials are NOT saved to `.env`

### Connection State Machine

```
UNCONFIGURED ──[user enters creds]──► CONNECTING
                                          │
                        ┌─────────────────┤
                        │                 │
                        ▼                 ▼
                    CONNECTED          FAILED
                        │                 │
                        │     [user retries]
                        │                 │
                        ▼                 ▼
                    WATCHING         CONNECTING
```

---

## Detailed Task List

### Phase A — Backend Connection Endpoints

- [ ] **A1. Implement `POST /api/connectors/{id}/connect`** with real authentication per connector:
  - [ ] AWS: Create `AWSConnector`, call `authenticate()`, return account ID on success
  - [ ] Azure: Create `AzureConnector`, call `authenticate()`, return subscription info
  - [ ] GCP: Create `GCPConnector`, call `authenticate()`, return project info
  - [ ] K8s: Create `KubernetesConnector`, call `authenticate()`, return cluster info
  - [ ] Vercel: Create `VercelConnector`, call `authenticate()`, return user info
  - [ ] GitHub: Validate PAT against `GET /user`, return username and scopes
  - [ ] GitLab: Validate token against `GET /api/v4/user`, return username
  - [ ] Datadog: Validate API key, return validation status
  - [ ] Grafana: Validate API key against org endpoint, return org name
  - [ ] PagerDuty: Validate key against users/me, return user info
  - [ ] Snyk: Validate token, return org name
  - [ ] Gitleaks: Check binary exists and runs, return version
  - [ ] Terraform: Check state file exists, return resource count

- [ ] **A2. Credential validation BEFORE save** — only write to `.env` after `authenticate()` returns True
- [ ] **A3. Return real provider identity info** on success — account IDs, usernames, org names (proves it's real)
- [ ] **A4. Return real provider error messages** on failure — pass through the exception message

### Phase B — Frontend Connection UI

- [ ] **B1. Create `ConnectorForm.tsx`** — generic form component that renders from registry auth_fields
- [ ] **B2. Create `useConnectorStatus` hook** — manages connection state machine (unconfigured → connecting → connected/failed)
- [ ] **B3. Success state rendering** — green glow, ✅ icon, show real provider identity info (account ID, username)
- [ ] **B4. Error state rendering** — red border, ❌ icon, show EXACT provider error message
- [ ] **B5. Loading state rendering** — spinner on button, inputs disabled, cancel not available
- [ ] **B6. Connected info display** — after successful connection, show what was connected (e.g., "AWS Account 123456789012 (us-east-1)")

### Phase C — Credential Management

- [ ] **C1. Implement credential masking** in `GET /api/config` — first 3 + last 3 chars only
- [ ] **C2. Never return full credentials** to the frontend — verify no endpoint leaks secrets
- [ ] **C3. Credential update flow** — if credentials already exist, show masked version with "Update" button
- [ ] **C4. Disconnect flow** — remove credentials from `.env`, stop any active watches

### Phase D — Reconnection & Health Checks

- [ ] **D1. Periodic health check** — every 60 seconds, call `authenticate()` on configured connectors to verify credentials still valid
- [ ] **D2. Expired credential detection** — if `authenticate()` starts failing, update status to "expired" and show warning
- [ ] **D3. Auto-reconnect** — if a connector was connected but health check fails, show "Reconnect" button (not auto-reconnect with bad creds)

---

## Testing Methodology

### Unit Tests

```
test_connect_aws_calls_sts_get_caller_identity
test_connect_aws_returns_account_id_on_success
test_connect_aws_returns_real_error_on_bad_keys
test_connect_aws_saves_to_dotenv_on_success
test_connect_aws_does_NOT_save_to_dotenv_on_failure
test_connect_github_calls_get_user
test_connect_github_returns_username_on_success
test_connect_github_returns_401_error_on_bad_token
test_connect_unknown_connector_returns_404
test_config_get_masks_all_secrets
test_config_get_never_returns_full_key
test_disconnect_removes_from_dotenv
test_health_check_detects_expired_credentials
```

### Anti-Hardcoding Test Suite

```
test_NO_HARDCODED_CONNECTION_LOGIC — The connect endpoint does NOT 
    contain a giant if/elif chain for each connector. Connection logic 
    uses the registry's connector_class to instantiate and call 
    authenticate() generically.

test_NO_SIMULATED_AUTH — When credentials are invalid, the backend 
    returns the REAL error from the cloud provider, not a canned 
    response like "Invalid credentials". Verify by sending garbage 
    credentials to each configured connector and checking the error 
    message contains provider-specific text (e.g., "InvalidClientTokenId" 
    for AWS, "Bad credentials" for GitHub).

test_NO_HARDCODED_ACCOUNT_INFO — The success response's detail (account 
    ID, username, etc.) comes from the actual API response, not from a 
    hardcoded string. Verify by connecting the same connector twice with 
    different credentials and checking the detail changes.

test_CREDENTIAL_NEVER_IN_RESPONSE — Parse every API response for 
    patterns matching AWS keys (AKIA...), GitHub tokens (ghp_...), 
    etc. None must appear unmasked.

test_NO_FAKE_SUCCESS — If authenticate() returns False, the connect 
    endpoint MUST return {success: false}. Never override with a 
    simulated success.

test_CONNECTION_GENERIC — The connect endpoint works identically for 
    a brand-new connector registered at test time. No connector-specific 
    branching.
```

### Integration Tests

```
test_FULL_CONNECTION_FLOW_AWS — With real AWS test credentials (from 
    .env.test): enter creds → connect → verify status shows "healthy" 
    → verify config shows masked key

test_CONNECT_DISCONNECT_RECONNECT — Connect → verify → disconnect → 
    verify status "unconfigured" → reconnect → verify status "healthy"

test_BAD_CREDENTIALS_FLOW — Enter invalid credentials → verify 
    error message is from provider → correct credentials → verify 
    success
```

---

## Definition of Done

- [ ] All 13 connectors can be connected via `POST /api/connectors/{id}/connect`
- [ ] Every connection calls the REAL provider `authenticate()` method
- [ ] Success responses include real provider identity info (account IDs, usernames)
- [ ] Error responses include real provider error messages
- [ ] Credentials only saved to `.env` after successful authentication
- [ ] Credentials never returned unmasked to the frontend
- [ ] Health checks detect expired/revoked credentials
- [ ] Anti-hardcoding tests all pass
