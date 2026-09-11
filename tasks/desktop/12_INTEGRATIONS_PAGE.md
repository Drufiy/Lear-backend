# Feature 12 — Integrations Management Page 🟡 MOSTLY DONE

**Priority:** P1 — post-setup connector management  
**Status:** 🟡 **MOSTLY DONE** — renders dynamically from API, inline connect flow missing  
**Depends on:** `02_CONNECTOR_REGISTRY.md` ✅, `05_SERVICE_CONNECTIONS.md` 🟡  
**Blocks:** Nothing

---

## What's Done

### Phase A — Dynamic Rendering ✅
- [x] **A1. Integrations.tsx rewritten** — no hardcoded connector lists
- [x] **A2. Fetch from `/api/connectors`** on mount (lines 20-26)
- [x] **A3. Group by `category`** dynamically — `Array.from(new Set(...))` (line 28)
- [x] **A4. Connector cards** with icon, name, status from API (lines 54-108)
- [x] **A5. Category headers** from unique categories (lines 48-52)
- [x] Connector brand colors from `item.color` (line 65)
- [x] Status badge — "● Configured" / "○ Not Configured" (lines 69-77)
- [x] Docs URL link (lines 84-95)
- [x] Loading state with spinner (lines 39-42)

## What's Remaining

### Phase B — Inline Connection (NOT STARTED)
- [ ] **B1. Expand card on "Connect" click** — show dynamic auth form inline (currently redirects to Wizard)
- [ ] **B2. Connect flow inline** — calls `POST /api/connectors/{id}/connect`
- [ ] **B3. Success → collapse card** and show ✅ status
- [ ] **B4. Failure → show error** inline with retry option

### Phase C — Management Actions (NOT STARTED)
- [ ] **C1. "Configure" button** — re-expand card to update credentials
- [ ] **C2. "Disconnect" button** — confirmation dialog, remove credentials
- [ ] **C3. Health refresh** — manual "Check Connection" button
- [ ] **C4. Last verified timestamp**

---

## Defects

> [!NOTE]
> **Minor**: The "Connect" / "Reconfigure" button (line 99) calls `onConfigureConnector` which in `App.tsx` sets `setIsSetupComplete(false)` — this **opens the full Wizard** instead of expanding the card inline. This is functional but poor UX — the user gets pulled out of the Integrations page just to update one connector's credentials.

> [!NOTE]
> **Minor**: The subtitle says "All 13 available providers" (line 35) — this count is hardcoded text. Should come from `connectors.length`.
