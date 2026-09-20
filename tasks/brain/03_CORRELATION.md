# Cross-Connector Correlation — `brain/correlation.py`

**Owner:** Aradhya  
**Status:** Foundation built, real correlation not yet proven  
**Priority:** Tier 1  
**Depends on:** `00_BASE_INTERFACE.md` (ConnectorEvent shape)  

---

## Goal

A pod crash + a Datadog metric spike + a recent deploy get recognized as **one** incident with one root cause, not three unrelated alerts. This is the competitive differentiator from the CONNECTOR_REWRITE_SPEC.

---

## Current State

`correlation.py` exists with basic structure. The 2026-09-07 measurement found: confidence rose 0.65→0.85 in one scenario with correlated signals, but false-positive gap didn't materialize because the brain is already conservative (declines to guess rather than guessing wrong).

---

## Tasks

### T1. Build shared timeline from `ConnectorEvent` streams
- [ ] Merge events from multiple connectors onto one UTC-normalized timeline
- [ ] Deduplicate events that describe the same underlying incident
- [ ] Window: configurable (default 5 minutes around the trigger event)

### T2. Temporal proximity correlation
- [ ] Events within the correlation window from different connectors → linked
- [ ] Scoring: time distance + event severity + connector relevance
- [ ] Output: `CorrelatedIncident` with `primary_event`, `supporting_events`, `confidence`

### T3. Resource-graph correlation
- [ ] Pod `api-xyz` → K8s namespace → linked Datadog monitors → linked PagerDuty services
- [ ] Map via: labels, tags, resource names, configured associations
- [ ] Fallback: name-based fuzzy matching when explicit links don't exist

### T4. Feed correlated context to diagnosis brain
- [ ] `format_correlated_context(incident: CorrelatedIncident) -> str`
- [ ] Include: primary event details + supporting evidence ranked by relevance
- [ ] Brain receives richer context → higher confidence → better recommendations

### T5. Construct ambiguous multi-signal test fixtures
- [ ] Scenario 1: Postgres connection pool saturation misread as network failure
- [ ] Scenario 2: Degraded downstream service misread as local problem
- [ ] Scenario 3: Deploy + pod crash + metric spike = one deploy-caused incident
- [ ] Measure: single-source accuracy vs. multi-source accuracy

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_timeline_merge` | `tests/test_correlation.py` | Events from multiple connectors merge correctly |
| `test_temporal_correlation` | `tests/test_correlation.py` | Near-simultaneous events are linked |
| `test_resource_graph` | `tests/test_correlation.py` | Pod → monitor → service mapping works |
| `test_correlated_context_format` | `tests/test_correlation.py` | Brain receives correct context |
| `test_single_vs_multi_source` | `tests/test_correlation.py` | Multi-source produces higher confidence |

---

## Success Metrics (from CONNECTOR_REWRITE_SPEC §3)

| Metric | Baseline | Target |
|---|---|---|
| Cold-start diagnosis time | 8.09s | Lower with warm `watch()` context |
| Single-source false-positive rate | 0% (but brain is conservative) | Measure specificity gain |
| Parallel vs sequential read latency | ~4ms per connector | Near-single-connector time |

---

## Acceptance Criteria

- [ ] `CorrelatedIncident` type defined and usable
- [ ] Timeline merge works across 2+ connector event streams
- [ ] At least one scenario where multi-source produces better diagnosis than single-source
- [ ] Metrics baseline measured, target proven
