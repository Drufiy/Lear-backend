# Feature 07 — Project System 🟡 PARTIALLY DONE

**Priority:** P0 — the organizational model  
**Status:** 🟡 **PARTIAL** — list view works with critical hardcoding defects, detail/create views missing  
**Depends on:** `01_BACKEND_API_BRIDGE.md` ✅, `02_CONNECTOR_REGISTRY.md` ✅, `06_SIDEBAR_NAVIGATION.md` 🟡  
**Blocks:** `08_METRIC_WIDGETS.md`, `11_DASHBOARD_OVERVIEW.md`

---

## What's Done

### Phase A — Backend Project API
- [x] **A1. Project schema** — `id`, `name`, `created_at`, `environments[]` with `name` + `services[]`
- [x] **A2. `GET /api/projects`** — reads from `prash.yaml`
- [x] **A3. `POST /api/projects`** — saves to `prash.yaml`
- [x] **A5. `DELETE /api/projects/{id}`** — removes project
- [x] **A7. Auto-generate project ID** from name (slugify) — line 64: `newProjectName.toLowerCase().replace(/\s+/g, '-')`

### Phase B — Project List View
- [x] **B1. Projects.tsx as list view** — functional with project cards
- [x] **B2. Fetch from `/api/projects`** on mount (lines 29-41)
- [x] **B3. Project card rendering** — name, environments, service counts
- [x] **B5. "View →" link** — implicit (no navigation to detail yet)
- [x] **B6. "+ New Project" button** — opens modal (lines 124-129)
- [x] **B7. Empty state** — "No Projects Found" with auto-import CTA (lines 138-153)
- [x] Auto-import from `.env` via `POST /api/projects/auto-import` (lines 47-59)
- [x] Delete project via API (lines 96-105)

## What's Remaining

### 🔴 Critical Fix Required
- [ ] **FIX: `handleCreateProject` hardcodes resource IDs** — Lines 71-76:
  ```tsx
  services: [{ connector_id: 'aws', resource_id: 'i-0abc123', display_name: 'Primary EC2' }]
  ```
  This creates a project with **fake** AWS resource IDs. Must be replaced with a service selection step that discovers real resources.

### Phase A — Backend (remaining)
- [ ] **A4. `PUT /api/projects/{id}`** — update project name/environments/services
- [ ] **A6. `GET /api/projects/{id}/status`** — aggregate health per service via `poll_state()`

### Phase C — Project Detail View (NOT STARTED)
- [ ] **C1. Create `ProjectDetail.tsx`** component
- [ ] **C2. Back navigation** — "← Back to Projects"
- [ ] **C3. Environment tabs** — dynamic tabs from project's environments
- [ ] **C4. Service card grid** — one card per service in selected environment
- [ ] **C5. Service card content** — connector icon, display name, live status, key metric
- [ ] **C6. "Expand Widget" button** — opens full metric widget (Feature 08)
- [ ] **C7. "Open Chat" button** — opens AI chat scoped to service (Feature 10)
- [ ] **C8. Activity feed** — events from all services in environment
- [ ] **C9. "+ Add Service" button**
- [ ] **C10. Edit project** — rename, add/remove environments

### Phase D — Project Creation Flow (NOT STARTED)
- [ ] **D1. Create `ProjectCreate.tsx`** component
- [ ] **D2. Step 1: Name input** with validation
- [ ] **D3. Step 2: Service selection** — list configured connectors with real resources
- [ ] **D4. Resource discovery** — call `/api/connectors/{id}/resources` per connector
- [ ] **D5. Step 3: Environment setup**
- [ ] **D6. Service-to-environment assignment**
- [ ] **D7. Step 4: Summary and confirm**
- [ ] **D8. Submit** via `POST /api/projects`

---

## Defects

> [!CAUTION]
> **HARDCODING VIOLATION**: `Projects.tsx` lines 71-76 create new projects with hardcoded `i-0abc123` and `i-0staging` resource IDs. Every new project gets the same fake AWS instance IDs regardless of what the user has actually connected.

> [!WARNING]
> No `ProjectDetail.tsx` exists — clicking a project card does nothing. The spec's detail view with environment tabs, service cards with live status, and activity feed is completely missing.

---

## Files Required
- `desktop/src/components/ProjectDetail.tsx` — **NEW**
- `desktop/src/components/ProjectCreate.tsx` — **NEW**
