# Feature 05 — Service Connection Flow 🟡 PARTIALLY DONE

**Priority:** P0 — credential validation is the trust-building moment  
**Status:** 🟡 **PARTIAL** — backend endpoint works, frontend connection flow works via Wizard, standalone components missing  
**Depends on:** `01_BACKEND_API_BRIDGE.md` ✅, `02_CONNECTOR_REGISTRY.md` ✅  
**Blocks:** `06_SIDEBAR_NAVIGATION.md`, `12_INTEGRATIONS_PAGE.md`

---

## What's Done

- [x] **A1. `POST /api/connectors/{id}/connect`** — exists in `prash/server.py`, calls real `authenticate()`
- [x] **A2. Credential validation before save** — backend saves to `.env` only on success
- [x] **A3. Real provider identity info** on success — returns from backend
- [x] **A4. Real provider error messages** on failure — pass-through from connector
- [x] Connection flow functional via `Wizard.tsx` — dynamic form + submit + feedback

## What's Remaining

### Phase B — Frontend Connection UI (NOT STARTED)
- [ ] **B1. Create `ConnectorForm.tsx`** — standalone reusable form component (currently inlined in Wizard.tsx)
- [ ] **B2. Create `useConnectorStatus` hook** — connection state machine (unconfigured → connecting → connected/failed)
- [ ] **B3. Success state rendering** — show real provider identity info (account ID, username) after connect
- [ ] **B4. Error state rendering** — show EXACT provider error message (Wizard does this, needs extraction)
- [ ] **B5. Loading state rendering** — spinner on button, inputs disabled
- [ ] **B6. Connected info display** — e.g., "AWS Account 123456789012 (us-east-1)"

### Phase C — Credential Management (NOT STARTED)
- [ ] **C1. Implement credential masking** in UI — first 3 + last 3 chars only
- [ ] **C2. Never return full credentials** to the frontend — verify no endpoint leaks secrets
- [ ] **C3. Credential update flow** — masked version with "Update" button
- [ ] **C4. Disconnect flow** — remove credentials from `.env`, stop watches

### Phase D — Reconnection & Health Checks (NOT STARTED)
- [ ] **D1. Periodic health check** — every 60s call `authenticate()` on configured connectors
- [ ] **D2. Expired credential detection** — update status to "expired" with warning
- [ ] **D3. Auto-reconnect** — "Reconnect" button when health check fails

---

## Defects in Current Code

> [!WARNING]
> **The Wizard inlines the connection form logic** instead of using a reusable `ConnectorForm.tsx`. This means the Integrations page can't re-use the form — it currently redirects to the Wizard to connect.

---

## Files Required
- `desktop/src/components/ConnectorForm.tsx` — **NEW** (extract from Wizard)
- `desktop/src/hooks/useConnectorStatus.ts` — **NEW**
