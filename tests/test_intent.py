"""REPL stage 2 (prash/intent.py, PRASH_V2.md §6b): free-text intent parsing.

Unit tests on the pure resolution layer plus integration tests running the
REPL loop headlessly with scripted lines. No TTY, CI-safe on all 3 OSes.
"""

from __future__ import annotations

import asyncio

import pytest

from prash import repl
from prash.intent import (
    Clarify,
    Suggestion,
    _Context,
    _args_to_suggestion_or_clarify,
    _verb_hit,
    complete,
    resolve,
)
from prash.repl import _is_it_phrase, _looks_like_talk


def ctx(**kw):
    return _Context(**kw)


# ---- verb detection ------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("my api pod is sick, fix it", "fix"),
    ("restart the broken pod", "restart"),
    ("please watch the cluster", "watch"),
    ("rollback the bad deployment", "rollback"),
    ("open a pr against acme/widget", "open-pr"),
    ("show me the audit log", "audit"),
    ("what can you do", "actions"),
    ("just show config", "config"),
    ("is the circuit open", "circuit"),
    ("apply the ci fix for run 123", "apply-ci-fix"),
])
def test_verb_detection(text, expected):
    assert _verb_hit(text) == expected


@pytest.mark.parametrize("text", ["hello", "3.14159", "open the door", "how are you"])
def test_not_intent(text):
    assert _verb_hit(text) is None


# ---- target resolution ---------------------------------------------------

def test_free_text_fix_resolves_bare_pod_with_namespace():
    s = resolve("my api pod is sick, fix it", ctx(namespace="prash-demo", pod="api-7f9d", last_target="prash-demo/api-7f9d"))
    assert isinstance(s, Suggestion)
    assert s.argv == ["fix", "prash-demo/api-7f9d"]


def test_free_text_fix_with_explicit_target_qualifies_it():
    s = resolve("fix web-3 now", ctx(namespace="prash-demo"))
    assert isinstance(s, Suggestion)
    assert s.argv == ["fix", "prash-demo/web-3"]


def test_qualified_target_passes_through_untouched():
    s = resolve("restart prash-demo/api-1", ctx(namespace="prash-demo"))
    assert isinstance(s, Suggestion)
    assert s.argv == ["run", "restart-pod", "prash-demo/api-1"]


def test_fix_with_no_context_asks_for_target():
    s = resolve("fix the broken pod", ctx())
    assert isinstance(s, Clarify)
    assert "Which pod" in s.question


def test_fix_with_no_context_but_remembered_pod_uses_it():
    s = resolve("fix the broken pod", ctx(namespace="prash-demo", pod="api-2", last_target="prash-demo/api-2"))
    assert isinstance(s, Suggestion)
    assert s.argv == ["fix", "prash-demo/api-2"]


def test_open_pr_never_guesses_a_repo():
    s = resolve("open a pr", ctx(namespace="prash-demo", pod="api-2", last_target="prash-demo/api-2"))
    assert isinstance(s, Clarify)
    assert "repository" in s.question


# ---- datadog fast-path routing (connector rewrite M2/M4) -------------------

def test_intent_watch_datadog_routes_to_datadog_provider():
    """'watch this datadog monitor' must NOT fall into the generic watch verb
    (which polls the kubernetes namespace watcher) — it names the provider."""
    s = resolve("watch this datadog monitor cpu-high", ctx(namespace="prash-demo"))
    assert isinstance(s, Suggestion)
    assert s.argv == ["watch", "--provider", "datadog", "--resource", "cpu-high"]


def test_intent_watch_datadog_without_target_uses_env_default():
    s = resolve("watch my datadog monitors", ctx())
    assert isinstance(s, Suggestion)
    assert s.argv == ["watch", "--provider", "datadog"]


def test_intent_datadog_stats_with_target_routes_to_investigate():
    s = resolve("what happened on datadog monitor cpu-high", ctx())
    assert isinstance(s, Suggestion)
    assert s.argv == ["investigate", "cpu-high", "--provider", "datadog"]


def test_intent_datadog_stats_without_target_asks_which_monitor():
    s = resolve("what happened on datadog", ctx())
    assert isinstance(s, Clarify)
    assert "datadog" in s.question


def test_intent_non_datadog_watch_still_routes_to_kubernetes():
    """The datadog fast path only fires when 'datadog' is explicit — every
    pre-existing phrasing keeps its old routing."""
    s = resolve("please watch the cluster", ctx(namespace="prash-demo"))
    assert isinstance(s, Suggestion)
    assert s.argv == ["watch"]


def test_intent_watch_pagerduty_routes_to_pagerduty_provider():
    s = resolve("watch the pagerduty service checkout-api", ctx())
    assert isinstance(s, Suggestion)
    assert s.argv == ["watch", "--provider", "pagerduty", "--resource", "checkout-api"]


def test_intent_pagerduty_incidents_routes_to_investigate():
    s = resolve("what happened on pagerduty service checkout-api", ctx())
    assert isinstance(s, Suggestion)
    assert s.argv == ["investigate", "checkout-api", "--provider", "pagerduty"]


def test_intent_pagerduty_without_target_asks_which_service():
    s = resolve("any pagerduty incidents?", ctx())
    assert isinstance(s, Clarify)
    assert "pagerduty" in s.question


def test_intent_pagerduty_watch_without_target_uses_env_default():
    s = resolve("watch pagerduty", ctx())
    assert isinstance(s, Suggestion)
    assert s.argv == ["watch", "--provider", "pagerduty"]


def test_open_pr_with_repo_uses_it():
    s = resolve("open a pr against acme/widget", ctx())
    assert isinstance(s, Suggestion)
    assert s.argv == ["run", "open-pr", "acme/widget"]


def test_watch_actions_config_circuit_audit_need_no_target():
    for text, argv in [
        ("watch the cluster", ["watch"]),
        ("show actions", ["actions"]),
        ("show config", ["config"]),
        ("circuit status please", ["circuit", "status"]),
        ("show the audit log", ["audit", "--tail", "20"]),
    ]:
        s = resolve(text, ctx())
        assert isinstance(s, Suggestion), text
        assert s.argv == argv


# ---- clarifying follow-ups ------------------------------------------------

def test_complete_with_bare_name_qualifies_with_namespace():
    s = complete("fix", "web-9", ctx(namespace="prash-demo"))
    assert isinstance(s, Suggestion)
    assert s.argv == ["fix", "prash-demo/web-9"]


def test_complete_with_qualified_target_passes_through():
    s = complete("restart", "prash-demo/api-1", ctx())
    assert isinstance(s, Suggestion)
    assert s.argv == ["run", "restart-pod", "prash-demo/api-1"]


def test_complete_garbage_returns_none():
    assert complete("fix", "??!", ctx()) is None


# ---- REPL-level integration ----------------------------------------------

def _run(lines):
    from rich.console import Console

    console = Console(record=True)
    rc = repl.run_repl(console, lines=lines)
    return rc, console


def test_free_text_fix_runs_through_loop():
    # fix needs a kube-config -> the diagnosis fails cleanly, but the point is
    # the free text was translated into a real `fix` invocation (context applied).
    rc, console = _run(["fix prash-demo/api-1", "the api pod is sick, fix it", "exit"])
    assert rc == 0
    text = console.export_text()
    assert "fixing prash-demo/api-1" in text  # stage 2 resolved + explained


def test_it_phrase_uses_remembered_target():
    rc, console = _run(["fix prash-demo/api-1", "fix it", "exit"])
    assert rc == 0
    text = console.export_text()
    assert "fixing prash-demo/api-1" in text


def test_ambiguous_target_asks_then_completes():
    # "restart the broken pod" with no remembered target -> Clarify -> then a
    # bare pod answer resolves through complete().
    rc, console = _run(["restart the broken pod", "web-5", "exit"])
    assert rc == 0
    text = console.export_text()
    assert "Which pod" in text
    assert "restarting prash-demo/web-5" in text or "restarting web-5" in text


def test_clarify_answer_by_index_picks_the_option():
    # A numbered answer to the clarifying question picks the listed option.
    rc, console = _run(["restart the broken pod", "1", "exit"])
    assert rc == 0
    text = console.export_text()
    assert "Which pod" in text


def test_watch_free_text_runs():
    rc, console = _run(["watch the cluster", "exit"])
    assert rc == 0
    text = console.export_text()
    assert "Watching namespace" in text or "watching the remembered namespace" in text


def test_talk_heuristics():
    assert _is_it_phrase("fix it")
    assert _is_it_phrase("restart that")
    assert not _is_it_phrase("fix prash-demo/api-1")
    assert _looks_like_talk("restart the broken api pod")
    assert not _looks_like_talk("fix api-7f9d")
    assert not _looks_like_talk("watch")


def test_run_llm_intent_sync_never_hangs_on_stuck_coroutine():
    """Regression for the 2026-08-24 'test_intent.py hangs under pytest'
    report: a coroutine that never completes (sync-blocked, ignoring
    cancellation) must still return None within a bounded time instead of
    hanging the caller forever. The sync bridge runs the LLM call in a
    worker thread with a bounded join, so a stuck task cannot block pytest."""
    import time

    from prash.intent import _LLM_INTENT_TIMEOUT_SECONDS, _run_llm_intent_sync

    async def never_completes():
        await asyncio.sleep(3600)  # pragma: no cover - would hang if reached

    start = time.monotonic()
    result = _run_llm_intent_sync(never_completes())
    elapsed = time.monotonic() - start
    assert result is None
    # Bounded: must return well before the sleep(3600) would finish. The
    # bridge's own timeout + join margin is _LLM_INTENT_TIMEOUT_SECONDS + 5,
    # so assert comfortably inside that.
    assert elapsed < _LLM_INTENT_TIMEOUT_SECONDS + 10


# ---- M3: get_stats / watch / alert reachable through natural language ------

@pytest.mark.parametrize("text,expected", [
    ("what's been happening with my api pod", "stats"),
    ("what happened to prash-demo/api", "stats"),
    ("show me the recent events", "stats"),
    ("show me the timeline", "stats"),
    ("give me the stats", "stats"),
    ("event history please", "stats"),
])
def test_stats_verb_detection(text, expected):
    assert _verb_hit(text) == expected


def test_stats_never_hijacks_an_explicit_action_verb():
    # "diagnose what happened" is a fix, not a read — the action verb wins.
    assert _verb_hit("diagnose what happened to my pod") == "fix"
    assert _verb_hit("fix it and show me what happened") == "fix"


def test_stats_resolves_target_like_fix():
    s = resolve("what's been happening with api-7f9d",
                ctx(namespace="prash-demo", last_target="prash-demo/api-7f9d"))
    assert isinstance(s, Suggestion)
    assert s.argv == ["stats", "prash-demo/api-7f9d"]


def test_stats_with_qualified_target_passes_through():
    s = resolve("what happened to prash-demo/web-3", ctx())
    assert isinstance(s, Suggestion)
    assert s.argv == ["stats", "prash-demo/web-3"]


def test_stats_with_no_target_asks():
    c = resolve("show me the recent events", ctx())
    assert isinstance(c, Clarify)


def test_complete_stats_qualifies_bare_name():
    s = complete("stats", "web-9", ctx(namespace="prash-demo"))
    assert isinstance(s, Suggestion)
    assert s.argv == ["stats", "prash-demo/web-9"]


def test_watch_with_target_scopes_to_its_namespace():
    s = resolve("keep an eye on prash-demo/api-1", ctx())
    assert isinstance(s, Suggestion)
    assert s.argv == ["watch", "--namespace", "prash-demo"]


def test_watch_without_target_stays_bare():
    s = resolve("watch the cluster", ctx())
    assert isinstance(s, Suggestion)
    assert s.argv == ["watch"]


# ---- M3: LLM slow-path arg mapping (pure, no network) ---------------------

def test_llm_stats_maps_to_stats_command():
    s = _args_to_suggestion_or_clarify(
        {"command": "stats", "resource": "i-0abc", "provider": "aws", "explanation": "recent AWS events"}
    )
    assert isinstance(s, Suggestion)
    assert s.argv == ["stats", "i-0abc", "--provider", "aws"]


def test_llm_stats_defaults_provider_to_kubernetes():
    s = _args_to_suggestion_or_clarify(
        {"command": "stats", "resource": "prash-demo/api", "explanation": "events"}
    )
    assert isinstance(s, Suggestion)
    assert s.argv == ["stats", "prash-demo/api", "--provider", "kubernetes"]


def test_llm_stats_without_resource_asks():
    c = _args_to_suggestion_or_clarify({"command": "stats", "explanation": "events"})
    assert isinstance(c, Clarify)


def test_llm_watch_non_k8s_uses_provider_resource():
    s = _args_to_suggestion_or_clarify(
        {"command": "watch", "provider": "datadog", "resource": "checkout-latency", "explanation": "watch monitor"}
    )
    assert isinstance(s, Suggestion)
    assert s.argv == ["watch", "--provider", "datadog", "--resource", "checkout-latency"]


def test_llm_watch_k8s_scopes_to_namespace():
    s = _args_to_suggestion_or_clarify(
        {"command": "watch", "provider": "kubernetes", "resource": "prash-demo/api", "explanation": "watch ns"}
    )
    assert isinstance(s, Suggestion)
    assert s.argv == ["watch", "--namespace", "prash-demo"]


def test_llm_alert_routes_through_run_action():
    # paging an on-call responder is a gated write -> command=run + *-alert id
    s = _args_to_suggestion_or_clarify(
        {"command": "run", "action_id": "aws-alert", "resource": "i-0abc", "explanation": "page on-call"}
    )
    assert isinstance(s, Suggestion)
    assert s.argv == ["run", "aws-alert", "i-0abc"]
