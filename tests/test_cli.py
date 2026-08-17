"""Track A/B/D boundary: cli.py's .env -> os.environ passthrough for the
kubernetes connector and, since Track D days 4-5, the diagnosis brain's
model clients. See PRASH_V2.md §10, 2026-08-09 (Pending decision, resolved
with option (a)).
"""

from __future__ import annotations

from argparse import Namespace

from prash.actions.contract import ActionContext, ActionSpec, Plan, RiskTier, Target
from prash.cli import _export_cluster_env, cmd_investigate, cmd_logs, cmd_watch


def test_exports_kube_context_from_env_dict(monkeypatch):
    monkeypatch.delenv("KUBE_CONTEXT", raising=False)
    _export_cluster_env({"KUBE_CONTEXT": "kind-prash-dev"})
    import os

    assert os.environ["KUBE_CONTEXT"] == "kind-prash-dev"


def test_shell_export_wins_over_dotenv(monkeypatch):
    """A value the user already exported in their shell must not be
    silently overwritten by whatever .env says -- .env only fills gaps.
    """
    monkeypatch.setenv("KUBE_CONTEXT", "shell-context")
    _export_cluster_env({"KUBE_CONTEXT": "dotenv-context"})
    import os

    assert os.environ["KUBE_CONTEXT"] == "shell-context"


def test_ignores_keys_outside_the_cluster_allowlist(monkeypatch):
    """Only the k8s-relevant keys get exported -- this is a targeted fix
    for the connector's env gap, not a blanket .env-to-os.environ dump.
    """
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    _export_cluster_env({"GITHUB_TOKEN": "should-not-leak"})
    import os

    assert "GITHUB_TOKEN" not in os.environ


def test_missing_keys_are_a_no_op(monkeypatch):
    monkeypatch.delenv("KUBECONFIG", raising=False)
    _export_cluster_env({})
    import os

    assert "KUBECONFIG" not in os.environ


def test_blank_dotenv_value_is_also_a_no_op(monkeypatch):
    """Real bug caught live (2026-08-13): a key left BLANK in .env (matching
    .env.example's own 'leave blank to use the default' instructions) is
    present in creds with value "" -- not absent. Exporting KUBECONFIG=""
    into the real process env made the kubernetes client treat it as an
    explicit empty path instead of 'not configured', breaking a
    fresh .env.example-based setup out of the box."""
    monkeypatch.delenv("KUBECONFIG", raising=False)
    _export_cluster_env({"KUBECONFIG": ""})
    import os

    assert "KUBECONFIG" not in os.environ


def test_exports_kimi_api_key_for_the_brain(monkeypatch):
    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    _export_cluster_env({"KIMI_API_KEY": "sk-test-value"})
    import os

    assert os.environ["KIMI_API_KEY"] == "sk-test-value"


def test_exports_deepseek_and_primary_model_for_the_brain(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("PRIMARY_MODEL", raising=False)
    _export_cluster_env({"DEEPSEEK_API_KEY": "sk-ds-test", "PRIMARY_MODEL": "deepseek"})
    import os

    assert os.environ["DEEPSEEK_API_KEY"] == "sk-ds-test"
    assert os.environ["PRIMARY_MODEL"] == "deepseek"


def test_cmd_watch_uses_shell_exported_namespace_not_just_dotenv(monkeypatch, tmp_path):
    """Real bug caught by manual verification against a live cluster
    (Track E, 2026-08-09): cmd_watch read KUBE_NAMESPACE from creds (.env)
    directly instead of os.environ post-passthrough, so a namespace set only
    via shell export was silently ignored and it watched 'default' instead."""
    import prash.cli as cli_mod
    import prash.watcher as watcher_mod

    monkeypatch.setenv("KUBE_NAMESPACE", "prash-demo")
    monkeypatch.setattr(cli_mod, "CredentialStore", type(
        "FakeStore", (), {"from_env": staticmethod(lambda: type("S", (), {"load": lambda self: {}})())}
    ))
    seen_namespace = {}
    monkeypatch.setattr(watcher_mod, "run_watch_loop", lambda ns, **kw: seen_namespace.setdefault("ns", ns))

    args = Namespace(namespace=None, interval=None)
    cmd_watch(args)
    assert seen_namespace["ns"] == "prash-demo"


def test_cmd_watch_cli_flag_wins_over_env(monkeypatch):
    import prash.cli as cli_mod
    import prash.watcher as watcher_mod

    monkeypatch.setenv("KUBE_NAMESPACE", "prash-demo")
    monkeypatch.setattr(cli_mod, "CredentialStore", type(
        "FakeStore", (), {"from_env": staticmethod(lambda: type("S", (), {"load": lambda self: {}})())}
    ))
    seen_namespace = {}
    monkeypatch.setattr(watcher_mod, "run_watch_loop", lambda ns, **kw: seen_namespace.setdefault("ns", ns))

    args = Namespace(namespace="explicit-ns", interval=None)
    cmd_watch(args)
    assert seen_namespace["ns"] == "explicit-ns"


def test_cmd_watch_no_cluster_is_a_clean_stop_not_a_traceback(monkeypatch, capsys):
    """Real bug caught live (2026-08-15, Windows §5 probe): `prash watch`
    with no kube-config raised the kubernetes client's ConfigException out of
    run_watch_loop uncaught, dying with a raw traceback instead of a clean
    message like `prash fix`'s. No cluster must stop the watch cleanly."""
    import prash.cli as cli_mod
    import prash.watcher as watcher_mod

    monkeypatch.setenv("KUBE_NAMESPACE", "prash-demo")
    monkeypatch.setattr(cli_mod, "CredentialStore", type(
        "FakeStore", (), {"from_env": staticmethod(lambda: type("S", (), {"load": lambda self: {}})())}
    ))

    def raise_config_exception(ns, **kw):
        from kubernetes.config.config_exception import ConfigException

        raise ConfigException("Invalid kube-config file. No configuration found.")

    monkeypatch.setattr(watcher_mod, "run_watch_loop", raise_config_exception)

    args = Namespace(namespace="prash-demo", interval=None)
    rc = cmd_watch(args)
    assert rc == 2
    captured = capsys.readouterr().out
    assert "watch stopped:" in captured
    assert "Invalid kube-config" in captured
    assert "Traceback" not in captured


def _fake_action(risk_tier=RiskTier.SAFE, approval_hint=""):
    spec = ActionSpec(
        id="restart-pod", summary="test", risk_tier=risk_tier, reversible=True, approval_hint=approval_hint
    )
    return type("FakeAction", (), {"spec": spec})()


def test_cli_ask_eof_on_stdin_is_a_clean_decline_not_a_crash(monkeypatch):
    """Real bug caught live (2026-08-14): running `prash run` with stdin
    already closed (piped input exhausted, Ctrl+D, or a script that forgot
    --noninteractive) raised an uncaught EOFError out of rich's Prompt.ask,
    killing the process with a full Python traceback instead of a clean
    outcome. No stdin available must be treated the same as the user saying
    no -- never proceed with an action nobody actually confirmed."""
    import prash.cli as cli_mod

    def raise_eof(*args, **kwargs):
        raise EOFError()

    monkeypatch.setattr(cli_mod.Prompt, "ask", raise_eof)

    action = _fake_action()
    plan = Plan(action_id="restart-pod", steps=[], reversible=True, risk_tier=RiskTier.SAFE)
    ctx = ActionContext(target=Target(resource="prash-demo/pod"), credentials={})

    assert cli_mod.CliAsk().ask(action, plan, ctx) is False


def test_cmd_investigate_stops_cleanly_when_unauthenticated(monkeypatch):
    """Real bug caught live (2026-08-14): cmd_investigate printed "auth not
    configured" for an unauthenticated connector but then fell through into
    poll_state() anyway. GitHub's real connector crashed with an unhandled
    KeyError indexing an empty API response; Vercel's connector happened not
    to crash but silently returned a fake "not-found" result instead of
    honestly stopping. poll_state() must never be called without a session."""
    import prash.cli as cli_mod

    poll_state_called = {"value": False}

    def fake_poll_state(resource):
        poll_state_called["value"] = True
        raise AssertionError("poll_state must not be called when authenticate() is False")

    fake_connector = type(
        "FakeConnector",
        (),
        {"name": "github", "authenticate": lambda self: False, "poll_state": fake_poll_state},
    )()
    monkeypatch.setattr(cli_mod, "_make_connectors", lambda creds: {"github": fake_connector})
    monkeypatch.setattr(cli_mod, "CredentialStore", type(
        "FakeStore", (), {"from_env": staticmethod(lambda: type("S", (), {"load": lambda self: {}})())}
    ))

    args = Namespace(provider="github", resource="owner/repo")
    exit_code = cmd_investigate(args)

    assert poll_state_called["value"] is False
    assert exit_code != 0


def test_cmd_logs_rejects_a_bad_target_cleanly(capsys):
    """<namespace>/<pod> is required, same contract as `prash fix`'s target
    parsing (reuses split_k8s_target) -- a malformed target must not reach
    the kubernetes client at all."""
    args = Namespace(target="not-a-valid-target", follow=False, tail=10)
    rc = cmd_logs(args)
    assert rc == 2
    assert "expected" in capsys.readouterr().out


def test_cmd_logs_no_follow_prints_recent_logs(monkeypatch, capsys):
    import prash.connectors.kubernetes as k8s_mod

    monkeypatch.setattr(k8s_mod, "get_pod_logs", lambda ns, pod, tail_lines: "line one\nline two")
    args = Namespace(target="prash-demo/api", follow=False, tail=10)
    rc = cmd_logs(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "line one" in out and "line two" in out


def test_cmd_logs_no_follow_handles_empty_logs_honestly(monkeypatch, capsys):
    import prash.connectors.kubernetes as k8s_mod

    monkeypatch.setattr(k8s_mod, "get_pod_logs", lambda ns, pod, tail_lines: "")
    args = Namespace(target="prash-demo/api", follow=False, tail=10)
    rc = cmd_logs(args)
    assert rc == 0
    assert "(no logs)" in capsys.readouterr().out


def test_cmd_logs_follow_streams_lines_and_stops_cleanly_on_ctrl_c(monkeypatch, capsys):
    import prash.connectors.kubernetes as k8s_mod

    def fake_stream(ns, pod, tail_lines):
        yield "first line"
        raise KeyboardInterrupt()

    monkeypatch.setattr(k8s_mod, "stream_pod_logs", fake_stream)
    args = Namespace(target="prash-demo/api", follow=True, tail=10)
    rc = cmd_logs(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "first line" in out
    assert "stopped" in out
    assert "Traceback" not in out


def test_cmd_logs_follow_unreachable_cluster_is_a_clean_stop_not_a_traceback(monkeypatch, capsys):
    """Same class of bug as cmd_watch's ConfigException fix (2026-08-15) --
    an unreachable cluster or a pod that disappears mid-stream must stop
    cleanly, not crash with a raw kubernetes-client traceback."""
    import prash.connectors.kubernetes as k8s_mod

    def fake_stream(ns, pod, tail_lines):
        raise ConnectionError("connection refused")
        yield  # pragma: no cover — makes this a generator function

    monkeypatch.setattr(k8s_mod, "stream_pod_logs", fake_stream)
    args = Namespace(target="prash-demo/api", follow=True, tail=10)
    rc = cmd_logs(args)
    assert rc == 2
    out = capsys.readouterr().out
    assert "logs stopped:" in out
    assert "connection refused" in out
    assert "Traceback" not in out


def test_cli_ask_ctrl_c_during_prompt_is_a_clean_decline_not_a_crash(monkeypatch):
    """Same class of bug as the EOFError case above, for Ctrl+C at the
    approval prompt specifically (as opposed to Ctrl+C elsewhere in the
    program, which is out of scope here)."""
    import prash.cli as cli_mod

    def raise_interrupt(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(cli_mod.Prompt, "ask", raise_interrupt)

    action = _fake_action()
    plan = Plan(action_id="restart-pod", steps=[], reversible=True, risk_tier=RiskTier.SAFE)
    ctx = ActionContext(target=Target(resource="prash-demo/pod"), credentials={})

    assert cli_mod.CliAsk().ask(action, plan, ctx) is False
