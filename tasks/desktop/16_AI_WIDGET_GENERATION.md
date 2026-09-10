# Feature 16 — AI Widget Generation

**Priority:** P1 — AI creates custom widget configurations per service  
**Owner:** TBD  
**Depends on:** `02_CONNECTOR_REGISTRY.md`, `08_METRIC_WIDGETS.md`, `10_AI_CHATBOX.md`  
**Target files:**  
- `prash/widget_generator.py` (new)  
- `desktop/src/components/WidgetConfigurator.tsx` (new)  
**Test file:** `tests/test_widget_generator.py` (new)

---

## Product Spec

When Lear connects to a new service, the AI analyses the connector's capabilities and the specific resource being watched to **generate custom widget configurations**. For example:

- You connect an EC2 instance → Lear sees it has CloudWatch metrics → generates CPU gauge, Network chart, Disk chart, Alarm timeline
- You connect a Kubernetes deployment → Lear sees it has pods, events, restart counts → generates pod grid, event timeline, restart counter
- You connect a Datadog account → Lear sees which monitors exist → generates monitor status grid tailored to YOUR monitors

This is NOT the frontend rendering widgets from a static template list. This is the AI looking at the ACTUAL resources and capabilities and generating a CUSTOM widget layout.

### How It Works

```
User connects a service and selects a resource to watch
    │
    ▼
POST /api/connectors/{id}/generate-widgets
    {resource_id: "i-0abc123"}
    │
    ▼
Backend:
  1. Get the connector's read_capabilities
  2. Call connector.get_stats(resource_id) to see what data is available
  3. Call connector.poll_state(resource_id) for current state
  4. Build a prompt for the AI:
     "Given an AWS EC2 instance with these capabilities: [instance_status, 
      logs, execute_command, watch, stats]. Available CloudWatch metrics: 
      [CPUUtilization, NetworkIn, NetworkOut, DiskReadOps, StatusCheckFailed].
      Current state: running, CPU: 23.4%.
      Generate a dashboard widget layout optimized for monitoring this 
      specific resource."
  5. AI returns a widget configuration JSON
    │
    ▼
Returns widget_config:
  [
    {id: "cpu", type: "gauge", metric_key: "CPUUtilization", label: "CPU", position: {row: 0, col: 0, span: 1}},
    {id: "network", type: "line_chart", metric_keys: ["NetworkIn", "NetworkOut"], label: "Network I/O", position: {row: 0, col: 1, span: 2}},
    ...
  ]
    │
    ▼
Frontend renders widgets from this generated config
```

### Two Modes

#### Mode 1: Template-Based (Fast, Reliable)
Uses the connector registry's pre-defined `widget_templates`. This is the fallback and default — always works, no LLM call needed.

#### Mode 2: AI-Generated (Personalized)
Makes an LLM call to generate a custom widget layout based on the actual resource's data. More tailored (e.g., if your EC2 instance has unusual metrics or your Datadog has custom monitors), but requires LLM access.

The app tries Mode 2 first, falls back to Mode 1 if the LLM is unavailable or returns invalid config.

### Widget Configuration Schema

```python
@dataclass
class WidgetConfig:
    id: str                    # unique widget identifier
    type: str                  # gauge | line_chart | metric_card | event_timeline | status_grid | bar_chart
    label: str                 # display label
    metric_keys: list[str]     # which metrics/events to display
    unit: str                  # display unit (%, MB/s, etc.)
    refresh_interval: int      # seconds
    position: WidgetPosition   # grid position
    size: str                  # "small" | "medium" | "large"
    description: str           # what this widget shows
    thresholds: dict           # {warning: 70, critical: 90} for gauges

@dataclass
class WidgetPosition:
    row: int
    col: int
    span: int                  # how many columns to span
```

### AI Prompt Template

```
You are Lear, an AI DevOps agent. Given the following connected service, 
generate an optimal monitoring dashboard widget layout.

Service: {connector_name} ({connector_id})
Resource: {resource_id}
Available capabilities: {read_capabilities}
Available metrics: {metric_names}
Current state: {current_state}
Recent events: {recent_events_summary}

Generate a JSON array of widget configurations. Each widget should:
1. Target a REAL metric that this service actually provides
2. Use the appropriate visualization type for the data
3. Have a sensible refresh interval
4. Include threshold values where applicable

Available widget types: gauge, line_chart, metric_card, event_timeline, 
status_grid, bar_chart

Respond with valid JSON only. No explanation.
```

### Validation Rules

The AI's output is validated before rendering:
1. Every `metric_key` must be a real metric the connector can produce
2. Every `type` must be a supported widget type
3. `refresh_interval` must be >= 10 seconds (prevent API spam)
4. No duplicate widget IDs
5. Grid positions must not overlap

Invalid widgets are silently dropped. If ALL are invalid, fall back to registry templates.

---

## Detailed Task List

### Phase A — Backend Widget Generator

- [ ] **A1. Create `prash/widget_generator.py`** with the `WidgetConfig` and `WidgetPosition` dataclasses
- [ ] **A2. Implement `generate_widget_config_from_template(connector_id)` function** — returns widget configs from the registry templates (Mode 1)
- [ ] **A3. Implement `generate_widget_config_from_ai(connector_id, resource_id)` function** — calls the LLM with the prompt template (Mode 2)
- [ ] **A4. Implement prompt builder** — gathers connector capabilities, available metrics, current state, and recent events to build the AI prompt
- [ ] **A5. Implement response parser** — parse the LLM's JSON response into `WidgetConfig` objects
- [ ] **A6. Implement validation** — validate each generated widget against the rules above
- [ ] **A7. Implement fallback chain** — Mode 2 → validation → if all invalid, Mode 1
- [ ] **A8. Create `POST /api/connectors/{id}/generate-widgets`** endpoint
- [ ] **A9. Cache generated configs** — save to `prash.yaml` per service so regeneration isn't needed every load

### Phase B — Frontend Widget Configurator

- [ ] **B1. Create `WidgetConfigurator.tsx`** — UI for viewing and customizing the widget layout
- [ ] **B2. "Generate Layout" button** — calls the AI generation endpoint
- [ ] **B3. Loading state** — "Lear is analyzing your service..." with shimmer
- [ ] **B4. Preview layout** — show the generated widgets in a preview before confirming
- [ ] **B5. Manual override** — user can add/remove/reorder widgets after AI generation
- [ ] **B6. Save layout** — persist the widget config for this service

### Phase C — Integration

- [ ] **C1. Auto-generate on first watch** — when a service is first watched, auto-generate widget config
- [ ] **C2. ServiceWidget uses generated config** — Feature 08's ServiceWidget reads the generated (or default) config
- [ ] **C3. Regenerate option** — "🔄 Regenerate Widgets" button to re-run AI analysis

---

## Testing Methodology

### Unit Tests

```
test_template_mode_returns_registry_templates
test_template_mode_handles_unknown_connector
test_ai_mode_builds_prompt_with_real_capabilities
test_ai_mode_builds_prompt_with_real_metrics
test_ai_mode_parses_valid_json_response
test_ai_mode_rejects_invalid_widget_type
test_ai_mode_rejects_invalid_metric_key
test_ai_mode_enforces_min_refresh_interval
test_ai_mode_rejects_duplicate_ids
test_ai_mode_falls_back_to_template_on_all_invalid
test_ai_mode_falls_back_to_template_on_llm_error
test_validation_allows_valid_config
test_validation_drops_invalid_widgets_keeps_valid
test_cache_persists_config
test_cache_loads_on_restart
```

### Anti-Hardcoding Test Suite

```
test_NO_HARDCODED_WIDGET_LAYOUT — The widget layout for a service 
    comes from either the AI generator or the registry templates, 
    never from hardcoded JSX in a React component.

test_AI_PROMPT_USES_REAL_DATA — The prompt sent to the LLM contains 
    actual connector capabilities and metric names, not placeholder 
    values. Mock the connector, verify the prompt contains the mock's 
    read_capabilities.

test_VALIDATION_AGAINST_REAL_CAPABILITIES — A generated widget with 
    metric_key "FakeMetric" is rejected because it doesn't exist in 
    the connector's actual metric list.

test_NO_HARDCODED_THRESHOLDS — Threshold values (warning, critical) 
    in generated widgets come from the AI or the registry, not from 
    hardcoded numbers in the frontend.

test_FALLBACK_IS_TEMPLATE_NOT_HARDCODED — When AI generation fails, 
    the fallback is the registry's widget_templates, not a hardcoded 
    widget array in the frontend.

test_GENERATED_CONFIG_IS_CACHED — After generation, the config is 
    saved and reloaded without calling the AI again.

test_AI_NOT_CALLED_UNNECESSARILY — If a cached config exists, the AI 
    is NOT called. Only explicit "Regenerate" triggers a new call.

test_DIFFERENT_RESOURCES_DIFFERENT_LAYOUTS — Generate configs for two 
    different resources on the same connector. If the AI mode is used, 
    the layouts should differ based on the resource's actual data.
```

### Integration Tests

```
test_FULL_GENERATION_FLOW — Connect AWS → select EC2 instance → 
    generate widgets → verify layout renders with real data

test_TEMPLATE_FALLBACK — Disable LLM access → generate widgets → 
    verify template-based layout renders correctly

test_REGENERATE — Generate → modify resource → regenerate → verify 
    new layout reflects changes
```

---

## Definition of Done

- [ ] Template mode generates valid widget configs from registry for all 13 connectors
- [ ] AI mode generates personalized configs using real connector data
- [ ] Validation rejects widgets with invalid metric_keys or types
- [ ] Fallback chain works: AI → validate → template fallback
- [ ] Generated configs cached in prash.yaml
- [ ] Frontend renders widgets from generated config, not hardcoded layout
- [ ] Anti-hardcoding tests all pass
