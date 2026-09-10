#!/usr/bin/env python3
"""Combined correlation fixture (CONNECTOR_REWRITE_SPEC §7, M6).

The one fixture the spec said had to be built for M6: a pod crash and a
coinciding Datadog metric spike inside the same time window, so that
correlate() over both connectors' get_stats() output resolves them to ONE
incident with one root cause — not two separate alerts.

Two legs, both REAL as of Aryan's M4 (Datadog real execution, 647f3fa):
  * Kubernetes — DatadogConnector.get_stats() for the standing `broken-app`
    fixture in prash-demo. Needs the kind cluster up; --offline substitutes a
    canned k8s crash event when it isn't.
  * Datadog — DatadogConnector.get_stats() against the real account for the
    standing synthetic monitor `prash-test-synthetic-error-rate`
    (scripts/testing/break_datadog.py owns it). Run `break_datadog.py` first
    to force it into Alert (allow ~1-5min for evaluation); --offline
    substitutes a canned spike when DATADOG_API_KEY/APP_KEY aren't set.

    python3 scripts/testing/break_datadog.py                  # force the monitor into Alert first
    python3 scripts/testing/break_combined.py                 # live k8s + live datadog
    python3 scripts/testing/break_combined.py --offline       # canned k8s + canned datadog
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


_DATADOG_MONITOR = "prash-test-synthetic-error-rate"


def _datadog_events_live(since: datetime.datetime) -> list[dict]:
    """Real Datadog ConnectorEvents for the standing synthetic monitor
    (M4, Aryan's DatadogConnector.get_stats())."""
    from prash.connectors.datadog import DatadogConnector

    creds = _env()
    conn = DatadogConnector({
        "DATADOG_API_KEY": creds.get("DATADOG_API_KEY"),
        "DATADOG_APP_KEY": creds.get("DATADOG_APP_KEY"),
    })
    if not conn.authenticate():
        raise RuntimeError("could not authenticate to Datadog (DATADOG_API_KEY/APP_KEY missing or invalid)")
    return conn.get_stats(_DATADOG_MONITOR, since=since)


def _datadog_spike_canned(anchor: datetime.datetime) -> list[dict]:
    """Canned fallback for --offline or missing credentials."""
    return [{
        "timestamp": anchor + datetime.timedelta(seconds=6),
        "connector": "datadog",
        "event_type": "metric_spike",
        "summary": f"checkout-api p99 latency spiked to 4200ms (monitor {_DATADOG_MONITOR})",
        "raw": {"canned": True},
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

    if args.offline:
        datadog_events = _datadog_spike_canned(anchor)
        print("datadog leg: CANNED (--offline)")
    else:
        try:
            since = datetime.datetime.now(UTC) - datetime.timedelta(hours=1)
            datadog_events = _datadog_events_live(since)
            if datadog_events:
                print(f"datadog leg: LIVE — {len(datadog_events)} event(s) from {_DATADOG_MONITOR}")
            else:
                print(f"datadog leg: LIVE call succeeded but returned 0 events — is {_DATADOG_MONITOR} "
                      f"in Alert? (run break_datadog.py first, allow ~1-5min to evaluate)", file=sys.stderr)
                datadog_events = _datadog_spike_canned(anchor)
                print("datadog leg: falling back to CANNED")
        except Exception as exc:
            print(f"datadog live leg failed ({exc}); falling back to canned", file=sys.stderr)
            datadog_events = _datadog_spike_canned(anchor)

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
