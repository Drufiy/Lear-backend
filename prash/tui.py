"""Prash v2 terminal app — one merged surface (2026-08-24), replacing the
repl/tui split.

Until now `prash repl` (plain-text, conversational, but only understood ~12
hardcoded verbs and 2 of 10 connectors via prash/intent.py) and `prash tui`
(a real dashboard, but read-only -- no input widget existed anywhere in it)
were two disconnected binaries. Found live testing the REPL against a real
Grafana alert: a completely reasonable sentence failed because it wasn't in
the keyword table, and the good-looking surface couldn't have taken that
input at all. This is the fix: one app, chat as the primary view, the
existing dashboard panes reachable from inside it instead of a separate
process.

The Chat pane does NOT reimplement REPL logic -- it drives repl.py's
`process_line()` (the exact function the plain-text `prash repl` loop now
also calls), in a worker thread so a real connector call never freezes the
UI. Two surfaces sharing one interaction engine is the whole point; forking
a second implementation here would repeat the mistake that split them in
the first place.

Built on `textual` (same team as `rich`). Non-TTY and headless-safe: every
data read is the same `AuditLog` / `CircuitBreaker` / `CredentialStore` /
connector call the CLI already uses, so nothing here is a fake dashboard.

Keys:
    q / ctrl+c   quit
    r            refresh all panes now
    c            switch to Chat
    t            switch to Overview
    a            switch to Actions
    d            switch to Audit
    k            switch to Kubernetes
"""

from __future__ import annotations

import contextlib
import io
import os
from typing import ClassVar

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Input, RichLog, Static, TabbedContent, TabPane

from . import repl as repl_mod
from . import ui as ui_mod
from .actions.contract import RiskTier
from .audit import AuditLog
from .circuit_breaker import CircuitBreaker
from .credentials import CredentialStore
from .permissions import PermissionMode
from .ui import TUI_PALETTE

REFRESH_SECONDS = 5

_BG = TUI_PALETTE["bg"]
_PANEL = TUI_PALETTE["panel"]
_PANEL_BORDER = TUI_PALETTE["panel_border"]
_TEXT = TUI_PALETTE["text"]
_DIM = TUI_PALETTE["dim"]
_BRAND = TUI_PALETTE["brand"]
_ACCENT = TUI_PALETTE["accent"]
_GOOD = TUI_PALETTE["good"]
_BAD = TUI_PALETTE["bad"]
_WARN = TUI_PALETTE["warn"]

CSS = f"""
Screen {{
    background: {_BG};
    layout: vertical;
    color: {_TEXT};
}}

#main {{
    height: 1fr;
}}

Header {{
    background: {_PANEL};
    color: {_BRAND};
}}

TabbedContent {{
    height: 1fr;
}}

TabbedContent > .tab-pane {{
    height: 1fr;
    padding: 1 2;
}}

TabbedContent > .tab--label {{
    color: {_DIM};
}}

TabbedContent > .tab--label.-active {{
    color: {_BRAND};
}}

/* ---- overview ---- */
#cards {{
    height: auto;
    margin-bottom: 1;
}}

.stat-card {{
    background: {_PANEL};
    border: tall {_PANEL_BORDER};
    padding: 1 2;
    height: auto;
    margin: 0 1 0 0;
}}

.stat-card .stat-value {{
    color: {_BRAND};
    text-style: bold;
    height: auto;
}}

.stat-card .stat-label {{
    color: {_DIM};
    height: auto;
}}

/* ---- tables ---- */
DataTable {{
    height: 1fr;
    background: {_PANEL};
    border: tall {_PANEL_BORDER};
}}

DataTable > .datatable--header {{
    color: {_ACCENT};
    text-style: bold;
    background: {_PANEL};
}}

DataTable > .datatable--cursor {{
    background: #1f6feb33;
}}

/* ---- chat ---- */
#chat-container {{
    height: 1fr;
    padding: 0;
}}

#wordmark {{
    color: {_BRAND};
    text-style: bold;
    padding: 1 2 0 2;
    height: auto;
}}

#wordmark-tag {{
    color: {_DIM};
    padding: 0 2 1 2;
    height: auto;
}}

#chat-log {{
    background: {_BG};
    height: 1fr;
    padding: 0 2;
    scrollbar-color: {_PANEL_BORDER};
}}

#chat-input {{
    background: {_PANEL};
    border: none;
    border-top: solid {_PANEL_BORDER};
    padding: 0 2;
    color: {_TEXT};
}}

#chat-input:focus {{
    border-top: solid {_BRAND};
}}

#status-line {{
    color: {_DIM};
    height: 1;
    padding: 0 2;
}}

Footer {{
    background: {_PANEL};
    color: {_DIM};
}}
"""


def _risk_tier_style(tier: str) -> str:
    return {
        RiskTier.SAFE.value: _GOOD,
        RiskTier.APPROVAL.value: _WARN,
        RiskTier.NEVER.value: _BAD,
    }.get(tier, _DIM)


def _decision_style(decision: str) -> str:
    return {
        "allow": _GOOD,
        "granted": _GOOD,
        "prompt": _WARN,
        "refuse": _BAD,
    }.get(decision, _DIM)


def _status_style(status: str) -> str:
    return {
        "succeeded": _GOOD,
        "failed": _BAD,
        "skipped": _WARN,
        "refused": _BAD,
        "needs_input": _WARN,
        "circuit_open": _WARN,
    }.get(status, _DIM)


def _verified_style(ok: bool) -> str:
    return _GOOD if ok else _DIM


class _StatCard(Horizontal):
    DEFAULT_CSS = """
    _StatCard {
        width: 1fr;
    }
    """

    def __init__(self, label: str, value: str = "—", id: str | None = None):
        super().__init__(id=id)
        self._label = label
        self._value = value
        self.add_class("stat-card")

    def compose(self) -> ComposeResult:
        yield Static(self._value, classes="stat-value")
        yield Static(self._label, classes="stat-label")

    def set_value(self, value: str) -> None:
        self.query_one(".stat-value").update(value)


class PrashApp(App):
    TITLE = "PRASH V2"
    SUB_TITLE = "local AI DevOps agent"
    CSS = CSS

    BINDINGS: ClassVar[list] = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("ctrl+c", "quit", "Quit", priority=True),
        Binding("r", "refresh", "Refresh"),
        Binding("c", "tab_chat", "Chat", key_display="c"),
        Binding("t", "tab_overview", "Overview", key_display="t"),
        Binding("a", "tab_actions", "Actions", key_display="a"),
        Binding("d", "tab_audit", "Audit", key_display="d"),
        Binding("k", "tab_k8s", "Kubernetes", key_display="k"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="chat"):
            with TabPane("Chat", id="chat"):
                yield self._compose_chat()
            with TabPane("Overview", id="overview"):
                yield self._compose_overview()
            with TabPane("Actions", id="actions"):
                yield self._compose_actions()
            with TabPane("Audit", id="audit"):
                yield self._compose_audit()
            with TabPane("Kubernetes", id="k8s"):
                yield self._compose_k8s()
        yield Static("", id="status-line")
        yield Footer()

    # ---- panes ---------------------------------------------------------

    def _compose_chat(self) -> Container:
        return Container(
            Static("prash", id="wordmark"),
            Static("local ai devops agent — type what's wrong, or `help`", id="wordmark-tag"),
            RichLog(id="chat-log", wrap=True, markup=False, highlight=False, auto_scroll=True),
            Input(placeholder="what's broken?", id="chat-input"),
            id="chat-container",
        )

    def _compose_overview(self) -> Container:
        self._card_mode = _StatCard("PERMISSION MODE")
        self._card_circuit = _StatCard("CIRCUIT BREAKER")
        self._card_actions = _StatCard("ACTIONS REGISTERED")
        self._card_audit = _StatCard("AUDIT ENTRIES")
        self._card_creds = _StatCard("CREDENTIALS")
        cards = Horizontal(
            self._card_mode, self._card_circuit, self._card_actions,
            self._card_audit, self._card_creds,
            id="cards",
        )
        return Container(
            cards,
            Static("", id="overview-detail"),
        )

    def _compose_actions(self) -> DataTable:
        table = DataTable(id="actions-table", cursor_type="row")
        table.add_columns("action", "risk tier", "reversible", "summary")
        return table

    def _compose_audit(self) -> DataTable:
        table = DataTable(id="audit-table", cursor_type="row")
        table.add_columns("when", "action", "tier", "decision", "status", "verified")
        return table

    def _compose_k8s(self) -> Vertical:
        return Vertical(
            Static("No cluster configured — set KUBECONFIG / KUBE_CONTEXT / KUBE_NAMESPACE in local .env", id="k8s-empty"),
            DataTable(id="k8s-table", cursor_type="row"),
        )

    # ---- lifecycle -----------------------------------------------------

    def on_mount(self) -> None:
        self._k8s_enabled = False
        self._chat_parser = repl_mod.build_parser()
        self._chat_session = repl_mod.ReplSession(None)
        self._chat_pending = None
        self._chat_busy = False
        self.query_one("#chat-input", Input).focus()
        self._refresh()
        self.set_interval(REFRESH_SECONDS, self._refresh)

    # ---- chat ------------------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "chat-input":
            return
        line = event.value.strip()
        event.input.value = ""
        if not line:
            return
        log = self.query_one("#chat-log", RichLog)
        log.write(f"> {line}")
        if self._chat_busy:
            log.write("(still working on the last one — hang on)")
            return
        self._chat_busy = True
        self._run_chat_line(line)

    @work(thread=True)
    def _run_chat_line(self, line: str) -> None:
        # Redirect the one global console (prash/ui.py's `console` -- every
        # cmd_* function in cli.py prints through this same object) so real
        # command output lands in the chat log instead of the raw stdout
        # Textual has already taken over the screen buffer for. Runs off
        # the main thread so a real connector call never freezes the UI.
        buf = io.StringIO()
        old_file = ui_mod.console.file
        ui_mod.console.file = buf
        try:
            with contextlib.redirect_stdout(buf):
                new_pending = repl_mod.process_line(
                    line, self._chat_session, self._chat_parser, ui_mod.console, self._chat_pending
                )
        finally:
            ui_mod.console.file = old_file
        self.call_from_thread(self._on_chat_result, new_pending, buf.getvalue())

    def _on_chat_result(self, new_pending, output: str) -> None:
        self._chat_busy = False
        log = self.query_one("#chat-log", RichLog)
        text = output.rstrip("\n")
        if text:
            # cmd_* output carries real ANSI (the CLI's Rich-rendered tables/
            # panels, plus argparse's own help text via a Rich formatter) --
            # decode it into styled Text instead of writing the raw escape
            # sequences as literal characters.
            log.write(Text.from_ansi(text))
        if new_pending is repl_mod._EXIT:
            self.exit()
            return
        self._chat_pending = new_pending

    def action_tab_chat(self) -> None:
        self.query_one(TabbedContent).active = "chat"
        self.query_one("#chat-input", Input).focus()

    def _refresh(self) -> None:
        try:
            self._refresh_overview()
            self._refresh_actions()
            self._refresh_audit()
            self._refresh_k8s()
        except Exception as exc:  # noqa: BLE001 — the TUI must never die on a data hiccup
            self.notify(f"refresh failed: {exc}", severity="error", timeout=5)

    def _refresh_overview(self) -> None:
        store = CredentialStore.from_env()
        creds = store.load()
        mode = PermissionMode(creds.get("PRASH_PERMISSION_MODE", "ask"))
        breaker = CircuitBreaker.default()
        open_resources = breaker.open_resources()
        audit = AuditLog().read()

        self._card_mode.set_value(mode.value.upper())
        self._card_circuit.set_value(f"OPEN ({len(open_resources)})" if open_resources else "CLOSED")
        self._card_actions.set_value(str(self._actions_count()))
        self._card_audit.set_value(str(len(audit)))
        self._card_creds.set_value(str(len(creds)))

        detail = self.query_one("#overview-detail", Static)
        lines = [
            f"[bold {_ACCENT}]permission mode[/]        {mode.value}",
            (
                f"[bold {_ACCENT}]circuit breaker[/]        {'OPEN' if open_resources else 'closed'}  —  "
                f"{breaker.max_actions} actions / {breaker.window_seconds}s / resource  "
                f"(file: {breaker.path})"
            ),
            f"[bold {_ACCENT}]credentials file[/]       {store.path}",
            f"[bold {_ACCENT}]keys present[/]           {', '.join(creds.keys()) if creds else '(none)'}",
            f"[bold {_ACCENT}]secrets stored[/]         {', '.join(sorted(store.secrets())) if store.secrets() else '(none)'}",
        ]
        if open_resources:
            lines.append(f"[bold {_BAD}]OPEN RESOURCES[/]        {', '.join(open_resources)} — run `prash circuit reset` after a human decides")
        detail.update("\n".join(lines))

    def _refresh_actions(self) -> None:
        from .cli import _build_dispatcher

        table = self.query_one("#actions-table", DataTable)
        table.clear()
        dispatcher = _build_dispatcher(PermissionMode.ASK)
        for aid, action in dispatcher.available.items():
            table.add_row(
                f"[bold]{aid}[/]",
                f"[{_risk_tier_style(action.spec.risk_tier.value)}]{action.spec.risk_tier.value}[/]",
                f"[{_GOOD if action.spec.reversible else _DIM}]{'yes' if action.spec.reversible else 'no'}[/]",
                action.spec.summary,
            )

    def _refresh_audit(self) -> None:
        table = self.query_one("#audit-table", DataTable)
        table.clear()
        entries = AuditLog().read(limit=100)
        for entry in reversed(entries):
            table.add_row(
                f"[{_DIM}]{entry['ts']}[/]",
                f"[bold]{entry['action']}[/]",
                f"[{_risk_tier_style(entry['risk_tier'])}]{entry['risk_tier']}[/]",
                f"[{_decision_style(entry['decision'])}]{entry['decision']}[/]",
                f"[{_status_style(entry['status'])}]{entry['status']}[/]",
                f"[{_verified_style(entry['verification_ok'])}]{'verified' if entry['verification_ok'] else '—'}[/]",
            )

    def _refresh_k8s(self) -> None:
        empty = self.query_one("#k8s-empty", Static)
        table = self.query_one("#k8s-table", DataTable)
        namespace = os.environ.get("KUBE_NAMESPACE", "default")
        if not self._k8s_enabled:
            table.add_columns("name", "namespace", "phase", "ready", "restarts", "problem")
            self._k8s_enabled = True

        table.clear()
        try:
            from .connectors.kubernetes import get_pod_status

            pods = get_pod_status(namespace)
        except Exception:  # noqa: BLE001 — no cluster configured / not reachable
            empty.update(f"cluster not reachable in namespace '{namespace}' — set KUBECONFIG / KUBE_CONTEXT and retry (r)")
            return

        if not pods:
            empty.update(f"no pods in namespace '{namespace}'")
            return

        empty.update("")
        for pod in pods:
            phase = pod.phase
            style = _GOOD if pod.ready else (_BAD if pod.problem else _WARN)
            table.add_row(
                f"[bold]{pod.name}[/]",
                pod.namespace,
                f"[{style}]{phase}[/]",
                f"[{_GOOD if pod.ready else _BAD}]{pod.ready}[/]",
                str(pod.restart_count),
                f"[{_BAD if pod.problem else _DIM}]{(pod.problem or '')}[/]",
            )

    def _actions_count(self) -> int:
        from .cli import _build_dispatcher

        return len(_build_dispatcher(PermissionMode.ASK).available)

    # ---- key actions ---------------------------------------------------

    def action_refresh(self) -> None:
        self._refresh()
        self.notify("refreshed", timeout=2)

    def action_tab_overview(self) -> None:
        self.query_one(TabbedContent).active = "overview"

    def action_tab_actions(self) -> None:
        self.query_one(TabbedContent).active = "actions"

    def action_tab_audit(self) -> None:
        self.query_one(TabbedContent).active = "audit"

    def action_tab_k8s(self) -> None:
        self.query_one(TabbedContent).active = "k8s"


def run_tui() -> int:
    """Entry point for `prash tui`. Returns a shell exit code."""
    try:
        PrashApp().run()
    except KeyboardInterrupt:
        pass
    return 0
