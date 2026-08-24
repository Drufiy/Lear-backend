"""Shared visual identity for the prash CLI (Track A).

Single source for the look: a compact yellow masthead, a small fixed palette,
and the same quiet rounded tables/panels everywhere, so the whole interface
reads as one designed surface rather than argparse plus raw rich.

§8 resolved the interface to `rich` formatted CLI output; this keeps every
rendered surface consistent with that choice. Colors degrade gracefully when
stdout is not a TTY (rich strips ANSI), so nothing breaks in pipelines.
"""

from __future__ import annotations

import io
import sys

from rich import box
from rich.console import Console
from rich.table import Table

# The CLI's rendered output uses box-drawing + accent characters. On a legacy
# Windows console the child process still sees a cp1252-encoded stdout (Python
# picks up the ANSI code page), and encoding runs crash on any U+2500-ish
# character the moment output is piped or redirected -- exactly the
# cross-platform trap §0c flags. Force UTF-8 with a lossy fallback (question
# marks instead of a crash), like most modern CLIs on Windows. Harmless on
# POSIX, where stdout is already UTF-8 by default.
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

# -- palette -----------------------------------------------------------------
# Brand accent is yellow; cyan is the secondary detail colour carried over
# from the original interface; green/red answer "yes"/"no". Keep it to these.
BRAND = "bold yellow"
ACCENT = "cyan"
META = "dim"
GOOD = "green"
BAD = "red"
WARN = "yellow"

# Hex equivalents of the same identity for surfaces that need concrete colour
# values rather than rich styles (the Textual app). Single source so a brand
# change in the palette updates every surface. Repainted 2026-08-24 (black +
# one neon pink, spent only on the wordmark and live state, never on
# decoration) -- replaces the GitHub-dark palette this shipped with since
# 2026-08-16. Semantic good/warn/bad stay deliberately apart from the accent
# hue so state is never confused with branding.
TUI_PALETTE = {
    "bg": "#060407",
    "panel": "#0e0812",
    "panel_border": "#2c1a2b",
    "text": "#f3e6ee",
    "dim": "#8f7488",
    "brand": "#ff2f8f",
    "accent": "#ff7ac2",
    "good": "#35d68f",
    "bad": "#ff4d6a",
    "warn": "#ffb020",
}

_RULE_STYLE = "bright_black"

MASTHEAD = "[bold yellow]PRASH V2[/]  [dim]local AI DevOps agent[/dim]"

console = Console()


def masthead(console_: Console) -> None:
    """Print the brand header + divider line that opens every command run."""
    console_.print(MASTHEAD)
    console_.rule(style=_RULE_STYLE)


def masthead_text() -> str:
    """Brand header as an ANSI string, used to brand argparse help output."""
    buf = io.StringIO()
    render = Console(file=buf, width=80, color_system="truecolor")
    render.print(MASTHEAD)
    render.rule(style=_RULE_STYLE)
    return buf.getvalue().rstrip("\n")


def make_table(title: str | None = None, caption: str | None = None) -> Table:
    return Table(
        title=title,
        caption=caption,
        box=box.ROUNDED,
        header_style="bold cyan",
        title_justify="left",
        title_style="bold",
        caption_justify="left",
        caption_style="dim",
        pad_edge=False,
        padding=(0, 1),
    )


def tier(value: str) -> str:
    return {
        "safe": "[green]safe[/]",
        "approval": "[yellow]approval[/]",
        "danger": "[red]danger[/]",
        "unknown": "[dim]unknown[/]",
    }.get(value, value)


def reversible(value: bool) -> str:
    return "[green]yes[/]" if value else "[dim]no[/]"


def decision(value: str) -> str:
    return {
        "allow": "[green]allow[/]",
        "granted": "[green]granted[/]",
        "prompt": "[yellow]prompt[/]",
        "refuse": "[red]refuse[/]",
    }.get(value, value)


def status(value: str) -> str:
    return {
        "succeeded": "[green]succeeded[/]",
        "failed": "[red]failed[/]",
        "skipped": "[yellow]skipped[/]",
        "refused": "[red]refused[/]",
        "needs_input": "[yellow]needs input[/]",
        "circuit_open": "[yellow]circuit open[/]",
    }.get(value, value)


def verified(value: bool) -> str:
    return "[green]verified[/]" if value else "[dim]not verified[/]"