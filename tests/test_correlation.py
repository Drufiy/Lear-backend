"""Multi-connector correlation (M6, CONNECTOR_REWRITE_SPEC §6/§7).

The spec's M6 acceptance: a pod crash coinciding with a Datadog metric spike
must yield ONE correlated incident, not two separate alerts. These pin that
join deterministically (no cluster, no Datadog needed — correlation is a pure
operation over the shared ConnectorEvent timeline). The live combined fixture
that produces the real events is scripts/testing/break_combined.py.
"""

from __future__ import annotations

import datetime

from prash.brain.correlation import (
    CorrelatedIncident,
    correlate,
    correlate_and_format,
    format_incident_context,
)

UTC = datetime.timezone.utc


def _event(connector, event_type, summary, ts):
    return {
        "timestamp": ts,
        "connector": connector,
        "event_type": event_type,
        "summary": summary,
        "raw": {},
    }


def _pod_crash(ts):
    return _event("kubernetes", "crashloopbackoff", "Pod checkout-api CrashLoopBackOff (restart_count=6)", ts)


def _datadog_spike(ts):
    return _event("datadog", "metric_spike", "checkout-api p99 latency spiked to 4200ms", ts)


# ── the M6 acceptance bar ──────────────────────────────────────────────────

def test_pod_crash_and_datadog_spike_within_window_is_one_incident():
    t = datetime.datetime(2026, 9, 6, 12, 0, 0, tzinfo=UTC)
    events = [
        _pod_crash(t),
        _datadog_spike(t + datetime.timedelta(seconds=8)),  # coincident
    ]
    incidents = correlate(events, window_seconds=120)

    assert len(incidents) == 1, "coinciding pod crash + spike must be ONE incident, not two"
    incident = incidents[0]
    assert incident.is_multi_source
    assert set(incident.connectors) == {"kubernetes", "datadog"}
    assert len(incident.events) == 2


def test_far_apart_events_are_separate_incidents():
    t = datetime.datetime(2026, 9, 6, 12, 0, 0, tzinfo=UTC)
    events = [
        _pod_crash(t),
        _datadog_spike(t + datetime.timedelta(minutes=30)),  # unrelated, later
    ]
    incidents = correlate(events, window_seconds=120)

    assert len(incidents) == 2
    assert all(not inc.is_multi_source for inc in incidents)


def test_single_connector_burst_is_not_multi_source():
    t = datetime.datetime(2026, 9, 6, 12, 0, 0, tzinfo=UTC)
    events = [
        _pod_crash(t),
        _event("kubernetes", "backoff", "Back-off restarting failed container", t + datetime.timedelta(seconds=5)),
    ]
    incidents = correlate(events)
    assert len(incidents) == 1
    assert incidents[0].is_multi_source is False
    assert incidents[0].connectors == ["kubernetes"]


def test_correlate_handles_naive_and_aware_timestamps_together():
    # k8s/AWS return tz-aware; some GCP paths return naive. They must still join.
    aware = datetime.datetime(2026, 9, 6, 12, 0, 0, tzinfo=UTC)
    naive = datetime.datetime(2026, 9, 6, 12, 0, 10)  # no tzinfo
    events = [_pod_crash(aware), _datadog_spike(naive)]
    incidents = correlate(events, window_seconds=120)
    assert len(incidents) == 1 and incidents[0].is_multi_source


def test_empty_events_returns_no_incidents():
    assert correlate([]) == []


def test_events_are_sorted_onto_one_timeline():
    t = datetime.datetime(2026, 9, 6, 12, 0, 0, tzinfo=UTC)
    # fed out of order
    events = [
        _datadog_spike(t + datetime.timedelta(seconds=8)),
        _pod_crash(t),
    ]
    incident = correlate(events)[0]
    assert incident.events[0]["connector"] == "kubernetes"  # earliest first
    assert incident.events[1]["connector"] == "datadog"


# ── the text the brain reads ───────────────────────────────────────────────

def test_format_incident_context_flags_multi_source_root_cause():
    t = datetime.datetime(2026, 9, 6, 12, 0, 0, tzinfo=UTC)
    incident = correlate([_pod_crash(t), _datadog_spike(t + datetime.timedelta(seconds=8))])[0]
    text = format_incident_context(incident)
    assert "CORRELATED INCIDENT" in text
    assert "kubernetes" in text and "datadog" in text
    assert "ONE root cause" in text
    assert "UNIFIED TIMELINE" in text


def test_correlate_and_format_lists_multi_source_first():
    t = datetime.datetime(2026, 9, 6, 12, 0, 0, tzinfo=UTC)
    events = [
        # a lone single-source incident earlier in time
        _event("snyk", "vuln", "new high-severity CVE", t - datetime.timedelta(hours=1)),
        # the correlated multi-source incident later
        _pod_crash(t),
        _datadog_spike(t + datetime.timedelta(seconds=8)),
    ]
    text = correlate_and_format(events)
    # multi-source block should appear before the single-source one despite
    # being later in time
    assert text.index("2 connectors") < text.index("Single-source")
