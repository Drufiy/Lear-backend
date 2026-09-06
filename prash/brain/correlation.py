"""Multi-connector correlation (CONNECTOR_REWRITE_SPEC §4c/§6, M6).

The competitive bet in one function: a pod crash, a Datadog metric spike, and a
recent deploy that all happen inside the same minute are ONE incident with one
root cause — not three unrelated alerts. Every connector already emits the same
`ConnectorEvent` shape (base.py §4c: timestamp/connector/event_type/summary/raw),
so correlation is a pure operation over that shared timeline: merge events from
N connectors, sort by time, and cluster the ones that coincide.

This module is deliberately pure and connector-agnostic — it takes events that
were already fetched via each connector's get_stats() and joins them. It does no
I/O and imports no connector, so it's unit-testable headlessly and works the
moment any two connectors return events on the same clock (real Datadog is M4;
until then the same logic runs against a stubbed Datadog get_stats — the join
doesn't care where the events came from).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field

# ConnectorEvent is a TypedDict (base.py §4c); at runtime it's a plain dict, so
# this module only ever does dict access on events.
ConnectorEvent = dict

# Default: events within two minutes of each other are treated as coincident.
# A pod's CrashLoopBackOff and the metric spike it causes land seconds apart in
# practice; two minutes is generous without chaining genuinely separate
# incidents together.
DEFAULT_WINDOW_SECONDS = 120


def _as_utc(ts: datetime.datetime) -> datetime.datetime:
    """Normalize to tz-aware UTC so events from connectors that return naive
    timestamps (some GCP paths) sort and subtract cleanly against tz-aware
    ones (k8s, AWS)."""
    if ts.tzinfo is None:
        return ts.replace(tzinfo=datetime.timezone.utc)
    return ts.astimezone(datetime.timezone.utc)


@dataclass
class CorrelatedIncident:
    """A cluster of ConnectorEvents that coincide in time and therefore likely
    share one root cause. `connectors` is the distinct set involved, in the
    order first seen on the timeline."""

    events: list[ConnectorEvent]
    connectors: list[str] = field(default_factory=list)

    @property
    def start(self) -> datetime.datetime:
        return _as_utc(self.events[0]["timestamp"])

    @property
    def end(self) -> datetime.datetime:
        return _as_utc(self.events[-1]["timestamp"])

    @property
    def is_multi_source(self) -> bool:
        """True when the incident spans >=2 connectors — the case where
        correlation changes the diagnosis (cross-check beats single source)."""
        return len(self.connectors) >= 2


def _make_incident(events: list[ConnectorEvent]) -> CorrelatedIncident:
    connectors: list[str] = []
    for e in events:
        c = e.get("connector", "unknown")
        if c not in connectors:
            connectors.append(c)
    return CorrelatedIncident(events=list(events), connectors=connectors)


def correlate(
    events: list[ConnectorEvent],
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
) -> list[CorrelatedIncident]:
    """Merge ConnectorEvents from any number of connectors onto one timeline and
    cluster the ones that coincide. Events (from any mix of connectors) that are
    within `window_seconds` of the running cluster join it; a larger gap starts a
    new incident. Returns incidents in chronological order.

    The join is what makes "pod crash + Datadog spike" resolve to ONE incident
    with two connectors instead of two separate single-source alerts.
    """
    if not events:
        return []

    ordered = sorted(events, key=lambda e: _as_utc(e["timestamp"]))
    incidents: list[CorrelatedIncident] = []
    cluster: list[ConnectorEvent] = [ordered[0]]

    for event in ordered[1:]:
        gap = (_as_utc(event["timestamp"]) - _as_utc(cluster[-1]["timestamp"])).total_seconds()
        if gap <= window_seconds:
            cluster.append(event)
        else:
            incidents.append(_make_incident(cluster))
            cluster = [event]
    incidents.append(_make_incident(cluster))
    return incidents


def format_incident_context(incident: CorrelatedIncident) -> str:
    """Render one correlated incident as the unified-timeline text block the
    diagnosis brain reads — so a multi-source incident is presented as a single
    thing to diagnose, not N separate log streams. Mirrors the =SECTION= style
    of diagnosis_agent.py's format_*_context helpers."""
    n_conn = len(incident.connectors)
    header = (
        f"=== CORRELATED INCIDENT ({len(incident.events)} events across "
        f"{n_conn} connector{'s' if n_conn != 1 else ''}: {', '.join(incident.connectors)}) ==="
    )
    lines = [header, "", "=== UNIFIED TIMELINE ==="]
    for e in incident.events:
        ts = _as_utc(e["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"- {ts} [{e.get('connector', '?')}/{e.get('event_type', '?')}] {e.get('summary', '')}")
    lines.append("")
    if incident.is_multi_source:
        lines.append(
            "These events span multiple connectors within one time window and "
            "very likely share ONE root cause — diagnose them together as a "
            "single incident, cross-checking the signals, not as separate alerts."
        )
    else:
        lines.append(
            "Single-source incident — no corroborating signal from another "
            "connector in this window."
        )
    return "\n".join(lines)


def correlate_and_format(
    events: list[ConnectorEvent],
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
) -> str:
    """Convenience: correlate, then render every incident into one block for the
    brain. Multi-source incidents are listed first — they're the ones where
    correlation improves the diagnosis."""
    incidents = correlate(events, window_seconds=window_seconds)
    incidents.sort(key=lambda inc: (not inc.is_multi_source, inc.start))
    return "\n\n".join(format_incident_context(inc) for inc in incidents)
