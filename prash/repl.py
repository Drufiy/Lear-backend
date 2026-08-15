"""REPL stage 1 (PRASH_V2.md §6b) — a persistent interactive session.

Not a new command set: the REPL re-invokes the existing argparse parser per
line, so every `cmd_*` entry point works exactly as in one-shot mode. What
makes it a session (and not just a prompt loop) is short-lived context that
is carried between lines:

    prash repl
    prash> fix api-7f9d                 -> uses the remembered namespace
    prash> run restart-pod api-7f9d     -> ditto, no full ns/pod retyping
    prash> watch                        -> uses the remembered namespace
    prash> exit

Stage 2 (free-text intent parsing, §6b) is deliberately out of scope here —
this is the usable, shippable skeleton. `q`/`exit`/`quit`/Ctrl+D end the
session; `help` prints the parser's usage.
"""

from __future__ import annotations

import shlex
from typing import Iterable, Optional

from . import ui
from .cli import build_parser

# `run` only auto-fills the namespace for actions whose resource is a pod.
# open-pr/request-secret/apply-ci-fix take an owner/repo; rollback takes a
# deployment — guessing a namespace there would be wrong.
_POD_ACTIONS = {"restart-pod"}

_PROMPT = "[bold yellow]prash>[/bold yellow] "


class ReplSession:
    """Carries the small amount of context that makes repeated commands
    bearable: the last namespace, the last pod, and the last full target."""

    def __init__(self, console) -> None:
        self.console = console
        self.namespace: Optional[str] = None
        self.pod: Optional[str] = None
        self.last_target: Optional[str] = None

    def apply_context(self, args) -> None:
        """Fill in remembered context for a parsed command, in place, before
        its func runs. A bare pod name in `fix`/`run restart-pod` resolves
        against the remembered namespace; `watch` picks up the namespace too."""
        command = getattr(args, "command", None)
        if command == "fix":
            target = getattr(args, "target", "")
            if "/" not in target and self.namespace and target:
                args.target = f"{self.namespace}/{target}"
        elif command == "run":
            resource = getattr(args, "resource", "")
            if getattr(args, "action", "") in _POD_ACTIONS and "/" not in resource and self.namespace and resource:
                args.resource = f"{self.namespace}/{resource}"
        elif command == "watch":
            if not getattr(args, "namespace", None) and self.namespace:
                args.namespace = self.namespace

    def learn(self, args) -> None:
        """Record context from a completed command for the next one."""
        command = getattr(args, "command", None)
        if command == "fix":
            target = getattr(args, "target", "")
            if "/" in target:
                self.namespace, self.pod = target.split("/", 1)
                self.last_target = target
        elif command == "run":
            if getattr(args, "action", "") in _POD_ACTIONS:
                resource = getattr(args, "resource", "")
                if "/" in resource:
                    self.namespace, self.pod = resource.split("/", 1)
                    self.last_target = resource
        elif command == "watch":
            if getattr(args, "namespace", None):
                self.namespace = args.namespace


def run_repl(console=None, lines: Optional[Iterable[str]] = None) -> int:
    """Start the interactive session. `lines` is for tests/CI only — when
    given, input is consumed from it instead of stdin so the loop is testable
    headlessly. Returns a shell exit code."""
    console = console or ui.console
    parser = build_parser()
    session = ReplSession(console)
    iterator = iter(lines) if lines is not None else None

    console.print("[dim]type a command, or `help` / `exit`.[/dim]")

    while True:
        try:
            line = next(iterator) if iterator is not None else console.input(_PROMPT)
        except StopIteration:
            return 0
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]bye[/dim]")
            return 0

        line = line.strip()
        if not line:
            continue
        if line.lower() in ("exit", "quit", "q"):
            console.print("[dim]bye[/dim]")
            return 0
        if line.lower() in ("help", "?"):
            parser.print_help()
            continue

        try:
            argv = shlex.split(line)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            continue

        try:
            args = parser.parse_args(argv)
        except SystemExit:
            # argparse printed help/usage for a bad line; keep the session alive.
            continue

        session.apply_context(args)
        try:
            rc = args.func(args)
            session.learn(args)
            if rc:
                console.print(f"[dim](exit {rc})[/dim]")
        except KeyboardInterrupt:
            console.print("[dim]interrupted[/dim]")
        except Exception as exc:  # noqa: BLE001 — a bad command must not kill the session
            console.print(f"[red]{exc}[/red]")
    return 0