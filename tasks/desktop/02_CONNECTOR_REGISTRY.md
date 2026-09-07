# Feature 02 — Connector Registry & Auto-Discovery

**Priority:** P0 — drives wizard, widgets, chat, and every dynamic UI element  
**Owner:** TBD  
**Depends on:** `01_BACKEND_API_BRIDGE.md`, existing `prash/connectors/`  
**Target file:** `prash/connector_registry.py` (new)  
**Test file:** `tests/test_connector_registry.py` (new)

---

## Product Spec

The Connector Registry is the single source of truth for everything the desktop app knows about each connector. It defines what auth fields a connector needs, what widgets it supports, what category it belongs to, what icon/color to render — all in one place. The frontend NEVER hardcodes connector metadata; it always comes from this registry via the API.

### What It Does

1. **Declares all 13 connectors** with their metadata, auth requirements, and UI hints
2. **Auto-discovers configured connectors** by checking `.env` for required credentials
3. **Defines widget templates per connector** — what metrics/visualizations are available for each service type
4. **Provides auth field schemas** — so the wizard can dynamically generate credential forms
5. **Categorizes connectors** — Infrastructure, CI/CD, Monitoring, Security, IaC

### Why a Registry (not hardcoded in frontend)

- **Single source of truth**: Adding a new connector = adding one registry entry. No frontend changes needed.
- **Dynamic wizard**: The onboarding wizard renders auth forms FROM the registry, not from hardcoded JSX
- **Dynamic widgets**: Widget types are defined per-connector in the registry, not in React component code
- **Testability**: You can assert completeness (all 13 present, all have auth fields, all have widgets)

### Registry Entry Schema

```python
@dataclass
class AuthField:
    key: str               # env var name, e.g. "AWS_ACCESS_KEY_ID"
    label: str             # human-readable, e.g. "Access Key ID"
    type: str              # "text" | "password" | "textarea" | "file" | "select"
    required: bool = True
    default: str = ""
    placeholder: str = ""
    help_text: str = ""
    options: list[str] = field(default_factory=list)  # for "select" type

@dataclass
class WidgetTemplate:
    id: str                # e.g. "cpu_gauge"
    label: str             # e.g. "CPU Utilization"
    type: str              # "gauge" | "line_chart" | "status_grid" | "event_timeline" | "metric_card" | "bar_chart"
    metric_keys: list[str] # e.g. ["CPUUtilization"] — maps to connector get_stats() event_types
    unit: str = ""         # e.g. "%", "MB/s", "ms"
    description: str = ""
    refresh_interval: int = 30  # seconds

@dataclass
class ConnectorRegistryEntry:
    id: str                     # e.g. "aws"
    name: str                   # e.g. "AWS EC2"
    category: str               # "infrastructure" | "cicd" | "monitoring" | "security" | "iac"
    icon: str                   # lucide icon name, e.g. "cloud"
    color: str                  # hex color, e.g. "#FF9900"
    connector_class: type       # the actual Connector subclass
    auth_fields: list[AuthField]
    widget_templates: list[WidgetTemplate]
    description: str = ""
    docs_url: str = ""
    supports_watch: bool = False
    supports_stats: bool = False
    supports_execute: bool = False
```

### Complete Registry (all 13 connectors)

| ID | Name | Category | Color | Auth Fields | Widget Templates |
|---|---|---|---|---|---|
| `aws` | AWS EC2 | infrastructure | `#FF9900` | AccessKeyID, SecretKey, Region | CPU gauge, Network I/O chart, Disk Ops, Status Checks, Alarms timeline |
| `azure` | Microsoft Azure | infrastructure | `#0078D4` | SubscriptionID, TenantID, ClientID, ClientSecret, Location | VM status, CPU gauge, Memory chart, Disk I/O |
| `gcp` | Google Cloud | infrastructure | `#4285F4` | ProjectID, ServiceAccountJSON, Region | Instance status, CPU gauge, Network chart, Disk metrics |
| `kubernetes` | Kubernetes | infrastructure | `#326CE5` | Kubeconfig (file), Context, Namespace | Pod status grid, Restart count, Memory/CPU per pod, Events timeline |
| `vercel` | Vercel | infrastructure | `#000000` | VercelToken, TeamID | Deployment status, Build time chart, Function invocations |
| `github` | GitHub Actions | cicd | `#24292E` | PersonalAccessToken | Workflow status, Recent runs, Success rate, Build time trend |
| `gitlab` | GitLab CI | cicd | `#FC6D26` | AccessToken, BaseURL | Pipeline status, Recent pipelines, Success rate, Duration trend |
| `datadog` | Datadog | monitoring | `#632CA6` | APIKey, AppKey, Site | Monitor status grid, Alert timeline, Custom metric charts |
| `grafana` | Grafana | monitoring | `#F46800` | URL, APIKey | Alert rules, Dashboard list, Panel metrics |
| `pagerduty` | PagerDuty | monitoring | `#06AC38` | APIKey, RoutingKey | Incident timeline, On-call status, Escalation chain |
| `snyk` | Snyk | security | `#4C4A73` | APIToken, OrgID | Vulnerability count, Severity breakdown, Project health |
| `gitleaks` | Gitleaks | security | `#FF6B6B` | (none — local binary) | Scan results, Secret count, Severity breakdown |
| `terraform` | Terraform | iac | `#7B42BC` | (local state path) | Drift status, Resource count, Last apply time |

---

## Detailed Task List

### Phase A — Registry Data Structure

- [ ] **A1. Create `prash/connector_registry.py`** with the dataclass definitions (`AuthField`, `WidgetTemplate`, `ConnectorRegistryEntry`)
- [ ] **A2. Register AWS connector** — full auth fields (AccessKeyID, SecretKey, Region), all widget templates (CPU, Network, Disk, Status Checks, Alarms)
- [ ] **A3. Register Azure connector** — auth fields (SubscriptionID, TenantID, ClientID, ClientSecret, Location), widget templates
- [ ] **A4. Register GCP connector** — auth fields (ProjectID, ServiceAccountJSON, Region), widget templates
- [ ] **A5. Register Kubernetes connector** — auth fields (Kubeconfig file path, Context, Namespace), widget templates
- [ ] **A6. Register Vercel connector** — auth fields (Token, TeamID), widget templates
- [ ] **A7. Register GitHub connector** — auth fields (PAT), widget templates
- [ ] **A8. Register GitLab connector** — auth fields (Token, BaseURL), widget templates
- [ ] **A9. Register Datadog connector** — auth fields (APIKey, AppKey, Site), widget templates
- [ ] **A10. Register Grafana connector** — auth fields (URL, APIKey), widget templates
- [ ] **A11. Register PagerDuty connector** — auth fields (APIKey, RoutingKey), widget templates
- [ ] **A12. Register Snyk connector** — auth fields (Token, OrgID), widget templates
- [ ] **A13. Register Gitleaks connector** — no auth fields (local binary), widget templates
- [ ] **A14. Register Terraform connector** — auth fields (state file path), widget templates

### Phase B — Auto-Discovery

- [ ] **B1. Implement `discover_configured()` function** — reads `.env`, checks each connector's required auth fields, returns list of configured connector IDs
- [ ] **B2. Implement `get_connector_status(id)` function** — beyond just "configured", actually instantiate and call `authenticate()` to verify credentials are valid
- [ ] **B3. Implement `get_missing_fields(id)` function** — returns which auth fields are missing for a partially-configured connector
- [ ] **B4. Wire into server.py** — `GET /api/connectors` uses the registry, not hardcoded logic

### Phase C — Widget Template System

- [ ] **C1. Define widget templates for each connector** that map to actual `get_stats()` event types
- [ ] **C2. Implement `get_widget_config(connector_id)` function** — returns the widget templates for a connector, including which are currently available (based on connector capabilities)
- [ ] **C3. Widget template validation** — verify that every `metric_key` in a widget template corresponds to an actual event_type the connector can produce

### Phase D — Serialization

- [ ] **D1. Implement `registry_to_json()` function** — serialize the full registry to JSON for the frontend (excluding the class reference)
- [ ] **D2. Implement `connector_detail_to_json(id)` function** — serialize a single connector's full metadata

---

## Testing Methodology

### Unit Tests (`tests/test_connector_registry.py`)

```
test_registry_has_all_13_connectors
test_every_connector_has_name_and_id
test_every_connector_has_category
test_every_connector_has_icon_and_color
test_every_connector_has_at_least_one_widget_template
test_every_connector_class_is_importable
test_every_auth_field_has_key_and_label
test_every_auth_field_key_is_valid_env_var_name
test_no_duplicate_connector_ids
test_no_duplicate_auth_field_keys_within_connector
test_category_values_are_valid_enum
test_widget_template_types_are_valid
test_discover_configured_with_full_env
test_discover_configured_with_empty_env
test_discover_configured_with_partial_env
test_get_missing_fields_all_present
test_get_missing_fields_partial
test_get_connector_status_authenticated
test_get_connector_status_bad_credentials
test_registry_to_json_shape
```

### Anti-Hardcoding Test Suite

```
test_NO_HARDCODED_CONNECTOR_LIST — The frontend NEVER contains a 
    hardcoded list of connectors. Verify that the wizard and integrations 
    page render ONLY from /api/connectors response data.

test_NO_HARDCODED_AUTH_FIELDS — The wizard credential forms are 
    generated from registry auth_fields, not from hardcoded <input> 
    elements per connector. Simulate adding a new connector to the 
    registry and verify the wizard renders its fields without code changes.

test_NO_HARDCODED_WIDGET_LIST — Widget templates come from the registry, 
    not from React component code. Verify by adding a widget template to 
    a connector's registry entry and confirming it appears in the UI.

test_REGISTRY_DRIVES_EVERYTHING — Every connector's name, icon, color, 
    category, and auth fields rendered in the UI match EXACTLY what's in 
    the registry. No frontend overrides.

test_NO_HARDCODED_CATEGORIES — The category grouping in the wizard/
    integrations page comes from the registry category field, not from 
    a hardcoded array in the frontend.

test_NEW_CONNECTOR_ZERO_FRONTEND_CHANGES — Create a MockConnector with 
    registry entry. Verify it appears in /api/connectors, wizard renders 
    its auth fields, and its widget templates are available. All without 
    touching any frontend code.
```

### Completeness Tests

```
test_EVERY_CONNECTOR_IN_PRASH_CONNECTORS_IS_REGISTERED — Scan the 
    prash/connectors/ directory for .py files (excluding __init__, base, 
    testdata). Assert each has a registry entry.

test_EVERY_AUTH_FIELD_EXISTS_IN_ENV_EXAMPLE — Every auth field key in 
    the registry appears in .env.example.

test_EVERY_WIDGET_METRIC_KEY_IS_DOCUMENTED — Every metric_key in 
    widget templates has a corresponding event_type that the connector 
    is known to produce (from its get_stats docstring or test fixtures).
```

---

## Definition of Done

- [ ] `CONNECTOR_REGISTRY` dict contains all 13 connectors with complete metadata
- [ ] `discover_configured()` correctly identifies configured connectors from `.env`
- [ ] `GET /api/connectors` returns the full registry with live status
- [ ] Widget templates defined for every connector
- [ ] Adding a new connector requires ONLY adding a registry entry + connector class — zero frontend changes
- [ ] All anti-hardcoding tests pass
- [ ] All completeness tests pass
