"""REPL stage 1 (prash/repl.py, PRASH_V2.md §6b): the persistent interactive
session. Kept headless — the loop takes an iterable of lines for tests, so no
TTY is needed and it is CI-safe on all three OSes.
"""

from __future__ import annotations

from argparse import Namespace

from prash import repl
from prash.repl import ReplSession


def _session():
    from rich.console import Console

    return ReplSession(Console(record=True))


def test_apply_context_resolves_bare_pod_with_remembered_namespace():
    s = _session()
    s.namespace = "production"
    args = Namespace(command="fix", target="api-7f9d")
    s.apply_context(args)
    assert args.target == "production/api-7f9d"


def test_apply_context_leaves_full_target_alone():
    s = _session()
    s.namespace = "production"
    args = Namespace(command="fix", target="staging/api-1")
    s.apply_context(args)
    assert args.target == "staging/api-1"


def test_apply_context_does_not_namespace_non_pod_run_action():
    s = _session()
    s.namespace = "production"
    args = Namespace(command="run", action="open-pr", resource="acme/widget")
    s.apply_context(args)
    assert args.resource == "acme/widget"


def test_apply_context_namespaces_restart_pod():
    s = _session()
    s.namespace = "production"
    args = Namespace(command="run", action="restart-pod", resource="api-7f9d")
    s.apply_context(args)
    assert args.resource == "production/api-7f9d"


def test_learn_records_namespace_and_pod_from_fix():
    s = _session()
    args = Namespace(command="fix", target="production/api-7f9d")
    s.learn(args)
    assert s.namespace == "production"
    assert s.pod == "api-7f9d"
    assert s.last_target == "production/api-7f9d"


def test_learn_records_namespace_from_watch():
    s = _session()
    args = Namespace(command="watch", namespace="staging")
    s.learn(args)
    assert s.namespace == "staging"


def test_run_repl_exits_cleanly_on_quit():
    from rich.console import Console

    rc = repl.run_repl(Console(record=True), lines=["config", "exit"])
    assert rc == 0


def test_run_repl_survives_bad_line_and_eof(monkeypatch):
    from rich.console import Console

    # "this is not a verb" has no recognized keyword, so resolve() now falls
    # through to the Milestone 2 LLM fallback (prash/intent.py). Stub it out:
    # this test is about the REPL loop surviving bad input, not about
    # exercising a real network call in a unit test (found live, 2026-08-24
    # -- an unmocked call here hung 40+ seconds in call_with_tool's retry
    # backoff instead of failing fast).
    monkeypatch.setattr("prash.intent._resolve_via_llm", lambda text, ctx: None)
    rc = repl.run_repl(Console(record=True), lines=["this is not a verb", "fix", ""])
    assert rc == 0

def test_learn_does_not_treat_ci_target_as_namespace_pod():
    """Regression for the 2026-08-19 bug: `fix owner/repo --ci` must not
    pollute the remembered namespace/pod, since owner/repo isn't a k8s
    resource -- a later 'fix the broken pod' would otherwise silently reuse
    it and send it straight to the Kubernetes API."""
    s = _session()
    args = Namespace(command="fix", target="drufiyai-group/prash-ci-test", ci=True)
    s.learn(args)
    assert s.namespace is None
    assert s.pod is None
    assert s.last_target is None


def test_apply_context_does_not_namespace_bare_ci_target():
    s = _session()
    s.namespace = "production"
    args = Namespace(command="fix", target="some-repo", ci=True)
    s.apply_context(args)
    assert args.target == "some-repo"


def test_run_repl_survives_contraction_without_crashing(monkeypatch):
    """Regression: shlex.split raises ValueError on an unbalanced quote
    (any English contraction -- "what's", "it's"), which used to print the
    raw shlex exception and never give stage-2 intent resolution a chance."""
    from rich.console import Console

    # "what's up" has no recognized verb either -- same LLM-fallback stub
    # as above, this test is about the shlex ValueError path, not the brain.
    monkeypatch.setattr("prash.intent._resolve_via_llm", lambda text, ctx: None)
    console = Console(record=True)
    rc = repl.run_repl(console, lines=["what's up", "exit"])
    assert rc == 0
    output = console.export_text()
    assert "No closing quotation" not in output
