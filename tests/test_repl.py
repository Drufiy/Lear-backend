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


def test_run_repl_survives_bad_line_and_eof():
    from rich.console import Console

    rc = repl.run_repl(Console(record=True), lines=["this is not a verb", "fix", ""])
    assert rc == 0