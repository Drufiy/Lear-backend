# Feature 08 — Dynamic Metric Widgets

**Priority:** P0 — the killer demo feature  
**Owner:** TBD  
**Depends on:** `01_BACKEND_API_BRIDGE.md`, `02_CONNECTOR_REGISTRY.md`, `07_PROJECT_SYSTEM.md`  
**Target files:**  
- `desktop/src/components/ServiceWidget.tsx` (new — orchestrator)  
- `desktop/src/components/widgets/MetricGauge.tsx` (new)  
- `desktop/src/components/widgets/MetricLineChart.tsx` (new)  
- `desktop/src/components/widgets/MetricCard.tsx` (new)  
- `desktop/src/components/widgets/EventTimeline.tsx` (new)  
- `desktop/src/components/widgets/StatusGrid.tsx` (new)  
- `desktop/src/components/widgets/BarChart.tsx` (new)  
**Test file:** `desktop/src/__tests__/widgets/*.test.tsx` (new)

---

## Product Spec

When you connect a service (e.g., an AWS EC2 instance), Lear creates dynamic widgets that visualize all relevant metrics for that specific resource. The widget types are determined by the **Connector Registry's widget_templates**, not hardcoded in React components.

### The Widget System Architecture

```
Connector Registry
    │
    ├── widget_templates: [
    │     {id: "cpu", type: "gauge", metric_keys: ["CPUUtilization"]},
    │     {id: "network", type: "line_chart", metric_keys: ["NetworkIn", "NetworkOut"]},
    │   ]
    │
    ▼
ServiceWidget.tsx (orchestrator)
    │
    ├── Reads widget_templates for this connector
    ├── Fetches live data from /api/connectors/{id}/metrics
    ├── Maps each template to the correct widget component
    │
    ▼
┌──────────┐ ┌──────────────┐ ┌──────────┐ ┌───────────────┐
│MetricGauge│ │MetricLineChart│ │MetricCard│ │EventTimeline  │
│(gauge)    │ │(line_chart)   │ │(metric)  │ │(event_timeline│
└──────────┘ └──────────────┘ └──────────┘ └───────────────┘
```

### Widget Types

#### 1. MetricGauge (`type: "gauge"`)
A radial gauge showing a single metric as a percentage (0-100).

**Use cases**: CPU utilization, memory usage, disk utilization, capacity percentage  
**Visual**: Animated SVG arc with current value, min/max labels, color gradient (green → yellow → red)  
**Data**: Single numeric value + unit from `get_stats()` response  

```
        ╭──────────╮
       ╱            ╲
      │    73.2%     │
      │     CPU      │
       ╲            ╱
        ╰──────────╯
```

#### 2. MetricLineChart (`type: "line_chart"`)
A time-series line chart with multiple data series.

**Use cases**: Network I/O over time, request latency, error rate trends, build durations  
**Visual**: SVG path with bezier smoothing, gradient fill under the line, tooltip on hover, auto-scaling Y-axis  
**Data**: Array of `{timestamp, value}` points from `get_stats()`  

```
  100│         ╱╲
     │    ╱╲  ╱  ╲    ╱
   50│╲  ╱  ╲╱    ╲╱╲╱
     │ ╲╱
    0│_____________________
     0   5   10   15   20  min
```

#### 3. MetricCard (`type: "metric_card"`)
A compact numeric display with trend indicator.

**Use cases**: Request count, error count, uptime percentage, response time  
**Visual**: Large number, unit label, trend arrow (↑/↓), sparkline miniature chart, comparison to previous period  
**Data**: Current value + historical values for trend calculation  

```
┌─────────────────┐
│  Requests/min   │
│  1,247  ↑12%    │
│  ▁▂▃▅▆▇█▆▅▃▂▁  │
└─────────────────┘
```

#### 4. EventTimeline (`type: "event_timeline"`)
A vertical timeline of recent events.

**Use cases**: CloudWatch alarms, pod restarts, deployment events, CI runs, incidents  
**Visual**: Vertical line with event dots, each event has timestamp + summary + severity color  
**Data**: Array of `ConnectorEvent` from `get_stats()`  

```
  ● 2m ago   Instance status check passed
  ◉ 15m ago  CPU spike: 94% for 3 minutes
  ● 1h ago   Security group rule added
  ● 3h ago   Instance started
```

#### 5. StatusGrid (`type: "status_grid"`)
A grid of items with individual status indicators.

**Use cases**: K8s pod grid, Datadog monitor grid, GitHub workflow list  
**Visual**: Grid of small cards, each with name + status dot  
**Data**: Array of `{name, status}` from connector  

```
┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐
│api-1│ │api-2│ │db-1 │ │wrk-1│
│ ●   │ │ ●   │ │ ◉   │ │ ●   │
└─────┘ └─────┘ └─────┘ └─────┘
```

#### 6. BarChart (`type: "bar_chart"`)
A horizontal or vertical bar chart.

**Use cases**: Vulnerability severity breakdown, resource allocation, per-region distribution  
**Visual**: Animated bars with labels and values  
**Data**: Array of `{label, value}` pairs  

### Widget Templates Per Connector (AWS focused for demo)

#### AWS EC2 — Primary Demo Target
| Widget ID | Type | Metric Keys | Label | Refresh |
|---|---|---|---|---|
| `aws_cpu` | `gauge` | `CPUUtilization` | CPU Utilization | 30s |
| `aws_network_io` | `line_chart` | `NetworkIn`, `NetworkOut` | Network I/O | 30s |
| `aws_disk_ops` | `line_chart` | `DiskReadOps`, `DiskWriteOps` | Disk Operations | 60s |
| `aws_status_checks` | `metric_card` | `StatusCheckFailed` | Status Checks | 30s |
| `aws_instance_state` | `metric_card` | `instance_state` | Instance State | 15s |
| `aws_alarms` | `event_timeline` | `alarm_*` | CloudWatch Alarms | 60s |
| `aws_network_packets` | `line_chart` | `NetworkPacketsIn`, `NetworkPacketsOut` | Network Packets | 60s |

#### Kubernetes
| Widget ID | Type | Metric Keys | Label |
|---|---|---|---|
| `k8s_pod_status` | `status_grid` | `pod_status` | Pod Health |
| `k8s_restarts` | `metric_card` | `restart_count` | Restart Count |
| `k8s_events` | `event_timeline` | `pod_event` | Recent Events |

#### GitHub Actions
| Widget ID | Type | Metric Keys | Label |
|---|---|---|---|
| `gh_workflow_status` | `status_grid` | `workflow_status` | Workflows |
| `gh_success_rate` | `gauge` | `success_rate` | Success Rate |
| `gh_build_time` | `line_chart` | `build_duration` | Build Duration Trend |
| `gh_recent_runs` | `event_timeline` | `workflow_run` | Recent Runs |

#### Datadog
| Widget ID | Type | Metric Keys | Label |
|---|---|---|---|
| `dd_monitors` | `status_grid` | `monitor_status` | Monitors |
| `dd_alerts` | `event_timeline` | `monitor_alert` | Alert History |

#### (Templates for Azure, GCP, Vercel, GitLab, Grafana, PagerDuty, Snyk, Gitleaks, Terraform follow the same pattern — defined in the Connector Registry, not in frontend code)

### Data Flow for Rendering

```
1. ServiceWidget receives connector_id + resource_id
2. Fetches widget_templates from /api/connectors (cached)
3. Fetches metrics from /api/connectors/{id}/metrics?resource={resource_id}
4. For each widget_template:
   a. Filter metrics by template.metric_keys
   b. Render the widget component matching template.type
   c. Set up polling interval per template.refresh_interval
5. Auto-refresh: each widget polls independently at its own interval
```

### Widget Expand View

Clicking a widget expands it to a full-screen overlay showing:
- Larger chart/gauge
- More historical data (1h / 6h / 24h / 7d selector)
- Raw data table
- "Open Chat" button to ask AI about this specific metric

---

## Detailed Task List

### Phase A — Widget Components (pure rendering, no data fetching)

- [ ] **A1. Create `MetricGauge.tsx`** — SVG radial gauge, animated arc, value label, unit, color-coded
- [ ] **A2. Create `MetricLineChart.tsx`** — SVG time-series chart, bezier curves, gradient fill, tooltip, auto-scale Y
- [ ] **A3. Create `MetricCard.tsx`** — large number, trend arrow, sparkline, unit label
- [ ] **A4. Create `EventTimeline.tsx`** — vertical timeline, event dots, timestamps, summary text, severity colors
- [ ] **A5. Create `StatusGrid.tsx`** — grid of small status cards, name + dot
- [ ] **A6. Create `BarChart.tsx`** — horizontal/vertical bars, labels, values, animated entrance

### Phase B — Widget Orchestration

- [ ] **B1. Create `ServiceWidget.tsx`** — the orchestrator that:
  - Receives `connector_id`, `resource_id`, `display_name`
  - Fetches widget_templates from the connector registry
  - Fetches live metrics from the API
  - Maps each template to the correct widget component
  - Sets up polling intervals
- [ ] **B2. Widget type mapping** — `{ "gauge": MetricGauge, "line_chart": MetricLineChart, ... }`
- [ ] **B3. Loading state** — shimmer/skeleton while metrics are fetching
- [ ] **B4. Error state** — "Unable to fetch metrics" with retry button (never fake data)
- [ ] **B5. Empty state** — "No data available" when metrics are empty (not a zero-value gauge)

### Phase C — Data Integration

- [ ] **C1. Implement metric data parser** — convert `/api/connectors/{id}/metrics` response into widget-specific data shapes
- [ ] **C2. Gauge data adapter** — extract single numeric value + max for percentage
- [ ] **C3. Line chart data adapter** — extract time-series arrays with timestamps
- [ ] **C4. Event timeline data adapter** — map `ConnectorEvent[]` to timeline entries
- [ ] **C5. Status grid data adapter** — extract name+status pairs from connector response
- [ ] **C6. Auto-refresh system** — each widget polls at its template's `refresh_interval`, with jitter to prevent thundering herd
- [ ] **C7. Data caching** — cache recent data points so charts have history across refreshes

### Phase D — Interaction

- [ ] **D1. Widget expand** — click to expand to full-screen overlay
- [ ] **D2. Time range selector** — 10m / 1h / 6h / 24h / 7d
- [ ] **D3. Tooltip on hover** — show exact value + timestamp for line charts
- [ ] **D4. "Open Chat" from widget** — opens AI chat pre-loaded with this widget's data context
- [ ] **D5. Widget header** — connector icon, label, last-updated timestamp, refresh indicator

### Phase E — AWS-Specific Demo Polish

- [ ] **E1. AWS CPU gauge** — fetches real CloudWatch CPUUtilization
- [ ] **E2. AWS Network I/O chart** — real NetworkIn/NetworkOut time series
- [ ] **E3. AWS Disk Ops chart** — real DiskReadOps/DiskWriteOps
- [ ] **E4. AWS Status Checks card** — real StatusCheckFailed count
- [ ] **E5. AWS Instance State card** — real instance state (running/stopped/etc.)
- [ ] **E6. AWS CloudWatch Alarms timeline** — real alarm history
- [ ] **E7. Verify ALL data is from CloudWatch API** — no hardcoded values anywhere

---

## Testing Methodology

### Unit Tests (per widget component)

```
# MetricGauge
test_gauge_renders_value_at_0_percent
test_gauge_renders_value_at_50_percent
test_gauge_renders_value_at_100_percent
test_gauge_shows_unit_label
test_gauge_animates_on_value_change
test_gauge_color_green_below_70
test_gauge_color_yellow_between_70_and_90
test_gauge_color_red_above_90

# MetricLineChart
test_line_chart_renders_single_series
test_line_chart_renders_multiple_series
test_line_chart_handles_empty_data
test_line_chart_auto_scales_y_axis
test_line_chart_shows_tooltip_on_hover
test_line_chart_updates_with_new_data
test_line_chart_gradient_fill

# MetricCard
test_metric_card_shows_value
test_metric_card_shows_unit
test_metric_card_shows_trend_up_arrow
test_metric_card_shows_trend_down_arrow
test_metric_card_sparkline_renders
test_metric_card_handles_zero_value

# EventTimeline
test_timeline_renders_events_chronologically
test_timeline_shows_timestamps
test_timeline_shows_event_summaries
test_timeline_color_codes_severity
test_timeline_handles_empty_events

# StatusGrid
test_status_grid_renders_items
test_status_grid_correct_status_dots
test_status_grid_handles_many_items

# ServiceWidget (orchestrator)
test_service_widget_fetches_templates_from_registry
test_service_widget_fetches_metrics_from_api
test_service_widget_renders_correct_widget_types
test_service_widget_shows_loading_state
test_service_widget_shows_error_state_on_api_failure
test_service_widget_polls_at_template_interval
test_service_widget_stops_polling_on_unmount
```

### Anti-Hardcoding Test Suite

```
test_NO_HARDCODED_WIDGET_LAYOUT — ServiceWidget does NOT contain 
    connector-specific rendering logic (e.g., no `if (connector === 'aws') 
    { render gauge }`). It renders purely from widget_templates.

test_NO_HARDCODED_METRIC_VALUES — Every value displayed in every widget 
    comes from the API response. Mock the API to return specific values 
    and assert the widget displays EXACTLY those values, not defaults.

test_NO_HARDCODED_COLORS_IN_WIDGETS — Widget colors for status/severity 
    come from the design system CSS variables, not inline hex codes.

test_NO_HARDCODED_CHART_DATA — Line chart data points are EXACTLY the 
    API response data. No synthetic/demo data generation in the frontend.

test_NO_HARDCODED_LABELS — Widget labels (e.g., "CPU Utilization") come 
    from the widget template's `label` field, not from the component.

test_NO_HARDCODED_INTERVALS — Refresh intervals come from the widget 
    template's `refresh_interval`, not from a hardcoded `setInterval(30000)`.

test_WIDGET_TYPE_MAPPING_COMPLETE — Every `type` value that exists in 
    any connector's widget_templates has a corresponding React component 
    in the type mapping.

test_EMPTY_DATA_SHOWS_EMPTY_NOT_ZERO — When the API returns no data 
    points, the widget shows "No data" — NOT a zero-value gauge or 
    flat-line chart.

test_ERROR_SHOWS_ERROR_NOT_CACHED — When the API call fails, the widget 
    shows an error state, not stale cached data presented as current.

test_GAUGE_VALUES_FROM_API — Render a gauge with a mock API returning 
    CPU=73.2. Assert the gauge displays "73.2%". Change mock to 
    CPU=41.8. Assert the gauge displays "41.8%". The component must 
    not contain either number.

test_NEW_WIDGET_TYPE_RENDERS — Add a new widget_template with type 
    "donut_chart" to the registry. Verify ServiceWidget either renders 
    a fallback widget or gracefully handles the unknown type — never 
    crashes.
```

### Performance Tests

```
test_WIDGET_POLL_MEMORY — Start ServiceWidget, let it poll 100 times, 
    verify no memory leak (data arrays don't grow unbounded).

test_WIDGET_UNMOUNT_CLEANUP — Mount and unmount ServiceWidget 50 times, 
    verify all intervals/subscriptions are cleaned up.

test_CHART_RENDER_PERFORMANCE — Render a line chart with 1000 data 
    points, verify render time < 100ms.
```

---

## Definition of Done

- [ ] All 6 widget types render correctly with real data
- [ ] ServiceWidget dynamically renders widgets from registry templates — zero connector-specific code
- [ ] AWS EC2 demo shows: CPU gauge, Network chart, Disk chart, Status card, Instance state, Alarm timeline
- [ ] All widget data comes from live API calls — no hardcoded values
- [ ] Auto-refresh at per-widget intervals
- [ ] Loading, error, and empty states handled correctly
- [ ] Widget expand view with time range selector
- [ ] Anti-hardcoding tests all pass
