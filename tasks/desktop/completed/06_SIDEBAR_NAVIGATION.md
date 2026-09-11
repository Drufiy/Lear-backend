# Feature 06 — Sidebar & Navigation ✅ COMPLETED

**Priority:** P0 — the app's structural skeleton  
**Status:** ✅ **COMPLETED** — fully dynamic, zero hardcoding, integrated with `LearContext` and backend watch APIs  
**Depends on:** `03_DESIGN_SYSTEM.md` ✅, `07_PROJECT_SYSTEM.md` ✅  
**Blocks:** Nothing directly (used by all views)

---

## What's Completed

### Foundation & UI
- [x] **A1. Sidebar.tsx structured with config array** — Nav items defined cleanly with icons, labels, badges, and layout IDs.
- [x] **A2. Lear branding & versioning** — "Lear" text + dynamic `v2.0.0` badge fetched from `/api/system/version` + "Infrastructure Intelligence" tagline.
- [x] **A3. Nav items with icons** — Dashboard (`Home`), Projects (`FolderGit2`), Integrations (`Blocks`), Activity Log (`Activity`), Notifications (`Bell`), Settings (`Settings`).
- [x] **A4. Active state indicator** — Accent-colored left border with Framer Motion `layoutId="sidebar-active"` spring animation.
- [x] **A5. Section separators** — Subtle dark borders between branding, menu, and watch status.

### Project & Environment Selection
- [x] **B1. Project selector** — Dropdown listing all real projects from `/api/projects`.
- [x] **B4. "All Projects" option** — Aggregate view across all projects with `Layers` icon, aggregating all environments and services.
- [x] **B5. "+ New Project" option** — Button at the bottom of dropdown that navigates to Projects tab and triggers creation modal.
- [x] **B6. Persist selected project** — Project ID selection persisted in `localStorage` under `lear_active_project_id`.
- [x] **B7. Wire project selection** — Synchronized through global `LearContext` with reactive updates across the entire app.
- [x] **🔴 FIX: Dynamic environments** — Environment tabs derived dynamically from `activeProject?.environments`. Automatically falls back to valid environments when switching projects. Selection persisted in `localStorage` under `lear_active_environment`.

### Live Watch Status & Telemetry
- [x] **C1-C6. Live Watch Status Section** — Displays active watched resources fetched from `GET /api/watch/active` and live WebSocket events from `/ws/events`.
- [x] **Real-time status colors** — Dynamic status dots:
  - Green (`bg-accent`): Healthy
  - Amber (`bg-amber-400`): Degraded / Warning
  - Red (`bg-rose-500`): Alerting / Error
  - Blue (`bg-sky-400`): Deploying
- [x] **Stop watch action** — Hover-revealed button to stop active watch handles via `DELETE /api/connectors/{id}/watch`.
- [x] **1-Click watch for active services** — When no active watches are running, active services show a quick 1-click `Watch` button.

### Badges & Metrics
- [x] **D2. Connection count indicator** — Displays real count of configured backend connectors (`Connected (N)`) in the brand header.
- [x] **D3. Version number** — Dynamic version `v2.0.0` from `GET /api/system/version` / package metadata.
- [x] **D4. Aggregate status dot** — Pulsing health status indicator next to brand logo showing overall infrastructure state.
- [x] **E2. Global `LearContext`** — Created `desktop/src/context/LearContext.tsx`, managing projects, environments, active watches, connection counts, and notifications globally.

---

## Anti-Hardcoding Audit Results

| Item | Requirement | Status | Verification |
|---|---|---|---|
| Environments | Must derive from `activeProject?.environments` | ✅ PASSED | Zero static arrays; dynamic tabs render from context |
| Projects | Must list real projects from backend + "All Projects" | ✅ PASSED | Fetched from `/api/projects`, persists to `localStorage` |
| Watch Resources | Must show real watch handles from `/api/watch/active` | ✅ PASSED | Displays actual watched targets with live WebSocket status |
| Connection Count | Must show real configured connector count | ✅ PASSED | Derived from `/api/connectors` configured list |
| Version | Must reflect actual app / engine version | ✅ PASSED | Fetched from `/api/system/version` |
