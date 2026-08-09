"""`prash` CLI spine (Track A).

Entry point for the local agent. Loads local credentials, builds the action
registry and connectors, and drives the dispatch pipeline. The rich interface
is where the user gets walked through what Prash found, what it wants to do,
and where every approval prompt happens.

Commands:
    prash run <action> <resource>   execute an action through the pipeline
    prash investigate <resource>    read-only state/logs via a connector
    prash actions                   list registered actions and risk tiers
    prash audit                     show the append-only audit log
    prash config                    show local config (secrets redacted)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from .actions.contract import (
    ActionContext,
    MissingSecretError,
    Plan,
    Target,
)
from .actions.missing_secret import RequestSecretAction
from .actions.open_pr import OpenPrAction
from .actions.restart_pod import RestartPodAction
from .actions.rollback import RollbackAction
from .audit import AuditLog
from .connectors.base import Connector
from .connectors.github import GitHubConnector
from .connectors.vercel import VercelConnector
from .credentials import CredentialStore
from .dispatch import AskFn, Dispatcher
from .permissions import PermissionMode

console = Console()

PROVIDERS = {
    "github": GitHubConnector,
    "vercel": VercelConnector,
}


def _parse_mode(raw: str) -> PermissionMode:
    try:
        return PermissionMode(raw)
    except ValueError:
        console.print(f"[red]unknown permission mode: {raw}[/red]")
        sys.exit(2)


def _make_connectors(creds: Dict[str, Any]) -> Dict[str, Connector]:
    return {name: cls(creds) for name, cls in PROVIDERS.items()}


class CliAsk(AskFn):
    def ask(self, action: Any, plan: Plan, ctx: ActionContext) -> bool:
        console.print(Panel(plan.describe(), title=f"[bold]Prash proposes: {action.spec.id}[/bold]", border_style="cyan"))
        hint = f" ({action.spec.approval_hint})" if action.spec.approval_hint else ""
        answer = Prompt.ask(
            f"Proceed with '{action.spec.id}'{hint}? [y/N]",
            choices=["y", "n", "yes", "no"],
            default="n",
        )
        return answer.lower().startswith("y")


def _make_context(args: argparse.Namespace, store: CredentialStore, creds: Dict[str, Any]) -> ActionContext:
    connectors = _make_connectors(creds)
    secret_input = None
    if not getattr(args, "noninteractive", False):
        def secret_input(name: str, hint: str) -> str:
            prompt = f"Value for secret '{name}'" + (f" ({hint})" if hint else "")
            return Prompt.ask(prompt, password=True)

    return ActionContext(
        target=Target(resource=args.resource, environment=args.env or creds.get("PRASH_ENVIRONMENT", "staging")),
        credentials=creds,
        secrets=store.secrets(),
        dry_run=getattr(args, "dry_run", False),
        grant=getattr(args, "grant", False),
        extra={
            "store": store,
            "connectors": connectors,
            "secret_name": getattr(args, "secret_name", ""),
            "secret_hint": getattr(args, "secret_hint", ""),
            "secret_input": secret_input,
            "head": getattr(args, "head", None),
            "base": getattr(args, "base", None),
            "title": getattr(args, "title", None),
            "body": getattr(args, "body", None),
        },
    )


def _build_dispatcher(mode: PermissionMode) -> Dispatcher:
    dispatcher = Dispatcher(mode=mode)
    dispatcher.register_all(
        [OpenPrAction(), RequestSecretAction(), RestartPodAction(), RollbackAction()]
    )
    return dispatcher


def cmd_run(args: argparse.Namespace) -> int:
    store = CredentialStore.from_env()
    creds = store.load()
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

    console.print(Panel(f"{result.decision.value} / {result.result.status.value}: {result.result.summary}", title="outcome", border_style="green" if result.ok else "red"))
    if result.result.verification is not None:
        v = result.result.verification
        label = "[green]verified[/green]" if v.ok else "[red]NOT verified[/red]"
        console.print(f"{label}: {v.detail}")
    if result.audit_id:
        console.print(f"[dim]audit id: {result.audit_id}[/dim]")
    return 0 if result.ok else 1


def cmd_investigate(args: argparse.Namespace) -> int:
    store = CredentialStore.from_env()
    creds = store.load()
    connector = _make_connectors(creds).get(args.provider)
    if connector is None:
        console.print(f"[red]unknown provider: {args.provider}[/red]")
        return 2
    if not connector.authenticate():
        console.print(f"[yellow]{connector.name}: auth not configured (missing token in local .env)[/yellow]")
    state = connector.poll_state(args.resource)
    console.print(f"[bold]{args.resource}[/bold] -> {state.state.value}")
    console.print(f"[dim]{state.detail}[/dim]")
    return 0


def cmd_actions(_args: argparse.Namespace) -> int:
    dispatcher = _build_dispatcher(PermissionMode.ASK)
    table = Table(title="registered actions")
    table.add_column("action")
    table.add_column("risk tier")
    table.add_column("reversible")
    table.add_column("summary")
    for aid, action in dispatcher.available.items():
        table.add_row(aid, action.spec.risk_tier.value, str(action.spec.reversible), action.spec.summary)
    console.print(table)
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    audit = AuditLog()
    table = Table(title="audit log (append-only)")
    table.add_column("ts")
    table.add_column("action")
    table.add_column("tier")
    table.add_column("decision")
    table.add_column("status")
    table.add_column("verified")
    for entry in audit.read(limit=args.tail):
        table.add_row(
            entry["ts"],
            entry["action"],
            entry["risk_tier"],
            entry["decision"],
            entry["status"],
            str(entry["verification_ok"]),
        )
    console.print(table)
    return 0


def cmd_config(_args: argparse.Namespace) -> int:
    store = CredentialStore.from_env()
    creds = store.sanitized()
    secrets = store.secrets()
    console.print(f"[bold]credentials file:[/bold] {store.path}")
    console.print("[bold]keys present:[/bold] " + (", ".join(creds) if creds else "(none)"))
    console.print(f"[bold]secrets stored:[/bold] {', '.join(sorted(secrets)) if secrets else '(none)'}")
    console.print("[dim]secret values are never shown[/dim]")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prash", description="Prash v2 - local AI DevOps agent")
    parser.add_argument("--env-file", type=Path, help="override the local credentials file")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="execute an action through the permission pipeline")
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
    run.set_defaults(func=cmd_run)

    inv = sub.add_parser("investigate", help="read-only connector probe")
    inv.add_argument("resource")
    inv.add_argument("--provider", choices=list(PROVIDERS), default="github")
    inv.set_defaults(func=cmd_investigate)

    sub.add_parser("actions", help="list registered actions").set_defaults(func=cmd_actions)
    audit = sub.add_parser("audit", help="show the audit log")
    audit.add_argument("--tail", type=int, default=50)
    audit.set_defaults(func=cmd_audit)
    sub.add_parser("config", help="show local config (redacted)").set_defaults(func=cmd_config)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "env_file", None):
        import os

        os.environ["PRASH_ENV"] = str(args.env_file)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        console.print("[dim]interrupted[/dim]")
        return 130


if __name__ == "__main__":
    sys.exit(main())
