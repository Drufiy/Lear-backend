# Feature 07 — Project System

**Priority:** P0 — the organizational model (like Vercel projects)  
**Owner:** TBD  
**Depends on:** `01_BACKEND_API_BRIDGE.md`, `02_CONNECTOR_REGISTRY.md`, `06_SIDEBAR_NAVIGATION.md`  
**Target files:**  
- [`desktop/src/components/Projects.tsx`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/desktop/src/components/Projects.tsx) (rewrite)  
- `desktop/src/components/ProjectDetail.tsx` (new)  
- `desktop/src/components/ProjectCreate.tsx` (new)  
**Test file:** `tests/test_project_api.py` (new), `desktop/src/__tests__/Projects.test.tsx` (new)

---

## Product Spec

A Project in Lear is an organizational unit — like a Vercel project or a GitHub repository. It groups related services together so you can monitor your entire stack in one view.

### Data Model

```yaml
# prash.yaml
projects:
  - id: "my-saas-app"
    name: "My SaaS App"
    created_at: "2026-09-07T20:00:00Z"
    environments:
      - name: "Production"
        services:
          - connector_id: "aws"
            resource_id: "i-0abc123def"
            display_name: "API Server"
          - connector_id: "kubernetes"
            resource_id: "default/api-deployment"
            display_name: "K8s Pods"
          - connector_id: "github"
            resource_id: "myorg/myrepo"
            display_name: "CI Pipeline"
      - name: "Staging"
        services:
          - connector_id: "aws"
            resource_id: "i-0staging456"
            display_name: "Staging Server"
```

### Project List View

```
┌────────────────────────────────────────────────────────┐
│  Projects                              [+ New Project] │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │  My SaaS App                                     │  │
│  │  2 environments · 4 services · All healthy ●     │  │
│  │                                                  │  │
│  │  Production  ● AWS EC2  ● K8s  ● GitHub         │  │
│  │  Staging     ● AWS EC2                           │  │
│  │                                          [View →]│  │
│  └──────────────────────────────────────────────────┘  │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Internal Tools                                  │  │
│  │  1 environment · 2 services · 1 warning ◉        │  │
│  │                                                  │  │
│  │  Production  ● Vercel  ◉ Datadog                 │  │
│  │                                          [View →]│  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

### Project Detail View

```
┌────────────────────────────────────────────────────────┐
│  ← Back to Projects                                    │
│                                                        │
│  My SaaS App                                           │
│  [Production ▼] [Staging] [+ Add Environment]          │
│                                                        │
│  ┌────────────────┐ ┌────────────────┐ ┌────────────┐  │
│  │ ☁ API Server   │ │ ⎈ K8s Pods     │ │ ⚙ CI Pipe  │  │
│  │ AWS EC2        │ │ Kubernetes     │ │ GitHub     │  │
│  │ ● Healthy      │ │ ● 3/3 Running  │ │ ● Passing  │  │
│  │ CPU: 23.4%     │ │ Restarts: 0    │ │ Last: 2m   │  │
│  │                │ │                │ │            │  │
│  │ [Widget ↗]     │ │ [Widget ↗]     │ │ [Widget ↗] │  │
│  │ [Chat 💬]      │ │ [Chat 💬]      │ │ [Chat 💬]  │  │
│  └────────────────┘ └────────────────┘ └────────────┘  │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Activity Feed                                   │  │
│  │  ○ 2m ago  GitHub: CI passed (commit a1b2c3d)    │  │
│  │  ○ 5m ago  AWS: CPU spike to 89% on i-0abc123   │  │
│  │  ○ 12m ago K8s: Pod api-7f9d restarted (OOM)    │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

### Project Create Flow

```
Step 1: Project Name
  "What should we call this project?"
  [My SaaS App_______________]

Step 2: Select Services
  "Which connected services should Lear watch?"
  ☑ AWS EC2 (i-0abc123 — us-east-1)
  ☑ Kubernetes (default/api-deployment)
  ☑ GitHub (myorg/myrepo)
  ☐ Datadog (not connected)

Step 3: Environments (optional)
  "Add environments to organize your services"
  [+ Production] [+ Staging] [+ Development]
  Drag services to environments

Step 4: Confirm
  Summary of project configuration
  [Create Project]
```

### Key Behaviors

1. **Live service health**: Each service card in the project detail shows REAL current status from the connector
2. **Quick actions per service**: "Expand Widget" (full metric view), "Open Chat" (AI chat with service context)
3. **Environment switching**: Tabs above the service grid, one per environment
4. **Activity feed**: Aggregated events from ALL services in the current environment
5. **Edit/Delete**: Projects can be renamed, services added/removed, environments modified
6. **Empty state**: When no projects exist, show "Create your first project" with auto-import option

---

## Detailed Task List

### Phase A — Backend Project API

- [ ] **A1. Define project schema** — `id`, `name`, `created_at`, `environments[]` with `name` + `services[]`
- [ ] **A2. Implement `GET /api/projects`** — read from `prash.yaml`, include live status per service
- [ ] **A3. Implement `POST /api/projects`** — validate service connector_ids exist in registry, validate resource_ids (optional), save to `prash.yaml`
- [ ] **A4. Implement `PUT /api/projects/{id}`** — update project name, environments, services
- [ ] **A5. Implement `DELETE /api/projects/{id}`** — remove project, stop any associated watches
- [ ] **A6. Implement `GET /api/projects/{id}/status`** — aggregate health across all services in the project by calling each connector's `poll_state()`
- [ ] **A7. Auto-generate project ID** from name (slugify)

### Phase B — Project List View

- [ ] **B1. Rewrite Projects.tsx** as the list view
- [ ] **B2. Fetch projects from `/api/projects`** on mount
- [ ] **B3. Project card rendering** — name, environment count, service count, aggregate health
- [ ] **B4. Service badges** — show connector icons with status dots inline on the card
- [ ] **B5. "View →" link** — navigates to project detail view
- [ ] **B6. "+ New Project" button** — opens project creation flow
- [ ] **B7. Empty state** — "Create your first project" with auto-import CTA

### Phase C — Project Detail View

- [ ] **C1. Create ProjectDetail.tsx** component
- [ ] **C2. Back navigation** — "← Back to Projects" link
- [ ] **C3. Environment tabs** — dynamic tabs from project's environments array
- [ ] **C4. Service card grid** — one card per service in the selected environment
- [ ] **C5. Service card content** — connector icon, display name, connector type, live status, key metric
- [ ] **C6. "Expand Widget" button** — opens the full metric widget for this service (links to Feature 08)
- [ ] **C7. "Open Chat" button** — opens the AI chatbox scoped to this service (links to Feature 10)
- [ ] **C8. Activity feed** — chronological list of recent events from all services in this environment
- [ ] **C9. "+ Add Service" button** within an environment
- [ ] **C10. Edit project** — rename, add/remove environments

### Phase D — Project Creation Flow

- [ ] **D1. Create ProjectCreate.tsx** component
- [ ] **D2. Step 1: Name input** with validation (non-empty, unique)
- [ ] **D3. Step 2: Service selection** — list all configured connectors with their discoverable resources
- [ ] **D4. Resource discovery** — for each selected connector, call `/api/connectors/{id}/resources` to list available resources (EC2 instances, repos, etc.)
- [ ] **D5. Step 3: Environment setup** — optional, default to single "Production" environment
- [ ] **D6. Service-to-environment assignment** — drag/drop or checkboxes
- [ ] **D7. Step 4: Summary and confirm** — review before creating
- [ ] **D8. Submit** — call `POST /api/projects`, navigate to project detail on success

---

## Testing Methodology

### Unit Tests

```
test_project_crud_creates_in_yaml
test_project_crud_updates_name
test_project_crud_deletes
test_project_validates_connector_exists
test_project_validates_unique_name
test_project_status_aggregates_all_services
test_project_status_calls_real_poll_state
test_project_list_renders_from_api
test_project_detail_shows_environments
test_project_detail_shows_services_per_environment
test_project_create_flow_saves_via_api
test_project_card_shows_correct_service_count
test_project_card_shows_aggregate_health
```

### Anti-Hardcoding Test Suite

```
test_NO_HARDCODED_PROJECTS — The project list renders entirely from 
    the API response. No project names, service names, or resource IDs 
    exist in the frontend source code.

test_NO_HARDCODED_ENVIRONMENTS — Environment names ("Production", 
    "Staging") are NOT hardcoded in the component. They come from the 
    project's data in prash.yaml.

test_NO_HARDCODED_SERVICE_LIST — The service selection in the create 
    flow lists ONLY services from /api/connectors that are actually 
    configured, not a static list.

test_NO_HARDCODED_RESOURCE_IDS — Resource IDs (EC2 instance IDs, pod 
    names, repo names) are fetched from /api/connectors/{id}/resources, 
    not hardcoded.

test_NO_HARDCODED_STATUS — Each service card's status (healthy/error/etc.) 
    comes from a real poll_state() call via the API, not from a hardcoded 
    value in the project YAML.

test_NO_HARDCODED_METRICS_ON_CARDS — The "key metric" shown on service 
    cards (e.g., "CPU: 23.4%") comes from real connector data, not from 
    a placeholder.

test_PROJECT_DATA_PERSISTS — Create a project, restart the server, 
    verify the project still exists (prash.yaml persistence).

test_ACTIVITY_FEED_FROM_REAL_EVENTS — The activity feed shows events 
    from actual connector watch/stats calls, not synthetic events.
```

### E2E Tests

```
test_CREATE_PROJECT_FULL_FLOW — Create project → name it → select 
    services → assign environments → confirm → verify appears in list

test_PROJECT_DETAIL_NAVIGATION — List → click project → verify detail 
    view → switch environments → verify services change

test_DELETE_PROJECT — Create → delete → verify removed from list

test_ADD_SERVICE_TO_EXISTING_PROJECT — Open project → add a new 
    service → verify it appears in the environment
```

---

## Definition of Done

- [ ] Projects persist in `prash.yaml` with environments and services
- [ ] Project list shows real aggregate health from connector status
- [ ] Project detail shows services per environment with live status
- [ ] Service cards show real metrics from connectors, not placeholders
- [ ] Create flow discovers real resources from connectors
- [ ] Activity feed shows real events from connectors
- [ ] Anti-hardcoding tests all pass
