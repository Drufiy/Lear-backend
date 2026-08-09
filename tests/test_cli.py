"""Track A/B/D boundary: cli.py's .env -> os.environ passthrough for the
kubernetes connector and, since Track D days 4-5, the diagnosis brain's
model clients. See PRASH_V2.md §10, 2026-08-09 (Pending decision, resolved
with option (a)).
"""

from __future__ import annotations

from prash.cli import _export_cluster_env


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
