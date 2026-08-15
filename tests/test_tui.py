"""Track A sprint-2: the textual TUI (`prash tui`) renders real data and is
keyboard-navigable. Kept headless via Textual's ``run_test`` pilot — no TTY
needed, safe in CI on all three OSes.

See PRASH_V2.md §7b (richer TUI direction) and §10 for the TUI landing.
"""

from __future__ import annotations

import asyncio

import pytest

pytestmark = pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")


def _tui_test(coro):
    """Run a headless TUI interaction inside an event loop."""
    asyncio.run(coro())


def test_app_mounts_and_shows_overview():
    async def run():
        from prash.tui import PrashApp

        async with PrashApp().run_test(size=(120, 40)) as pilot:
            assert pilot.app is not None

    _tui_test(run)


def test_tab_switching_via_keyboard():
    async def run():
        from prash.tui import PrashApp

        async with PrashApp().run_test(size=(120, 40)) as pilot:
            for key in ("a", "d", "k", "t"):
                await pilot.press(key)
                await pilot.pause()

    _tui_test(run)


def test_overview_stat_cards_present():
    async def run():
        from prash.tui import PrashApp

        async with PrashApp().run_test(size=(120, 40)) as pilot:
            cards = pilot.app.query(".stat-card")
            assert len(cards) == 5

    _tui_test(run)


def test_actions_table_shows_registered_actions():
    async def run():
        from prash.tui import PrashApp

        async with PrashApp().run_test(size=(120, 40)) as pilot:
            await pilot.press("a")
            await pilot.pause()
            table = pilot.app.query_one("#actions-table")
            assert len(table.rows) == 5  # open-pr, request-secret, restart-pod, rollback, apply-ci-fix
            row = table.get_row(next(iter(table.rows)))
            assert row[0] == "[bold]open-pr[/]"
            assert "safe" in row[1]

    _tui_test(run)


def test_audit_table_renders_entries():
    async def run():
        from prash.tui import PrashApp

        async with PrashApp().run_test(size=(120, 40)) as pilot:
            await pilot.press("d")
            await pilot.pause()
            table = pilot.app.query_one("#audit-table")
            assert len(table.rows) > 0
            row = table.get_row(next(iter(table.rows)))
            assert len(row) == 6
            assert row[1]  # action column non-empty

    _tui_test(run)


def test_k8s_pane_handles_no_cluster_gracefully():
    async def run():
        from prash.tui import PrashApp

        async with PrashApp().run_test(size=(120, 40)) as pilot:
            await pilot.press("k")
            await pilot.pause()
            table = pilot.app.query_one("#k8s-table")
            assert len(table.rows) == 0

    _tui_test(run)


def test_quit_binding():
    async def run():
        from prash.tui import PrashApp

        async with PrashApp().run_test(size=(120, 40)) as pilot:
            await pilot.press("q")
            await pilot.pause()

    _tui_test(run)