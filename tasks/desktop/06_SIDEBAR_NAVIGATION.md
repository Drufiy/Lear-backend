# Feature 06 — Sidebar & Navigation

**Priority:** P0 — the app's structural skeleton  
**Owner:** TBD  
**Depends on:** `03_DESIGN_SYSTEM.md`, `07_PROJECT_SYSTEM.md`  
**Target files:**  
- [`desktop/src/components/Sidebar.tsx`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/desktop/src/components/Sidebar.tsx) (rewrite)  
- [`desktop/src/App.tsx`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/desktop/src/App.tsx) (rewrite)  
**Test file:** `desktop/src/__tests__/Sidebar.test.tsx` (new)

---

## Product Spec

The sidebar is the persistent navigation spine of the app. It's always visible, provides project context, navigation between views, and live status indicators. Modeled after Vercel's sidebar — clean, information-dense, context-aware.

### Layout

```
┌────────────────────────┐
│  ◆ Lear               │  ← Logo + brand name
│                        │
│  ┌──────────────────┐  │  ← Project selector dropdown
│  │ My AWS Project ▾ │  │
│  └──────────────────┘  │
│                        │
│  ──────────────────── │  ← Separator
│                        │
│  ● Overview           │  ← Nav items with active indicator
│    Projects           │
│    Integrations       │
│    Activity Log       │
│                        │
│  ──────────────────── │
│                        │
│  WATCHING              │  ← Live watch status section
│  ● AWS EC2 i-0abc     │     Green dot = healthy
│  ◉ K8s api-pod        │     Yellow dot = degraded
│                        │
│  ──────────────────── │
│                        │
│  ⚙ Settings           │  ← Bottom section
│  ● Connected (3)      │     Connection count
│  v0.2.0               │     Version number
└────────────────────────┘
```

### Sidebar Behavior

1. **Fixed width**: 256px, not collapsible (desktop app, not mobile)
2. **Always visible**: Present on every page except the wizard
3. **Project context**: The selected project determines what the main area shows
4. **Live indicators**: Watch status dots update in real-time from WebSocket events
5. **Active state**: Current page highlighted with accent color + left border indicator

### Navigation Items

| ID | Label | Icon | View |
|---|---|---|---|
| `overview` | Overview | `LayoutDashboard` | Dashboard with health summary |
| `projects` | Projects | `FolderGit2` | Project list / project detail |
| `integrations` | Integrations | `Blocks` | Connector management |
| `activity` | Activity Log | `Clock` | Event timeline + audit log |
| `settings` | Settings | `Settings` | Preferences, credentials, about |

### Project Selector

- Dropdown at the top of the sidebar
- Lists all projects from `GET /api/projects`
- Shows: project name + service count
- "All Projects" option at the top (shows aggregate)
- "+ New Project" at the bottom of the dropdown
- Changing project updates the main area view

### Live Watch Section

- Only visible when there are active watchers
- Shows each watched resource with:
  - Status dot (green/yellow/red)
  - Connector icon (small)
  - Resource short name (truncated to fit)
- Clicking a watched resource navigates to its widget detail
- Dot color updates in real-time via WebSocket

---

## Detailed Task List

### Phase A — Sidebar Structure

- [ ] **A1. Rewrite Sidebar.tsx** — remove hardcoded nav items, use a config array
- [ ] **A2. Add Lear branding** — logo + "Lear" text (not "Prash")
- [ ] **A3. Implement nav items** with icons from lucide-react
- [ ] **A4. Active state indicator** — accent-colored left border + text highlight with spring animation
- [ ] **A5. Section separators** — subtle horizontal lines between sections

### Phase B — Project Selector

- [ ] **B1. Create `ProjectSelector` component** — dropdown at the top of the sidebar
- [ ] **B2. Fetch projects from `/api/projects`** on mount
- [ ] **B3. Show project name + service count badge** for each project
- [ ] **B4. "All Projects" option** — aggregate view across all projects
- [ ] **B5. "+ New Project" option** — navigates to project creation flow
- [ ] **B6. Persist selected project** — remember selection across page refreshes (localStorage)
- [ ] **B7. Wire project selection** — changing project updates `activeProject` in App.tsx state

### Phase C — Live Watch Status

- [ ] **C1. Create `WatchStatusSection` component** — renders only when active watchers exist
- [ ] **C2. Fetch active watches** from `/api/watch/poll` or WebSocket
- [ ] **C3. Render resource list** with status dots, connector icons, and short names
- [ ] **C4. Real-time status updates** — subscribe to WebSocket `/ws/events` for status changes
- [ ] **C5. Click handler** — clicking a watched resource navigates to its service widget
- [ ] **C6. Empty state** — section hidden when no active watches (not "No watches" placeholder)

### Phase D — Bottom Section

- [ ] **D1. Settings link** — navigates to settings view
- [ ] **D2. Connection count indicator** — "Connected (N)" showing number of configured connectors
- [ ] **D3. Version number** — read from `package.json` version field
- [ ] **D4. Aggregate status dot** — green if all connectors healthy, yellow if any degraded, red if any failed

### Phase E — App.tsx Router

- [ ] **E1. Implement routing state** in App.tsx — `activeView` + `activeProject`
- [ ] **E2. Create global context** — `LearContext` providing `activeProject`, `connectedServices`, `watchState`
- [ ] **E3. Wire sidebar navigation** to view switching
- [ ] **E4. Maintain scroll position** per view (don't reset scroll on tab switch)

---

## Testing Methodology

### Unit Tests

```
test_sidebar_renders_all_nav_items
test_sidebar_highlights_active_item
test_sidebar_shows_lear_branding
test_project_selector_fetches_from_api
test_project_selector_shows_project_names
test_project_selector_shows_service_counts
test_project_selector_persists_selection
test_watch_section_hidden_when_no_watches
test_watch_section_shows_active_resources
test_watch_status_dots_update_from_events
test_bottom_section_shows_connection_count
test_bottom_section_shows_version
```

### Anti-Hardcoding Test Suite

```
test_NO_HARDCODED_PROJECT_LIST — The project selector does NOT contain 
    a hardcoded list of project names. It renders from the API response.

test_NO_HARDCODED_NAV_ITEMS — While nav items are defined in a config 
    array (acceptable), they are NOT conditionally rendered based on 
    hardcoded connector states.

test_NO_HARDCODED_WATCH_RESOURCES — The live watch section renders 
    entirely from the API's active watch list, not from hardcoded 
    resource names.

test_NO_HARDCODED_CONNECTION_COUNT — The "Connected (N)" count comes 
    from the actual number of configured connectors via the API, not 
    from a hardcoded number.

test_NO_HARDCODED_STATUS_COLORS — Status dot colors are determined by 
    the actual watcher status from the API, not by hardcoded connector 
    ID checks (e.g., no "if aws then green").

test_BRANDING_SAYS_LEAR — Grep sidebar source for "Prash" — must not 
    appear. Only "Lear" branding.
```

### Integration Tests

```
test_SIDEBAR_NAV_SWITCHES_VIEW — Click each nav item, verify the 
    main area changes to the corresponding view.

test_PROJECT_SELECTOR_UPDATES_VIEW — Change project in selector, 
    verify main area shows that project's data.

test_WATCH_STATUS_LIVE_UPDATE — Start a watcher via API, verify 
    the watch section appears in the sidebar with the resource.
```

---

## Definition of Done

- [ ] Sidebar renders with Lear branding (not Prash)
- [ ] All 5 nav items with icons and active state animation
- [ ] Project selector dropdown with live project list from API
- [ ] Selected project persisted across refreshes
- [ ] Live watch section shows active watchers with real-time status dots
- [ ] Connection count reflects actual configured connectors
- [ ] All anti-hardcoding tests pass
