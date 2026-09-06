#!/usr/bin/env python3
"""Combined correlation fixture (CONNECTOR_REWRITE_SPEC §7, M6).

The one fixture the spec said had to be built for M6: a pod crash and a
coinciding Datadog metric spike inside the same time window, so that
correlate() over both connectors' get_stats() output resolves them to ONE
incident with one root cause — not two separate alerts.

Two legs:
  * Kubernetes — REAL. Reads KubernetesConnector.get_stats() for a
    crash-looping pod (the standing `broken-app` fixture in prash-demo). Needs
    the kind cluster up; use --offline to substitute a canned k8s crash event
    when it isn't (Datadog real execution — M4 — isn't landed yet either, so
    the Datadog leg is stubbed regardless; the join is identical either way).
  * Datadog — STUBBED. A canned metric_spike ConnectorEvent timestamped to
    coincide with the k8s crash. Swap this for DatadogConnector.get_stats()
    once M4 lands; correlate() doesn't care where the events came from.

    python3 scripts/testing/break_combined.py                 # live k8s + stub datadog
    python3 scripts/testing/break_combined.py --offline       # canned k8s + stub datadog
    python3 scripts/testing/break_combined.py --namespace prash-demo --pod <name>

Exit 0 when the two legs correlate into exactly one multi-source incident.
"""
from __future__ import annotations

import argparse
import datetime
import sys

from prash.brain.correlation import correlate, format_incident_context

UTC = datetime.timezone.utc


def _env(path: str = ".env") -> dict:
    out = {}
    try:
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return out


def _k8s_events_live(namespace: str, pod: str) -> list[dict]:
    """Real k8s ConnectorEvents for the crash-looping pod, last 30 minutes."""
    from prash.connectors.kubernetes import KubernetesConnector

    creds = _env()
    conn = KubernetesConnector({
        "KUBE_CONTEXT": creds.get("KUBE_CONTEXT"),
        "KUBE_NAMESPACE": namespace,
    })
    if not conn.authenticate():
        raise RuntimeError("could not authenticate to the cluster (is kind-prash-dev up?)")
    since = datetime.datetime.now(UTC) - datetime.timedelta(minutes=30)
    return conn.get_stats(f"{namespace}/{pod}", since=since)


def _k8s_event_canned() -> list[dict]:
    """A canned k8s crash event for --offline runs (no cluster)."""
    now = datetime.datetime.now(UTC)
    return [{
        "timestamp": now,
        "connector": "kubernetes",
        "event_type": "backoff",
        "summary": "Back-off restarting failed container checkout-api in pod checkout-api-xxxx",
        "raw": {"reason": "BackOff"},
    }]


def _datadog_spike_stub(anchor: datetime.datetime) -> list[dict]:
    """STUB (M4 pending): a Datadog metric spike coinciding with the crash."""
    return [{
        "timestamp": anchor + datetime.timedelta(seconds=6),
        "connector": "datadog",
        "event_type": "metric_spike",
        "summary": "checkout-api p99 latency spiked to 4200ms (monitor prash-test-synthetic-error-rate)",
        "raw": {"stubbed": True, "note": "replace with DatadogConnector.get_stats() when M4 lands"},
    }]


def _auto_pod(namespace: str) -> str | None:
    try:
        import subprocess
        out = subprocess.run(
            ["kubectl", "get", "pods", "-n", namespace, "--no-headers", "-o",
             "custom-columns=NAME:.metadata.name"],
            capture_output=True, text=True, timeout=10,
        ).stdout
        for line in out.splitlines():
            if "broken-app" in line:
                return line.strip()
    except Exception:
        pass
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Combined k8s+Datadog correlation fixture (M6)")
    ap.add_argument("--namespace", default="prash-demo")
    ap.add_argument("--pod", default=None, help="crash-looping pod (default: auto-detect broken-app)")
    ap.add_argument("--offline", action="store_true", help="use a canned k8s event instead of the live cluster")
    ap.add_argument("--window", type=int, default=120, help="correlation window seconds")
    args = ap.parse_args()

    if args.offline:
        k8s_events = _k8s_event_canned()
        print("k8s leg: CANNED (--offline)")
    else:
        pod = args.pod or _auto_pod(args.namespace)
        if not pod:
            print("no crash-looping pod found; is the cluster up? falling back to --offline", file=sys.stderr)
            k8s_events = _k8s_event_canned()
        else:
            try:
                k8s_events = _k8s_events_live(args.namespace, pod)
                print(f"k8s leg: LIVE — {len(k8s_events)} event(s) from {args.namespace}/{pod}")
            except Exception as exc:
                print(f"k8s live leg failed ({exc}); falling back to canned", file=sys.stderr)
                k8s_events = _k8s_event_canned()

    if not k8s_events:
        print("no k8s events to anchor on; cannot build the combined incident", file=sys.stderr)
        return 1

    anchor = max(e["timestamp"] for e in k8s_events)
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=UTC)
    datadog_events = _datadog_spike_stub(anchor)
    print("datadog leg: STUBBED (M4 real execution pending)")

    all_events = list(k8s_events) + list(datadog_events)
    incidents = correlate(all_events, window_seconds=args.window)

    print("\n" + "=" * 70)
    for inc in incidents:
        print(format_incident_context(inc))
        print("-" * 70)

    multi = [i for i in incidents if i.is_multi_source]
    if len(multi) == 1 and {"kubernetes", "datadog"} <= set(multi[0].connectors):
        print("\nOK — one correlated incident spanning kubernetes + datadog (M6 acceptance met).")
        return 0
    print(f"\nFAIL — expected 1 multi-source incident, got {len(multi)}.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
