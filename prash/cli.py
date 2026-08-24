"""`prash` CLI spine (Track A).

Entry point for the local agent. Loads local credentials, builds the action
registry and connectors, and drives the dispatch pipeline. The rich interface
is where the user gets walked through what Prash found, what it wants to do,
and where every approval prompt happens.

Commands:
    prash run <action> <resource>   execute an action through the pipeline
    prash fix <namespace>/<pod>     diagnose a pod, then run the brain's recommended action
    prash fix <owner>/<repo> --ci --run-id <n>   multi-failure CI diagnosis (Track D tier 2)
    prash investigate <resource>    read-only state/logs via a connector
    prash logs <namespace>/<pod> [--follow]   read/tail a pod's logs
    prash actions                   list registered actions and risk tiers
    prash audit                     show the append-only audit log
    prash config                    show local config (secrets redacted)
    prash watch                     poll a namespace, notify on new pod problems (Track E)
    prash notify <message>          send a message to every configured team channel (Slack/Discord)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

from rich.panel import Panel
from rich.prompt import Prompt

from . import ui
from .actions.apply_ci_fix import ApplyCiFixAction, ApplyManifestFixAction
from .actions.apply_gitlab_ci_fix import ApplyGitlabCiFixAction
from .actions.contract import (
    ActionContext,
    MissingSecretError,
    Plan,
    Target,
)
from .actions.edit_config import EditConfigMapAction, EditSecretAction
from .actions.exec_command import ExecAction
from .actions.execute_aws import ExecuteAwsAction
from .actions.missing_secret import RequestSecretAction
from .actions.datadog_mute import DatadogMuteMonitorAction
from .actions.gitleaks_escalate import GitleaksEscalateAction
from .actions.grafana_silence import GrafanaSilenceAlertAction
from .actions.open_pr import OpenPrAction
from .actions.pagerduty_incident import PagerdutyAcknowledgeAction, PagerdutyResolveAction
from .actions.restart_pod import RestartPodAction
from .actions.snyk_ignore import SnykIgnoreIssueAction
from .actions.rollback import RollbackAction
from .actions.scale import ScaleAction
from .actions.vercel_deploy import VercelRedeployAction, VercelRollbackAction
from .audit import AuditLog
from .circuit_breaker import CircuitBreaker
from .connectors.aws import AWSConnector
from .connectors.azure import AzureConnector
from .connectors.gcp import GCPConnector
from .connectors.base import Connector
from .connectors.datadog import DatadogConnector
from .connectors.github import GitHubConnector, GitHubRunner
from .connectors.gitleaks import GitleaksConnector
from .connectors.gitlab import GitLabConnector
from .connectors.grafana import GrafanaConnector
from .connectors.pagerduty import PagerDutyConnector
from .connectors.snyk import SnykConnector
from .connectors.vercel import VercelConnector
from .credentials import CredentialStore
from .dispatch import AskFn, Dispatcher, ExecutionOutcome, RunResult
from .notifications import send_team_notifications, team_notifiers
from .permissions import PermissionMode

console = ui.console

PROVIDERS: dict[str, type[Connector]] = {
    "github": GitHubConnector,
    "gitlab": GitLabConnector,
    "vercel": VercelConnector,
    "aws": AWSConnector,
    "azure": AzureConnector,
    "gcp": GCPConnector,
    "datadog": DatadogConnector,
    "grafana": GrafanaConnector,
    "pagerduty": PagerDutyConnector,
    "snyk": SnykConnector,
    "gitleaks": GitleaksConnector,
}

# Providers --ci diagnosis on `prash fix` knows how to drive. Not all of
# PROVIDERS: aws/vercel have no CI-run concept for this command.
_CI_PROVIDERS = ("github", "gitlab")


def _parse_mode(raw: str) -> PermissionMode:
    try:
        return PermissionMode(raw)
    except ValueError:
        console.print(f"[red]unknown permission mode: {raw}[/red]")
        sys.exit(2)


def _make_connectors(creds: dict[str, Any]) -> dict[str, Connector]:
    return {name: cls(creds) for name, cls in PROVIDERS.items()}


# Keys the kubernetes connector (Track B) and the diagnosis brain (Track D)
# read directly from the process environment, not from ctx.credentials --
# see PRASH_V2.md §10, 2026-08-09 (cluster keys) and days 4-5 (brain keys).
_CLUSTER_ENV_PASSTHROUGH = ("KUBECONFIG", "KUBE_CONTEXT", "KUBE_NAMESPACE")
_BRAIN_ENV_PASSTHROUGH = (
    "KIMI_API_KEY", "KIMI_BASE_URL", "KIMI_MODEL",
    "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL",
    "PRIMARY_MODEL",
)


def _export_cluster_env(creds: dict[str, Any]) -> None:
    """Make .env's cluster + brain-model settings visible to the libraries that
    read them straight from the process environment (prash.connectors.kubernetes,
    prash.brain.kimi_client) rather than through ctx.credentials.

    A shell-exported value always wins over .env -- this only fills in what
    isn't already set, so power users overriding via their shell still work
    exactly as before.

    Real bug, caught live (2026-08-13): a key left BLANK in .env (e.g.
    `KUBECONFIG=`, matching .env.example's own "leave blank to use the
    default" instructions) is present in creds with value "" -- not absent.
    `key in creds` was True for it, so an empty string got exported into the
    real process environment. That's not the same as unset: the kubernetes
    client treats KUBECONFIG="" as an explicit (empty, invalid) path rather
    than "not configured, use ~/.kube/config", producing "Invalid kube-config
    file. No configuration found." for a setup that should have worked out of
    the box. Checking creds.get(key) (truthy) instead of `key in creds`
    treats a blank .env line the same as an absent one for every key here,
    not just KUBECONFIG -- the same gap existed for KUBE_NAMESPACE, all the
    KIMI_*/DEEPSEEK_* keys, etc.
    """
    for key in (*_CLUSTER_ENV_PASSTHROUGH, *_BRAIN_ENV_PASSTHROUGH):
        if creds.get(key) and key not in os.environ:
            os.environ[key] = str(creds[key])


class CliAsk(AskFn):
    def ask(self, action: Any, plan: Plan, ctx: ActionContext) -> bool:
        console.print(
            Panel(
                f"[bold]Target[/bold] [yellow]{ctx.target.resource}[/yellow]  [dim]({ctx.target.environment})[/dim]\n\n{plan.describe()}",
                title=f"[bold]PRASH proposes · {action.spec.id}[/bold]",
                border_style=ui.ACCENT,
            )
        )
        hint = f" ({action.spec.approval_hint})" if action.spec.approval_hint else ""
        try:
            answer = Prompt.ask(
                f"Proceed with '{action.spec.id}'{hint}? [y/N]",
                choices=["y", "n", "yes", "no"],
                default="n",
            )
        except (EOFError, KeyboardInterrupt):
            # Real bug, caught live (2026-08-14): no stdin available (piped
            # input closed, Ctrl+D, or a script that forgot --noninteractive)
            # raised an uncaught EOFError with a full traceback instead of a
            # clean decline. Treat "can't get an answer" the same as "no" --
            # never proceed with an action nobody actually confirmed.
            console.print("\n[yellow]No input received -- treating as decline.[/yellow]")
            return False
        return answer.lower().startswith("y")


def _parse_set_flags(pairs: list | None) -> dict[str, str]:
    """--set KEY=VALUE (repeatable) -> {KEY: VALUE}, for edit-configmap/
    edit-secret. A malformed entry (no '=') is dropped rather than raising
    here -- the action's own execute() already fails honestly on an empty
    data dict, so a single bad --set degrades to that same clean failure
    instead of a CLI-level traceback."""
    result: dict[str, str] = {}
    for pair in pairs or []:
        key, sep, value = pair.partition("=")
        if not sep:
            console.print(f"[yellow]ignoring malformed --set value (expected KEY=VALUE): {pair!r}[/yellow]")
            continue
        result[key] = value
    return result


def _make_context(
    args: argparse.Namespace,
    store: CredentialStore,
    creds: dict[str, Any],
    resource: str | None = None,
    env: str | None = None,
) -> ActionContext:
    connectors = _make_connectors(creds)
    secret_input = None
    if not getattr(args, "noninteractive", False):
        def secret_input(name: str, hint: str) -> str:
            prompt = f"Value for secret '{name}'" + (f" ({hint})" if hint else "")
            try:
                return Prompt.ask(prompt, password=True)
            except (EOFError, KeyboardInterrupt):
                # Same class of bug as CliAsk.ask() above: no stdin available
                # must not crash. An empty value here is already handled
                # cleanly by RequestSecretAction.execute() -> NEEDS_INPUT.
                console.print("\n[yellow]No input received for secret value.[/yellow]")
                return ""

    runner = None
    github = connectors.get("github")
    if github is not None and creds.get("GITHUB_TOKEN"):
        runner = GitHubRunner(github)

    return ActionContext(
        target=Target(resource=resource or args.resource, environment=env or args.env or creds.get("PRASH_ENVIRONMENT", "staging")),
        credentials=creds,
        secrets=store.secrets(),
        dry_run=getattr(args, "dry_run", False),
        grant=getattr(args, "grant", False),
        extra={
            "store": store,
            "connectors": connectors,
            "runner": runner,
            "secret_name": getattr(args, "secret_name", ""),
            "secret_hint": getattr(args, "secret_hint", ""),
            "secret_input": secret_input,
            "head": getattr(args, "head", None),
            "base": getattr(args, "base", None),
            "title": getattr(args, "title", None),
            "body": getattr(args, "body", None),
            "command": getattr(args, "command", None),
            "pem_path": getattr(args, "pem_path", None),
            "replicas": getattr(args, "replicas", None),
            "noninteractive": getattr(args, "noninteractive", False),
            "config_data": _parse_set_flags(getattr(args, "set", None)),

            "exec_command": getattr(args, "exec_command", None),
            "container": getattr(args, "container", None),
            "deployment_id": getattr(args, "deployment_id", None),
            "minutes": getattr(args, "minutes", 60),
            "reason": getattr(args, "reason", None),
        },
    )


def _build_dispatcher(mode: PermissionMode) -> Dispatcher:
    dispatcher = Dispatcher(mode=mode, breaker=CircuitBreaker.default())
    dispatcher.register_all(
        [
            OpenPrAction(),
            RequestSecretAction(),
            RestartPodAction(),
            RollbackAction(),
            ScaleAction(),
            EditConfigMapAction(),
            EditSecretAction(),

            ExecAction(),
            ApplyCiFixAction(),
            ApplyGitlabCiFixAction(),
            ApplyManifestFixAction(),
            ExecuteAwsAction(),
            PagerdutyAcknowledgeAction(),
            PagerdutyResolveAction(),
            VercelRedeployAction(),
            VercelRollbackAction(),
            DatadogMuteMonitorAction(),
            GrafanaSilenceAlertAction(),
            SnykIgnoreIssueAction(),
            GitleaksEscalateAction(),
        ]
    )
    return dispatcher


def cmd_run(args: argparse.Namespace) -> int:
    store = CredentialStore.from_env()
    creds = store.load()
    _export_cluster_env(creds)
    mode_raw = args.mode or creds.get("PRASH_PERMISSION_MODE", "ask")
    mode = _parse_mode(mode_raw)
    dispatcher = _build_dispatcher(mode)
    ctx = _make_context(args, store, creds)

    if args.action not in dispatcher.available:
        console.print(f"[red]unknown action: {args.action}[/red]")
        return 2

    try:
        result = dispatcher.run(args.action, ctx, ask=None if args.noninteractive else CliAsk())
    except KeyError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2
    except MissingSecretError as exc:
        console.print(f"[yellow]secret '{exc.name}' required: {exc.hint}[/yellow]")
        return 3

    return _render_run_result(result)


def _render_run_result(result: RunResult) -> int:
    """Shared outcome rendering for cmd_run and cmd_fix: circuit-open gets the
    STOP-AND-ESCALATE panel, everything else gets the decision/status line +
    verification + audit id."""
    if result.outcome is ExecutionOutcome.CIRCUIT_OPEN:
        console.print(
            Panel(
                result.result.summary,
                title="[bold red]CIRCUIT OPEN — STOP AND ESCALATE TO A HUMAN[/bold red]",
                border_style="red",
            )
        )
        console.print("[yellow]Run `prash circuit status` to inspect, and `prash circuit reset <resource>` only after a human decides it is safe to continue.[/yellow]")
        if result.audit_id:
            console.print(f"[dim]audit id: {result.audit_id}[/dim]")
        return 1

    console.print(
        Panel(
            f"[bold]{result.decision.value}[/bold] / {result.result.status.value}: {result.result.summary}",
            title="outcome",
            border_style=ui.GOOD if result.ok else ui.BAD,
        )
    )
    if result.result.verification is not None:
        v = result.result.verification
        console.print(f"{ui.verified(v.ok)}: {v.detail}")
    if result.audit_id:
        console.print(f"[{ui.META}]audit id: {result.audit_id}[/{ui.META}]")
    return 0 if result.ok else 1


def _render_no_auto_action(recommended_action: str | None, namespace: str) -> None:
    if recommended_action == "rollback":
        console.print("[yellow]brain recommends rollback — not auto-run from `prash fix` (needs the owning Deployment, which Track B doesn't derive from a pod); run `prash run rollback <deployment> --env <namespace>` to execute[/yellow]")
    elif recommended_action == "scale":
        console.print("[yellow]brain recommends scale — no scale action is registered this sprint (§7 out of scope); escalate to a human[/yellow]")
    else:
        console.print("[dim]brain did not recommend an automated action; review the diagnosis above[/dim]")


def _pick_option(diagnosis: Any) -> str | None:
    """Interactive picker for the "ask, don't quit" menu (PRASH_V2.md §9,
    2026-08-15). Returns the chosen option's action value, or None for the
    explicit "escalate to a human" choice and for a declined/no-input prompt.
    Never auto-picks on the user's behalf — the whole point of the menu."""
    options = diagnosis.options or []
    choices = [str(i) for i in range(1, len(options) + 1)]
    default = str(next((i for i, o in enumerate(options, start=1) if o.is_default), 1))
    try:
        raw = Prompt.ask("Which option should Prash execute?", choices=choices, default=default)
    except (EOFError, KeyboardInterrupt):
        console.print("\n[yellow]No input received — treating as decline.[/yellow]")
        return None
    return options[int(raw) - 1].action


def cmd_fix(args: argparse.Namespace) -> int:
    from .fix import (
        FixTargetError,
        diagnose_ci_run,
        diagnose_gitlab_ci_run,
        diagnose_k8s_pod,
        recommended_action_id,
        render_diagnosis,
        render_multi_failure,
        split_k8s_target,
    )

    store = CredentialStore.from_env()
    creds = store.load()
    _export_cluster_env(creds)
    mode_raw = args.mode or creds.get("PRASH_PERMISSION_MODE", "ask")
    mode = _parse_mode(mode_raw)

    if args.ci:
        provider = getattr(args, "provider", "github") or "github"
        if not args.run_id:
            console.print(f"[red]--run-id is required for CI diagnosis: `prash fix <target> --ci --run-id <n>`[/red]")
            return 2

        # Same diagnosis+apply shape either way -- only the token, fetch
        # function, apply-fix action id, and the extra key naming the run
        # differ between providers.
        if provider == "gitlab":
            token_key, diagnose_fn, apply_action_id, run_extra_key = (
                "GITLAB_TOKEN", diagnose_gitlab_ci_run, "apply-gitlab-ci-fix", "pipeline_id",
            )
        else:
            token_key, diagnose_fn, apply_action_id, run_extra_key = (
                "GITHUB_TOKEN", diagnose_ci_run, "apply-ci-fix", "run_id",
            )

        if not creds.get(token_key):
            console.print(f"[yellow]CI diagnosis needs {token_key} in local .env[/yellow]")
            return 3
        try:
            result = asyncio.run(diagnose_fn(args.run_id, args.target, creds[token_key]))
        except Exception as exc:  # noqa: BLE001 — report honestly, never fake a diagnosis
            console.print(f"[red]CI diagnosis failed: {exc}[/red]")
            return 2
        render_multi_failure(result, console)

        changes = result.combined_files_changed()
        if not changes:
            return 0

        dispatcher = _build_dispatcher(mode)
        ctx = _make_context(args, store, creds, resource=args.target, env=args.env)
        ctx.extra["file_changes"] = changes
        ctx.extra[run_extra_key] = args.run_id
        try:
            run_result = dispatcher.run(apply_action_id, ctx, ask=None if args.noninteractive else CliAsk())
        except KeyError as exc:
            console.print(f"[red]{exc}[/red]")
            return 2
        return _render_run_result(run_result)

    try:
        namespace, pod = split_k8s_target(args.target)
    except FixTargetError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2

    manifest_repo = getattr(args, "repo", None) or creds.get("PRASH_MANIFEST_REPO") or None
    gh_token = creds.get("GITHUB_TOKEN") or None
    if manifest_repo and not gh_token:
        console.print("[yellow]--repo given but GITHUB_TOKEN is not set — diagnosing without manifest access[/yellow]")
        manifest_repo = None

    try:
        diagnosis = asyncio.run(diagnose_k8s_pod(namespace, pod, repo=manifest_repo, access_token=gh_token))
    except FixTargetError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2
    except Exception as exc:  # noqa: BLE001 — report honestly, never fake a diagnosis
        console.print(f"[red]pod diagnosis failed: {exc}[/red]")
        return 2
    render_diagnosis(diagnosis, console)

    if diagnosis.files_changed:
        # The manifest-fix path (PRASH_V2.md §9, 2026-08-16). Checked FIRST and
        # deliberately: a concrete corrected manifest is strictly more useful
        # than either a restart or a menu, and per the prompt the brain sets
        # recommended_action=null when it proposes one. This is the path that
        # turns "no available action fixes this, a human must edit the
        # Deployment" -- correct but useless, six live diagnoses running -- into
        # an actual reviewable fix.
        if not manifest_repo:
            # Defensive: the brain shouldn't produce files_changed without a
            # repo (the prompt forbids it), but never silently drop a real fix.
            console.print("[yellow]brain proposed file changes but no manifest repo is configured — pass --repo <owner/repo> or set PRASH_MANIFEST_REPO to open a PR[/yellow]")
            return 0
        dispatcher = _build_dispatcher(mode)
        ctx = _make_context(args, store, creds, resource=manifest_repo, env=args.env or namespace)
        ctx.extra["file_changes"] = diagnosis.files_changed
        ctx.extra["namespace"] = namespace
        ctx.extra["pod"] = pod
        try:
            run_result = dispatcher.run("apply-manifest-fix", ctx, ask=None if args.noninteractive else CliAsk())
        except KeyError as exc:
            console.print(f"[red]{exc}[/red]")
            return 2
        return _render_run_result(run_result)

    if diagnosis.options:
        # The "ask, don't quit" flow (PRASH_V2.md §9, 2026-08-15): the brain
        # genuinely couldn't commit to a single action, so it presented a
        # ranked menu. Handle it here explicitly -- never silently.
        if args.noninteractive:
            # Unattended run: report the menu and take zero automated action.
            # Auto-picking the top-ranked option with nobody to ask is exactly
            # the blast-radius risk the circuit breaker exists to prevent.
            console.print("[yellow]--noninteractive: options were reported above; taking no automated action (never auto-pick in unattended mode)[/yellow]")
            return 0
        chosen = _pick_option(diagnosis)
        if chosen is None:
            console.print("[dim]no automated action taken — escalating to a human[/dim]")
            return 0
        action_id = recommended_action_id(chosen)
        if action_id is None:
            _render_no_auto_action(chosen, namespace)
            return 0
        dispatcher = _build_dispatcher(mode)
        ctx = _make_context(args, store, creds, resource=f"{namespace}/{pod}", env=args.env or namespace)
        try:
            # Whatever the user picked still runs through the normal pipeline:
            # risk tiers, circuit breaker, and the audit log all apply.
            result = dispatcher.run(action_id, ctx, ask=CliAsk())
        except KeyError as exc:
            console.print(f"[red]{exc}[/red]")
            return 2
        except MissingSecretError as exc:
            console.print(f"[yellow]secret '{exc.name}' required: {exc.hint}[/yellow]")
            return 3
        return _render_run_result(result)

    action_id = recommended_action_id(diagnosis.recommended_action)
    if action_id is None:
        _render_no_auto_action(diagnosis.recommended_action, namespace)
        return 0

    dispatcher = _build_dispatcher(mode)
    ctx = _make_context(args, store, creds, resource=f"{namespace}/{pod}", env=args.env or namespace)
    try:
        result = dispatcher.run(action_id, ctx, ask=None if args.noninteractive else CliAsk())
    except KeyError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2
    except MissingSecretError as exc:
        console.print(f"[yellow]secret '{exc.name}' required: {exc.hint}[/yellow]")
        return 3
    return _render_run_result(result)


def cmd_investigate(args: argparse.Namespace) -> int:
    store = CredentialStore.from_env()
    creds = store.load()
    connector = _make_connectors(creds).get(args.provider)
    if connector is None:
        console.print(f"[red]unknown provider: {args.provider}[/red]")
        return 2
    if not connector.authenticate():
        # Real bug, caught live (2026-08-14): this warning printed, then
        # execution fell through into poll_state() anyway with no valid
        # session. GitHub's connector crashed with an unhandled KeyError
        # indexing an empty response; Vercel's connector happened not to
        # crash, but silently returned a "not-found" result that looked like
        # a real answer instead of "we never actually asked." Neither is the
        # clean, honest "not configured" outcome this message promises.
        # Found live 2026-08-19 testing the gitleaks connector: this message
        # assumed every connector's auth failure means a missing token in
        # .env. True for every API-backed connector, but gitleaks has no
        # token at all -- its authenticate() fails when the local binary
        # isn't installed, so the old wording was simply false for it.
        hint = "missing binary on PATH" if connector.name == "gitleaks" else "missing token in local .env"
        console.print(f"[yellow]{connector.name}: auth not configured ({hint})[/yellow]")
        return 1
    if getattr(args, "dependabot", False):
        if args.provider != "github":
            console.print("[red]--dependabot only applies to --provider github[/red]")
            return 2
        alerts = connector.get_dependabot_alerts(args.resource)
        if not alerts:
            console.print(f"[bold]{args.resource}[/bold] -> no open Dependabot alerts")
            return 0
        console.print(f"[bold]{args.resource}[/bold] -> {len(alerts)} open Dependabot alert(s)")
        for alert in alerts:
            pkg = alert.get("dependency", {}).get("package", {}).get("name", "?")
            severity = alert.get("security_vulnerability", {}).get("severity", "?")
            summary = alert.get("security_advisory", {}).get("summary", "")
            console.print(f"[dim]  #{alert.get('number')} {pkg} ({severity}): {summary}[/dim]")
        return 0
    state = connector.poll_state(args.resource)
    console.print(f"[bold]{args.resource}[/bold] -> {state.state.value}")
    console.print(f"[dim]{state.detail}[/dim]")
    return 0


def cmd_actions(_args: argparse.Namespace) -> int:
    dispatcher = _build_dispatcher(PermissionMode.ASK)
    table = ui.make_table("registered actions", caption="run one with: prash run <action> <resource> [--mode ...] [--dry-run]")
    table.add_column("action", style="bold")
    table.add_column("risk tier")
    table.add_column("reversible")
    table.add_column("summary", style=ui.META)
    for aid, action in dispatcher.available.items():
        table.add_row(
            aid,
            ui.tier(action.spec.risk_tier.value),
            ui.reversible(action.spec.reversible),
            action.spec.summary,
        )
    console.print(table)
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    audit = AuditLog()
    table = ui.make_table("audit log (append-only)", caption="every action, its tier, the decision, and the outcome")
    table.add_column("when", style=ui.META)
    table.add_column("action", style="bold")
    table.add_column("tier")
    table.add_column("decision")
    table.add_column("status")
    table.add_column("verified")
    for entry in audit.read(limit=args.tail):
        table.add_row(
            entry["ts"],
            entry["action"],
            ui.tier(entry["risk_tier"]),
            ui.decision(entry["decision"]),
            ui.status(entry["status"]),
            ui.verified(entry["verification_ok"]),
        )
    console.print(table)
    return 0


def cmd_config(_args: argparse.Namespace) -> int:
    store = CredentialStore.from_env()
    creds = store.sanitized()
    secrets = store.secrets()
    console.print(
        Panel(
            f"[bold]credentials file[/bold]   {store.path}\n"
            f"[bold]keys present[/bold]       {', '.join(creds) if creds else '(none)'}\n"
            f"[bold]secrets stored[/bold]     {', '.join(sorted(secrets)) if secrets else '(none)'}\n"
            f"[{ui.META}]secret values are never shown[/{ui.META}]",
            title="local config",
            border_style=ui.ACCENT,
        )
    )
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    from .watcher import run_watch_loop

    store = CredentialStore.from_env()
    creds = store.load()
    _export_cluster_env(creds)
    # Read from os.environ (post-passthrough), not creds directly -- a
    # KUBE_NAMESPACE the user exported in their own shell must win over
    # .env, matching _export_cluster_env's own "shell wins" contract. creds
    # alone would silently ignore a shell-only override.
    namespace = args.namespace or os.environ.get("KUBE_NAMESPACE", "default")
    console.print(f"[bold]Watching namespace '{namespace}' for CrashLoopBackOff / OOMKilled / ImagePullBackOff / stuck pods...[/bold] (Ctrl+C to stop)")
    team_channels = [n.name for n in team_notifiers(creds)]
    if team_channels:
        console.print(f"[dim]new-problem pings will also be sent to: {', '.join(team_channels)}[/dim]")
    try:
        run_watch_loop(namespace, interval=args.interval, console=console, creds=creds)
    except Exception as exc:  # noqa: BLE001 — no cluster configured / unreachable must be a clean stop, not a traceback
        console.print(f"[red]watch stopped: {exc}[/red]")
        return 2
    return 0


def cmd_notify(args: argparse.Namespace) -> int:
    """Sprint 2 Tier 2: send a message to every configured team channel. Doubles
    as the manual "does my webhook actually work" verification path."""
    store = CredentialStore.from_env()
    creds = store.load()
    message = " ".join(args.message)
    results = send_team_notifications(creds, "Prash", message)
    if not results:
        console.print("[yellow]no team channel configured — add SLACK_WEBHOOK_URL and/or DISCORD_WEBHOOK_URL to .env[/yellow]")
        return 1
    for channel, ok in results.items():
        console.print(f"[{'green' if ok else 'red'}]{channel}: {'sent' if ok else 'failed'}[/]")
    return 0 if all(results.values()) else 1


def cmd_logs(args: argparse.Namespace) -> int:
    """Sprint-2 Kubernetes Depth (PRASH_V2.md §7b). Read-only, no dispatcher
    involved -- same shape as cmd_investigate/cmd_audit, not an Action, since
    reading logs has no permission implications to gate.

    --follow iterates stream_pod_logs() directly on the main thread rather
    than via a background thread + queue -- tried that first, reverted
    (PRASH_V2.md §9, 2026-08-17). A blocking socket read genuinely does stay
    responsive to Ctrl+C in real usage: PEP 475 (3.5+) retries interrupted
    syscalls but still raises the pending Python signal first, confirmed via
    a real subprocess + SIGINT test with no shell job-control involved. What
    looked like a hang during manual testing was `&`-backgrounding in a
    non-interactive shell setting SIGINT to SIG_IGN, unrelated to this code
    -- a test-harness artifact, not a product bug. Keeping the simple
    version rather than the threading complexity that "fixed" it.
    """
    from .connectors.kubernetes import get_pod_logs, stream_pod_logs
    from .fix import FixTargetError, split_k8s_target

    try:
        namespace, pod = split_k8s_target(args.target)
    except FixTargetError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2

    if not args.follow:
        logs = get_pod_logs(namespace, pod, tail_lines=args.tail)
        console.print(logs or "[dim](no logs)[/dim]")
        return 0

    console.print(f"[bold]Following logs for {namespace}/{pod}...[/bold] (Ctrl+C to stop)")
    try:
        for line in stream_pod_logs(namespace, pod, tail_lines=args.tail):
            console.print(line)
    except KeyboardInterrupt:
        console.print("\n[dim]stopped[/dim]")
        return 0
    except Exception as exc:  # noqa: BLE001 — unreachable cluster / missing pod must be a clean stop, not a traceback
        console.print(f"[red]logs stopped: {exc}[/red]")
        return 2
    return 0


def cmd_tui(_args: argparse.Namespace) -> int:
    # Bug, found live 2026-08-25: unlike every other cmd_* here, this never
    # loaded .env into the process environment. The diagnosis brain
    # (prash.brain.kimi_client) reads its API keys straight from os.environ,
    # not from ctx.credentials, so the Chat tab's LLM intent fallback
    # (Milestone 2) silently failed on every real session -- it worked in
    # every direct test only because those scripts loaded credentials by
    # hand first. Same root cause as evals/run_eval.py's 2026-08-17 bug.
    store = CredentialStore.from_env()
    _export_cluster_env(store.load())

    from .tui import run_tui

    return run_tui()


def cmd_repl(_args: argparse.Namespace) -> int:
    store = CredentialStore.from_env()
    _export_cluster_env(store.load())

    from .repl import run_repl

    return run_repl()


def cmd_circuit(args: argparse.Namespace) -> int:
    breaker = CircuitBreaker.default()
    if args.circuit_action == "status":
        open_resources = breaker.open_resources()
        console.print(f"[bold]circuit state:[/bold] {breaker.path}")
        console.print(f"[bold]limit:[/bold] {breaker.max_actions} actions per {breaker.window_seconds}s per resource")
        if open_resources:
            for resource in open_resources:
                console.print(f"[red]OPEN[/red]  {resource}")
        else:
            console.print("[green]closed[/green]  no resource is over the cap")
        return 0
    if args.circuit_action == "reset":
        breaker.reset(args.resource)
        if args.resource:
            console.print(f"[green]circuit reset for {args.resource}[/green]")
        else:
            console.print("[green]circuit fully reset[/green]")
        return 0
    console.print(f"[red]unknown circuit action: {args.circuit_action}[/red]")
    return 2


def cmd_setup(args: argparse.Namespace) -> int:
    from .setup import run_setup_wizard

    env_path = str(args.env_file) if getattr(args, "env_file", None) else ".env"
    run_setup_wizard(env_path=env_path)
    return 0


class _BrandedHelp(argparse.HelpFormatter):
    """argparse's help is branding-hostile by default; prepend the masthead so
    `prash --help` and every subcommand's help carry the same yellow header."""

    def format_help(self) -> str:
        return ui.masthead_text() + "\n\n" + super().format_help()


def build_parser() -> argparse.ArgumentParser:
    formatter_class = _BrandedHelp
    parser = argparse.ArgumentParser(
        prog="prash",
        description="Prash v2 — local AI DevOps agent",
        epilog="credentials stay on your machine; Drufiy's servers never see them.",
        formatter_class=formatter_class,
    )
    parser.add_argument("--env-file", type=Path, help="override the local credentials file")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="execute an action through the permission pipeline", formatter_class=formatter_class)
    run.add_argument("action", help="action id (see `prash actions`)")
    run.add_argument("resource", help="target resource, e.g. owner/repo or ns/name")
    run.add_argument("--mode", default=None, help="permission mode: read-only|ask|auto-safe|environment-scoped|bypass (default: PRASH_PERMISSION_MODE or ask)")
    run.add_argument("--env", default=None, help="target environment staging|production (default: PRASH_ENVIRONMENT or staging)")
    run.add_argument("--dry-run", action="store_true", help="plan only; never touch infrastructure")
    run.add_argument("--grant", action="store_true", help="pre-grant this single action (approval tier still prompts via ask)")
    run.add_argument("--noninteractive", action="store_true", help="never prompt; missing secrets return NEEDS_INPUT")
    run.add_argument("--secret-name", help="secret name for request-secret")
    run.add_argument("--secret-hint", default="", help="hint shown when asking for a secret")
    run.add_argument("--head", help="PR source branch (open-pr)")
    run.add_argument("--base", help="PR target branch (open-pr)")
    run.add_argument("--title", help="PR title (open-pr)")
    run.add_argument("--body", help="PR body (open-pr)")
    run.add_argument("--command", help="Command to execute (execute-aws)")
    run.add_argument("--pem-path", help="Path to PEM file for SSH fallback (execute-aws)")
    run.add_argument("--replicas", type=int, help="target replica count (scale)")
    run.add_argument("--set", action="append", metavar="KEY=VALUE", help="key to merge-patch (edit-configmap/edit-secret); repeatable")

    run.add_argument("--exec-command", help="command to run inside the pod, e.g. 'ls -la /app' (exec)")
    run.add_argument("--container", default=None, help="container name, for multi-container pods (exec)")
    run.add_argument("--deployment-id", default=None, help="Vercel deployment id (vercel-redeploy/vercel-rollback)")
    run.add_argument("--minutes", type=int, default=60, help="mute/silence duration in minutes (datadog-mute-monitor/grafana-silence-alert)")
    run.add_argument("--reason", default=None, help="reason for the change (snyk-ignore-issue)")
    run.set_defaults(func=cmd_run)

    fix = sub.add_parser("fix", help="diagnose a problem (k8s pod or CI run) and run the brain's recommended action through the permission pipeline", formatter_class=formatter_class)
    fix.add_argument("target", help="<namespace>/<pod> for a Kubernetes problem, or <owner>/<repo> (GitHub) / <namespace>/<project> (GitLab) with --ci")
    fix.add_argument("--ci", action="store_true", help="diagnose a CI run (multi-failure) instead of a pod")
    fix.add_argument("--provider", choices=_CI_PROVIDERS, default="github", help="CI provider for --ci (default: github)")
    fix.add_argument("--run-id", type=int, help="GitHub run id, or GitLab pipeline id with --provider gitlab, for CI diagnosis")
    fix.add_argument(
        "--repo",
        default=None,
        help=(
            "owner/repo holding this pod's Deployment manifest (k8s only). Lets Prash read the "
            "manifest and propose a corrected one as a PR instead of only offering restart. "
            "Defaults to PRASH_MANIFEST_REPO. Requires GITHUB_TOKEN."
        ),
    )
    fix.add_argument("--env", default=None, help="target environment (k8s: defaults to the pod's namespace)")
    fix.add_argument("--mode", default=None, help="permission mode: read-only|ask|auto-safe|environment-scoped|bypass (default: PRASH_PERMISSION_MODE or ask)")
    fix.add_argument("--dry-run", action="store_true", help="plan only; never touch infrastructure")
    fix.add_argument("--noninteractive", action="store_true", help="never prompt; missing secrets return NEEDS_INPUT")
    fix.set_defaults(func=cmd_fix)

    inv = sub.add_parser("investigate", help="read-only connector probe", formatter_class=formatter_class)
    inv.add_argument("resource")
    inv.add_argument("--provider", choices=list(PROVIDERS), default="github")
    inv.add_argument("--dependabot", action="store_true", help="github only: list open Dependabot alerts instead of CI run status (Sprint 2 Tier 3)")
    inv.set_defaults(func=cmd_investigate)

    logs = sub.add_parser("logs", help="read a pod's logs, optionally following live (sprint-2 Kubernetes Depth)", formatter_class=formatter_class)
    logs.add_argument("target", help="<namespace>/<pod>")
    logs.add_argument("--follow", action="store_true", help="live-follow, like `kubectl logs -f` (Ctrl+C to stop)")
    logs.add_argument("--tail", type=int, default=10, help="number of recent lines to start from")
    logs.set_defaults(func=cmd_logs)

    sub.add_parser("actions", help="list registered actions", formatter_class=formatter_class).set_defaults(func=cmd_actions)
    audit = sub.add_parser("audit", help="show the audit log", formatter_class=formatter_class)
    audit.add_argument("--tail", type=int, default=50)
    audit.set_defaults(func=cmd_audit)
    sub.add_parser("config", help="show local config (redacted)", formatter_class=formatter_class).set_defaults(func=cmd_config)
    circuit = sub.add_parser("circuit", help="inspect or reset the action circuit breaker", formatter_class=formatter_class)
    circuit.add_argument("circuit_action", choices=["status", "reset"])
    circuit.add_argument("resource", nargs="?", help="reset only this resource (reset only)")
    circuit.set_defaults(func=cmd_circuit)

    watch = sub.add_parser("watch", help="poll a namespace for CrashLoopBackOff/OOMKilled/ImagePullBackOff/stuck pods, notify on new problems", formatter_class=formatter_class)
    watch.add_argument("--namespace", default=None, help="default: KUBE_NAMESPACE from .env, or 'default'")
    watch.add_argument("--interval", type=int, default=None, help="poll interval in seconds (default: PRASH_WATCH_INTERVAL_SECONDS or 30)")
    watch.set_defaults(func=cmd_watch)

    notify = sub.add_parser("notify", help="send a message to every configured team channel (Slack/Discord webhooks)", formatter_class=formatter_class)
    notify.add_argument("message", nargs="+", help="the message to send")
    notify.set_defaults(func=cmd_notify)

    sub.add_parser("tui", help="open the dashboard-style terminal UI (textual)", formatter_class=formatter_class).set_defaults(func=cmd_tui)
    sub.add_parser("repl", help="persistent interactive session (stage 1)", formatter_class=formatter_class).set_defaults(func=cmd_repl)
    
    setup = sub.add_parser("setup", help="run the interactive configuration wizard", formatter_class=formatter_class)
    setup.set_defaults(func=cmd_setup)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    ui.masthead(console)
    if getattr(args, "env_file", None):
        os.environ["PRASH_ENV"] = str(args.env_file)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        console.print("[dim]interrupted[/dim]")
        return 130


if __name__ == "__main__":
    sys.exit(main())
