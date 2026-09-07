# Feature 04 — Onboarding Wizard

**Priority:** P0 — first-run experience, first impression  
**Owner:** TBD  
**Depends on:** `02_CONNECTOR_REGISTRY.md`, `03_DESIGN_SYSTEM.md`, `05_SERVICE_CONNECTIONS.md`  
**Target file:** [`desktop/src/components/Wizard.tsx`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/desktop/src/components/Wizard.tsx) (rewrite)  
**Test file:** `desktop/src/__tests__/Wizard.test.tsx` (new)

---

## Product Spec

The Wizard is what a new user sees the first time they open Lear. It guides them through connecting their infrastructure services. The entire wizard is **dynamically generated from the Connector Registry** — zero hardcoded connector forms.

### User Flow

```
1. Welcome Screen
   "Welcome to Lear — your AI DevOps agent"
   [Get Started]  [Import from .env]

2. Category Browser
   Tabs: Infrastructure | CI/CD | Monitoring | Security | IaC
   Grid of connector cards (from registry) with connect buttons

3. Connect a Service (per connector)
   Dynamic form generated from registry auth_fields
   [Verify & Connect] button → real API call → success/failure
   Animated status indicator (loading → success ✅ / error ❌)

4. Project Setup
   "Name your first project"
   Select which connected services belong to this project
   Optional: define environments (Production, Staging, Dev)

5. Done
   Summary of what was connected
   [Enter Dashboard] → main app
```

### Key Design Decisions

1. **Non-linear**: User can jump between categories, skip services, come back later
2. **Progressive**: You can enter the dashboard with just 1 service connected — you don't need all of them
3. **Quick import**: "Import from .env" scans the existing `.env` file and auto-detects configured services
4. **Real verification**: Every "Connect" button calls the actual provider API — not a simulated check
5. **Error recovery**: If connection fails, show the exact provider error message, not a generic "failed"

### UI Layout

```
┌─────────────────────────────────────────────────┐
│  Lear                                           │
│                                                 │
│  Welcome to Lear                                │
│  Connect your infrastructure in minutes.        │
│                                                 │
│  ┌──────────────────────────────────────────┐   │
│  │  [Infrastructure] [CI/CD] [Monitoring]   │   │
│  │  [Security] [IaC]                        │   │
│  │                                          │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ │   │
│  │  │ ☁ AWS    │ │ ☁ Azure  │ │ ☁ GCP    │ │   │
│  │  │ ✅ Done  │ │ Connect  │ │ Connect  │ │   │
│  │  └──────────┘ └──────────┘ └──────────┘ │   │
│  │  ┌──────────┐ ┌──────────┐              │   │
│  │  │ ⎈ K8s    │ │ ▲ Vercel │              │   │
│  │  │ Connect  │ │ Connect  │              │   │
│  │  └──────────┘ └──────────┘              │   │
│  └──────────────────────────────────────────┘   │
│                                                 │
│  Connected: 1 service    [Enter Dashboard →]    │
└─────────────────────────────────────────────────┘
```

### Connector Card States

1. **Unconfigured** — gray card, "Connect" button with accent outline
2. **Connecting** — spinner on the button, inputs disabled
3. **Connected** — green border glow, ✅ badge, "Reconfigure" link
4. **Failed** — red border, ❌ badge, error message, "Retry" button

### Dynamic Form Rendering

The wizard does NOT contain hardcoded `<input>` elements for each connector. Instead:

```tsx
// CORRECT — dynamic from registry
{connector.auth_fields.map(field => (
  <FormField key={field.key} field={field} />
))}

// WRONG — hardcoded per connector
{connectorId === 'aws' && (
  <>
    <input placeholder="Access Key ID" />
    <input placeholder="Secret Access Key" />
  </>
)}
```

The `FormField` component renders different input types based on `field.type`:
- `text` → standard text input
- `password` → password input with show/hide toggle
- `textarea` → multi-line input (e.g., GCP service account JSON)
- `file` → file picker (e.g., kubeconfig)
- `select` → dropdown (e.g., AWS region)

---

## Detailed Task List

### Phase A — Wizard Structure

- [ ] **A1. Rewrite Wizard.tsx** — remove all hardcoded connector sections (AWS, GCP, GitHub, Slack blocks)
- [ ] **A2. Fetch connector list from `/api/connectors`** on mount
- [ ] **A3. Group connectors by `category`** — render category tabs dynamically
- [ ] **A4. Render connector cards** from the fetched list — icon, name, status
- [ ] **A5. Welcome screen** with branding, description, and two CTAs: "Get Started" and "Import from .env"

### Phase B — Dynamic Connection Form

- [ ] **B1. Create `ConnectorForm` component** — receives a connector's `auth_fields` and renders the appropriate inputs dynamically
- [ ] **B2. Implement `FormField` component** — renders text/password/textarea/file/select based on `field.type`
- [ ] **B3. Password visibility toggle** — eye icon to show/hide password fields
- [ ] **B4. File picker for kubeconfig** — native file dialog (or drag-and-drop)
- [ ] **B5. Default values** — pre-fill inputs with `field.default` where available
- [ ] **B6. Placeholder text** — use `field.placeholder` from registry
- [ ] **B7. Help text** — show `field.help_text` below each input

### Phase C — Connection Flow

- [ ] **C1. "Verify & Connect" button** — calls `POST /api/connectors/{id}/connect` with the form values
- [ ] **C2. Loading state** — spinner on the button, inputs disabled during connection
- [ ] **C3. Success state** — green border glow, ✅ badge, show success message from backend
- [ ] **C4. Error state** — red border, ❌ badge, show the EXACT error message from the provider (not a generic message)
- [ ] **C5. Retry** — clear error and allow re-entering credentials
- [ ] **C6. Credential persistence** — on success, credentials are saved to `.env` by the backend

### Phase D — Auto-Import

- [ ] **D1. "Import from .env" button** — calls `POST /api/projects/auto-import`
- [ ] **D2. Show detection results** — list which connectors were auto-detected
- [ ] **D3. Verify each detected connector** — sequentially call `authenticate()` for each
- [ ] **D4. Show results per connector** — ✅ for verified, ⚠️ for detected but unverifiable

### Phase E — Project Setup

- [ ] **E1. Project naming step** — "Name your first project" input
- [ ] **E2. Service selection** — checklist of connected services to include in the project
- [ ] **E3. Environment setup** — optional: define environments (defaults: Production, Staging)
- [ ] **E4. Save project** — calls `POST /api/projects` with the configuration

### Phase F — Completion

- [ ] **F1. Summary screen** — show all connected services with status
- [ ] **F2. "Enter Dashboard" button** — transitions to the main app
- [ ] **F3. Progress indicator** — show "Connected: N services" throughout the wizard
- [ ] **F4. Skip functionality** — user can skip directly to dashboard at any point

---

## Testing Methodology

### Unit Tests

```
test_wizard_fetches_connectors_from_api — on mount, GET /api/connectors called
test_wizard_renders_all_categories_from_response — categories not hardcoded
test_wizard_renders_connector_cards_dynamically — count matches API response
test_connector_form_renders_text_field
test_connector_form_renders_password_field_with_toggle
test_connector_form_renders_textarea_field
test_connector_form_renders_file_picker
test_connector_form_renders_select_with_options
test_connector_form_uses_field_defaults
test_connector_form_uses_field_placeholders
test_connect_button_calls_api_with_form_values
test_connect_loading_state_disables_inputs
test_connect_success_shows_checkmark
test_connect_failure_shows_real_error_message
test_connect_failure_allows_retry
test_auto_import_calls_api
test_auto_import_shows_detection_results
test_project_setup_saves_via_api
test_skip_to_dashboard_works
```

### Anti-Hardcoding Test Suite

```
test_NO_HARDCODED_CONNECTOR_FORMS — The wizard source code (Wizard.tsx, 
    ConnectorForm.tsx) must NOT contain any connector-specific strings 
    like "AWS_ACCESS_KEY_ID", "GCP_PROJECT_ID", etc. All field names 
    come from the API. Grep the source for env var patterns.

test_NO_HARDCODED_CATEGORIES — The category tabs ("Infrastructure", 
    "CI/CD", etc.) are NOT hardcoded in the wizard. They come from the 
    unique set of categories in the API response.

test_NO_HARDCODED_CONNECTOR_COUNT — The wizard does not assume a fixed 
    number of connectors. If the registry has 15 connectors, the wizard 
    shows 15. If it has 8, it shows 8.

test_NO_HARDCODED_ICONS — Connector icons are rendered from the 
    registry's icon field, not from a switch/case in the wizard.

test_NO_HARDCODED_SUCCESS_MESSAGES — Success/failure messages come 
    from the API response's `message` field, not from frontend strings.

test_FORM_FIELD_TYPES_DYNAMIC — Add a connector with a new field type 
    (e.g., "checkbox") to the registry. Verify FormField either renders 
    it or falls back to text input — never crashes.

test_ERROR_MESSAGES_FROM_PROVIDER — When connection fails, the displayed 
    error message is the exact string from the backend's response, not 
    a generic "Connection failed" message.
```

### E2E Tests

```
test_FULL_WIZARD_FLOW — Open wizard → select category → enter credentials 
    → click connect → verify connection → name project → enter dashboard

test_WIZARD_WITH_NO_SERVICES — Start wizard with empty .env → verify 
    all connectors show "Connect" state → verify "Enter Dashboard" 
    still works (empty dashboard)

test_WIZARD_AUTO_IMPORT — Pre-populate .env with AWS keys → click 
    "Import from .env" → verify AWS shows as detected
```

---

## Definition of Done

- [ ] Wizard generates ALL forms dynamically from `/api/connectors`
- [ ] Zero connector-specific code in the wizard component
- [ ] All 13 connectors appear in the correct category
- [ ] Connection flow calls real `authenticate()` via the API
- [ ] Error messages show actual provider errors, not generic text
- [ ] Auto-import from `.env` works
- [ ] Project setup step creates a real project via API
- [ ] Anti-hardcoding tests all pass
