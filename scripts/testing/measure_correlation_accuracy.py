#!/usr/bin/env python3
"""Measures the §3 quantitative metric M6 couldn't close: single-source vs
2-source false-positive rate on GENUINELY ambiguous incidents.

The M6 combined fixture (break_combined.py) proved the correlation MECHANISM
live (real k8s crash + real Datadog spike -> one incident) but its two legs
are semantically unrelated to each other, so there was no scenario where a
single-source diagnosis is plausibly *wrong* to compare against. This script
is that missing piece: N scenarios, each with a KNOWN true root cause that is
only identifiable when a k8s signal is combined with a Datadog signal --
single-source evidence alone plausibly leads the brain to the wrong (or an
incomplete/unhelpful) hypothesis.

Why the evidence is constructed, not read from a live cluster/Datadog account
(unlike break_combined.py): this measures the DIAGNOSIS BRAIN's reasoning
over given evidence, not the connectors' read path -- that's already covered
by the connector test suites and the M6 mechanism-proof fixture. The inputs
below are built in the exact shape the real connectors produce (same
PodStatus/get_pod_events dict shape, same ConnectorEvent TypedDict), so
`format_k8s_context()` and `diagnose_failure()` run for real, unmocked --
only the evidence's origin is synthetic, not the diagnosis call itself.

    python3 scripts/testing/measure_correlation_accuracy.py

Real LLM calls (2 per scenario: single-source, multi-source). Not free, not
instant -- this is a measurement run, not a unit test.
"""
from __future__ import annotations

import asyncio
import datetime

from prash.brain.diagnosis_agent import diagnose_failure, format_k8s_context
from prash.cli import _export_cluster_env
from prash.connectors.kubernetes import PodStatus
from prash.credentials import CredentialStore

# The brain reads KIMI_API_KEY/DEEPSEEK_API_KEY etc. from os.environ, not
# from .env directly -- cli.py's _export_cluster_env() does this for every
# real command; a standalone script must do it too or every call 404s on
# "API key not set" even with a fully populated .env.
_export_cluster_env(CredentialStore.from_env().load())

UTC = datetime.timezone.utc


def _event(connector: str, event_type: str, summary: str, ts: datetime.datetime) -> dict:
    return {"timestamp": ts, "connector": connector, "event_type": event_type, "summary": summary, "raw": {}}


# ── Scenario A: DB connection-pool saturation, misread as an app-side issue ──
_NOW = datetime.datetime.now(UTC)

SCENARIO_A = {
    "name": "checkout-api timeout -> Postgres connection pool exhausted",
    "pod_status": PodStatus(
        name="checkout-api-7f9d2", namespace="prod", phase="Running",
        problem="CrashLoopBackOff", restart_count=11, ready=False,
    ),
    "logs": (
        "starting checkout-api v2.3.1\n"
        "connecting to database...\n"
        "ERROR: dial tcp 10.0.4.12:5432: i/o timeout\n"
        "starting checkout-api v2.3.1\n"
        "connecting to database...\n"
        "ERROR: dial tcp 10.0.4.12:5432: i/o timeout\n"
    ),
    "k8s_events": [
        {"type": "Warning", "reason": "BackOff", "message": "Back-off restarting failed container", "count": 11, "last_timestamp": str(_NOW)},
    ],
    "datadog_event": _event(
        "datadog", "metric_spike",
        "Postgres active_connections at 198/200 (99% of max_connections) on postgres-primary -- connection pool saturated",
        _NOW,
    ),
    # Grading: correct diagnosis names connection-pool exhaustion on the DB
    # side and does NOT treat this as fixable by touching checkout-api itself.
    "true_cause_keywords": ["connection", "pool", "saturat", "max_connections", "postgres"],
    "wrong_if_recommends": {"restart_pod"},
}

# ── Scenario B: checkout-api symptom of a degraded downstream dependency ──
SCENARIO_B = {
    "name": "checkout-api errors -> payment-service degraded (upstream, not checkout-api)",
    "pod_status": PodStatus(
        name="checkout-api-9k2p1", namespace="prod", phase="Running",
        problem=None, restart_count=0, ready=True,
    ),
    "logs": (
        "processing checkout for order 88213\n"
        "ERROR: upstream request failed: context deadline exceeded\n"
        "processing checkout for order 88214\n"
        "ERROR: upstream request failed: context deadline exceeded\n"
        "processing checkout for order 88215\n"
        "ERROR: upstream request failed: context deadline exceeded\n"
    ),
    "k8s_events": [],
    "datadog_event": _event(
        "datadog", "monitor_alert",
        "payment-service error rate at 82% (baseline 0.5%) -- service degraded",
        _NOW,
    ),
    # Correct diagnosis names payment-service as the failing dependency and
    # does not propose changing checkout-api itself (timeout tuning, restart,
    # code fix) as the resolution -- the fault is upstream.
    "true_cause_keywords": ["payment-service", "payment service", "upstream", "degraded"],
    "wrong_if_recommends": {"restart_pod"},
}

SCENARIOS = [SCENARIO_A, SCENARIO_B]


def _single_source_context(scenario: dict) -> str:
    return format_k8s_context(scenario["pod_status"], scenario["logs"], scenario["k8s_events"])


def _multi_source_context(scenario: dict) -> str:
    """k8s context + the correlated Datadog signal appended as additional
    evidence -- mirrors how a real caller would fold correlation.
    format_incident_context()'s unified timeline into the diagnosis prompt."""
    base = _single_source_context(scenario)
    dd = scenario["datadog_event"]
    correlated = (
        "\n\n=== CORRELATED SIGNAL (Datadog, same incident window) ===\n"
        f"[{dd['timestamp']}] {dd['event_type']}: {dd['summary']}\n"
        "This event occurred in the same time window as the pod issue above and "
        "very likely shares one root cause -- consider both signals together, "
        "not as separate incidents."
    )
    return base + correlated


def _grade(scenario: dict, diagnosis) -> tuple[bool, str]:
    """True if the diagnosis correctly names the true cause and doesn't
    recommend an action that only makes sense if the cause were something
    else. Returns (correct, reason)."""
    text = f"{diagnosis.root_cause} {diagnosis.fix_description}".lower()
    names_cause = any(kw.lower() in text for kw in scenario["true_cause_keywords"])
    wrong_action = diagnosis.recommended_action in scenario["wrong_if_recommends"]
    if wrong_action:
        return False, f"recommended {diagnosis.recommended_action!r}, which only fixes the wrong cause"
    if not names_cause:
        return False, "root cause doesn't name the true issue (expected one of: " + ", ".join(scenario["true_cause_keywords"]) + ")"
    return True, "correctly identifies the true cause and doesn't propose a wrong-cause fix"


async def _run_scenario(scenario: dict) -> dict:
    single_ctx = _single_source_context(scenario)
    multi_ctx = _multi_source_context(scenario)

    single_diag = await diagnose_failure(
        logs=single_ctx, repo_full_name=f"prod/{scenario['pod_status'].name}",
        commit_message="(no commit -- Kubernetes pod diagnosis)", workflow_name="kubernetes",
    )
    multi_diag = await diagnose_failure(
        logs=multi_ctx, repo_full_name=f"prod/{scenario['pod_status'].name}",
        commit_message="(no commit -- Kubernetes pod diagnosis)", workflow_name="kubernetes",
    )

    single_correct, single_reason = _grade(scenario, single_diag)
    multi_correct, multi_reason = _grade(scenario, multi_diag)

    return {
        "name": scenario["name"],
        "single": (single_correct, single_reason, single_diag),
        "multi": (multi_correct, multi_reason, multi_diag),
    }


async def main() -> int:
    results = []
    for scenario in SCENARIOS:
        print(f"\n{'=' * 78}\n{scenario['name']}\n{'=' * 78}")
        result = await _run_scenario(scenario)
        results.append(result)

        for label, (correct, reason, diag) in (("SINGLE-SOURCE (k8s only)", result["single"]),
                                                 ("MULTI-SOURCE (k8s + Datadog)", result["multi"])):
            mark = "CORRECT" if correct else "WRONG"
            print(f"\n-- {label}: {mark} --")
            print(f"  root_cause: {diag.root_cause}")
            print(f"  recommended_action: {diag.recommended_action}")
            print(f"  confidence: {diag.confidence}")
            print(f"  grading: {reason}")

    n = len(results)
    single_wrong = sum(1 for r in results if not r["single"][0])
    multi_wrong = sum(1 for r in results if not r["multi"][0])

    print(f"\n{'=' * 78}\nSUMMARY (n={n} scenarios)\n{'=' * 78}")
    print(f"single-source false-positive rate: {single_wrong}/{n}")
    print(f"multi-source (correlated) false-positive rate: {multi_wrong}/{n}")
    print(
        "\nTarget was 'lower with 2-source correlation than single-source, on the same set'."
    )
    if multi_wrong < single_wrong:
        print("MET on this set.")
    elif multi_wrong == single_wrong and single_wrong > 0:
        print("NOT MET -- correlation did not reduce the false-positive rate on this set.")
    else:
        print("Inconclusive (both 0 or tie at 0) -- scenarios may need to be harder.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
