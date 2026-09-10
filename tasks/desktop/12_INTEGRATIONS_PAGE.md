# Feature 12 — Integrations Management Page

**Priority:** P1 — post-setup connector management  
**Owner:** TBD  
**Depends on:** `02_CONNECTOR_REGISTRY.md`, `05_SERVICE_CONNECTIONS.md`  
**Target file:** [`desktop/src/components/Integrations.tsx`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/desktop/src/components/Integrations.tsx) (rewrite)  
**Test file:** `desktop/src/__tests__/Integrations.test.tsx` (new)

---

## Product Spec

The Integrations page is where users manage their connected services AFTER initial setup. View all 13 connectors, connect new ones, reconfigure existing ones, and see connection health at a glance.

### Layout

```
┌────────────────────────────────────────────────────────────┐
│  Integrations                                              │
│  13 available · 4 connected                                │
│                                                            │
│  ┌── Infrastructure & Cloud ──────────────────────────┐    │
│  │                                                    │    │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ │    │
│  │  │ ☁ AWS   │ │ ☁ Azure │ │ ☁ GCP   │ │ ⎈ K8s   │ │    │
│  │  │ ✅ Live │ │ Connect │ │ ✅ Live │ │ Connect │ │    │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘ │    │
│  │  ┌─────────┐                                      │    │
│  │  │ ▲ Vercel│                                      │    │
│  │  │ Connect │                                      │    │
│  │  └─────────┘                                      │    │
│  └────────────────────────────────────────────────────┘    │
│                                                            │
│  ┌── CI/CD & Source Control ─────────────────────────┐     │
│  │  ┌──────────┐ ┌──────────┐                        │     │
│  │  │ 🐙 GitHub│ │ 🦊 GitLab│                        │     │
│  │  │ ✅ Live  │ │ Connect  │                        │     │
│  │  └──────────┘ └──────────┘                        │     │
│  └────────────────────────────────────────────────────┘    │
│  ...                                                       │
└────────────────────────────────────────────────────────────┘
```

### Connector Card States

1. **Not Connected** — gray card, "Connect" CTA, description text
2. **Connected / Live** — green border, ✅ badge, "Configure" and "Disconnect" buttons, last verified time
3. **Error / Expired** — red border, ⚠️ badge, error message, "Reconnect" button
4. **Connecting** — spinner, disabled inputs

### Key Behaviors

- **Categories from registry**: "Infrastructure & Cloud", "CI/CD & Source Control", "Monitoring & Alerting", "Security", "Infrastructure as Code" — all from the connector registry's `category` field
- **Connect inline**: Clicking "Connect" expands the card to show auth fields (from registry)
- **Disconnect**: Removes credentials from `.env`, stops any active watches
- **Health badge**: Shows real-time connection health (verified via `authenticate()`)

---

## Detailed Task List

### Phase A — Dynamic Rendering

- [ ] **A1. Rewrite Integrations.tsx** — remove hardcoded connector categories and items
- [ ] **A2. Fetch all connectors from `/api/connectors`** on mount
- [ ] **A3. Group by `category`** dynamically
- [ ] **A4. Render connector cards** with icon, name, status from the API
- [ ] **A5. Category headers** from the API's unique categories (not hardcoded strings)

### Phase B — Inline Connection

- [ ] **B1. Expand card on "Connect" click** — show dynamic auth form from registry fields
- [ ] **B2. Connect flow** — same as wizard (Feature 05), calls `POST /api/connectors/{id}/connect`
- [ ] **B3. Success → collapse card** and show ✅ status
- [ ] **B4. Failure → show error** inline with retry option

### Phase C — Management Actions

- [ ] **C1. "Configure" button** — re-expand card to update credentials
- [ ] **C2. "Disconnect" button** — confirmation dialog, then removes credentials
- [ ] **C3. Health refresh** — manual "Check Connection" button to re-verify
- [ ] **C4. Last verified timestamp** — show when the connection was last verified

---

## Testing Methodology

### Anti-Hardcoding Test Suite

```
test_NO_HARDCODED_CATEGORIES — Categories are grouped from the API 
    response's category field, not from a hardcoded array.

test_NO_HARDCODED_CONNECTORS — The number of connector cards matches 
    the API response, not a fixed count. Add a mock connector, verify 
    it appears.

test_NO_HARDCODED_STATUS — Connection status ("Connected", "Not Connected") 
    comes from the API's live status check, not from a hardcoded map.

test_NO_HARDCODED_ICONS — Connector icons are rendered from the 
    registry's icon field.

test_NO_HARDCODED_COLORS — Connector brand colors come from the 
    registry's color field.

test_INLINE_FORM_FROM_REGISTRY — The auth form rendered when "Connect" 
    is clicked uses fields from the registry, not hardcoded inputs.
```

---

## Definition of Done

- [ ] All 13 connectors shown, dynamically from API
- [ ] Categories grouped from registry, not hardcoded
- [ ] Inline connect/disconnect/reconfigure works
- [ ] Real connection health shown for each connector
- [ ] Zero hardcoded connector names, icons, or statuses
