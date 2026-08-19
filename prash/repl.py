"""Prash REPL (PRASH_V2.md §6b) — a persistent interactive session.

Not a new command set: the REPL re-invokes the existing argparse parser per
line, so every `cmd_*` entry point works exactly as in one-shot mode. What
makes it a session (and not just a prompt loop) is short-lived context that
is carried between lines:

    prash repl
    prash> fix api-7f9d                 -> uses the remembered namespace
    prash> fix it                       -> stage 2: resolves to the remembered pod
    prash> restart the broken api pod   -> stage 2: free text -> run restart-pod
    prash> watch                        -> uses the remembered namespace
    prash> exit

Stage 1 = the session + context. Stage 2 (`prash/intent.py`) = free-text
intent parsing with clarifying follow-ups when the target is ambiguous. A
line that parses as an exact command always wins; stage 2 only handles what
argparse can't. `q`/`exit`/`quit`/Ctrl+D end the session; `help` prints the
parser's usage.
"""

from __future__ import annotations

import shlex
from collections.abc import Iterable

from . import ui
from .cli import build_parser
from .intent import (
    _STOPWORDS,
    Clarify,
    Suggestion,
    _Context,
    _verb_hit,
    complete,
    resolve,
)

# `run` only auto-fills the namespace for actions whose resource is a pod.
# open-pr/request-secret/apply-ci-fix take an owner/repo; rollback takes a
# deployment — guessing a namespace there would be wrong.
_POD_ACTIONS = {"restart-pod"}

_PROMPT = "[bold yellow]prash>[/bold yellow] "


def _is_it_phrase(line: str) -> bool:
    """`fix it` / `restart that` — a known intent verb plus only a pronoun.
    These would parse as exact commands with garbage targets, so intercept
    them and let stage 2 resolve against the remembered context."""
    parts = line.strip().lower().split()
    return len(parts) == 2 and _verb_hit(parts[0]) is not None and parts[1] in ("it", "that")


def _looks_like_talk(line: str) -> bool:
    """A line that reads as natural language rather than an exact command:
    an intent verb plus conversational filler (stopwords) or pod/app talk.
    Routed to stage 2 before argparse so the parser's own "unrecognized
    arguments" noise never appears for obviously free-text input."""
    if _verb_hit(line) is None:
        return False
    return any(w in _STOPWORDS for w in line.strip().lower().split())


class ReplSession:
    """Carries the small amount of context that makes repeated commands
    bearable: the last namespace, the last pod, and the last full target."""

    def __init__(self, console) -> None:
        self.console = console
        self.namespace: str | None = None
        self.pod: str | None = None
        self.last_target: str | None = None

    def apply_context(self, args) -> None:
        """Fill in remembered context for a parsed command, in place, before
        its func runs. A bare pod name in `fix`/`run restart-pod` resolves
        against the remembered namespace; `watch` picks up the namespace too."""
        command = getattr(args, "command", None)
        if command == "fix" and not getattr(args, "ci", False):
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
        """Record context from a completed command for the next one.

        Bug, found live 2026-08-19: `fix <owner>/<repo> --ci` and
        `fix <namespace>/<pod>` share the same `target` field and both
        contain a `/`, but they are different resource types. Without the
        `--ci` guard, running a CI diagnosis pollutes the remembered
        namespace/pod with an owner/repo string -- a later "fix the broken
        pod" then silently reuses it (no clarifying question, since the
        context looks known) and sends a GitLab project path to the
        Kubernetes API as a namespace/pod. See PRASH_V2.md §10."""
        command = getattr(args, "command", None)
        if command == "fix" and not getattr(args, "ci", False):
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


def run_repl(console=None, lines: Iterable[str] | None = None) -> int:
    """Start the interactive session. `lines` is for tests/CI only — when
    given, input is consumed from it instead of stdin so the loop is testable
    headlessly. Returns a shell exit code."""
    console = console or ui.console
    parser = build_parser()
    session = ReplSession(console)
    iterator = iter(lines) if lines is not None else None
    pending: tuple[str, list[str]] | None = None  # (intent verb, clarify options)

    console.print("[dim]type a command, or `help` / `exit`.[/dim]")

    def run_argv(argv: list[str]) -> None:
        try:
            args = parser.parse_args(argv)
        except SystemExit:
            return
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

        if pending is not None:
            verb, options = pending
            pending = None
            ctx = _Context.from_session(session)
            if line.isdigit() and 1 <= int(line) <= len(options):
                choice = options[int(line) - 1]
            else:
                choice = line
            suggestion = complete(verb, choice, ctx)
            if suggestion is None:
                console.print(f"[red]I didn't get that. {options or 'no targets known yet — type one like `api-7f9d` or `ns/pod`.'}[/red]")
                continue
            console.print(f"[dim]→ {suggestion.explain}[/dim]")
            run_argv(suggestion.argv)
            continue

        ctx = _Context.from_session(session)
        if _is_it_phrase(line) or _looks_like_talk(line):
            suggestion = resolve(line, ctx)
            if isinstance(suggestion, Suggestion):
                console.print(f"[dim]→ {suggestion.explain}[/dim]")
                run_argv(suggestion.argv)
                continue
            if isinstance(suggestion, Clarify):
                pending = (_verb_hit(line), suggestion.options)
                _ask(console, suggestion)
                continue

        try:
            argv = shlex.split(line)
        except ValueError:
            # Bug, found live 2026-08-19: any line with an unbalanced quote
            # character -- in practice almost always an English contraction
            # ("what's", "it's", "let's") typed into something advertised as
            # talkable-to -- raised shlex's raw "No closing quotation" and
            # was discarded before stage 2 ever got a chance, even though
            # the exact same free text minus the apostrophe would have been
            # handled fine. Give it the same intent-resolution fallback the
            # argparse-SystemExit path below already gets, instead of
            # leaking a shlex implementation detail as the user-facing
            # error. See PRASH_V2.md §10.
            suggestion = resolve(line, ctx)
            if isinstance(suggestion, Suggestion):
                console.print(f"[dim]→ {suggestion.explain}[/dim]")
                run_argv(suggestion.argv)
                continue
            if isinstance(suggestion, Clarify):
                pending = (_verb_hit(line), suggestion.options)
                _ask(console, suggestion)
                continue
            console.print("[red]I didn't get that. Try `help`, or describe what you want in plain words.[/red]")
            continue

        try:
            parser.parse_args(argv)
        except SystemExit:
            # argparse printed usage for a bad line. Before giving up on it,
            # try stage 2: it might be free text ("restart the broken api pod").
            suggestion = resolve(line, ctx)
            if isinstance(suggestion, Suggestion):
                console.print(f"[dim]→ {suggestion.explain}[/dim]")
                run_argv(suggestion.argv)
                continue
            if isinstance(suggestion, Clarify):
                pending = (_verb_hit(line), suggestion.options)
                _ask(console, suggestion)
                continue
            continue

        run_argv(argv)
    return 0


def _ask(console, suggestion: Clarify) -> None:
    console.print(f"[bold]?[/bold] {suggestion.question}")
    for i, opt in enumerate(suggestion.options, start=1):
        console.print(f"  [yellow]{i}[/yellow]  {opt}")
    console.print("[dim]… or just type the target.[/dim]")