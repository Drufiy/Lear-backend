# Feature 06 — Sidebar & Navigation 🟡 PARTIALLY DONE

**Priority:** P0 — the app's structural skeleton  
**Status:** 🟡 **PARTIAL** — structure exists with known hardcoding violations  
**Depends on:** `03_DESIGN_SYSTEM.md` ✅, `07_PROJECT_SYSTEM.md` 🟡  
**Blocks:** Nothing directly (used by all views)

---

## What's Done

- [x] **A1. Sidebar.tsx rewritten** — uses config array for nav items (lines 30-36)
- [x] **A2. Lear branding** — "Lear" text + v2.0 badge + "Infrastructure Intelligence" tagline
- [x] **A3. Nav items with icons** — Home, FolderGit2, Blocks, Bell, Settings from lucide-react
- [x] **A4. Active state indicator** — accent-colored left border with Framer Motion `layoutId` spring animation (lines 126-133)
- [x] **A5. Section separators** — subtle borders between sections
- [x] **B1. Project selector** — dropdown at top, lists projects from props (lines 55-85)
- [x] **B7. Wire project selection** — calls `onSelectProject` prop, updates parent state
- [x] Live service tree — shows services from active environment with pulse dot (lines 139-158)
- [x] Footer watcher status — shows watcher stream state with radar pulse animation (lines 162-175)

## What's Remaining

### Critical Fixes
- [ ] **🔴 FIX: Hardcoded environments** — Line 89: `{['Production', 'Staging'].map(env => ...)}` — must derive from `activeProject?.environments?.map(e => e.name)` instead
- [ ] **B4. "All Projects" option** — aggregate view across all projects
- [ ] **B5. "+ New Project" option** — at bottom of project dropdown
- [ ] **B6. Persist selected project** — remember selection across page refreshes (localStorage)

### Missing Features
- [ ] **C1-C6. Live Watch Status Section** — currently shows services from project, NOT active watchers from `/api/watch/active`. Should show watched resources with WebSocket-driven status dots
- [ ] **D2. Connection count indicator** — "Connected (N)" from API, not shown currently
- [ ] **D3. Version number** — from `package.json`, not shown currently
- [ ] **D4. Aggregate status dot** — green if all healthy, yellow if degraded
- [ ] **E2. Create `LearContext`** — global context providing `activeProject`, `connectedServices`, `watchState`

---

## Defects

> [!CAUTION]
> **HARDCODING VIOLATION**: `Sidebar.tsx` line 89 hardcodes `['Production', 'Staging']` for environment tabs. If a project has `['Production', 'Staging', 'Development']`, the third env is invisible.

> [!WARNING]
> The "Live Services" section (lines 139-158) shows services from the project's active environment, NOT active watcher handles. Per the spec, this section should show **only watched resources** with real-time WebSocket-driven status colors.
