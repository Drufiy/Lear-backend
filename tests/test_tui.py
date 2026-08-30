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
            # Derived from the real registry rather than hardcoded: this
            # asserted == 5 and broke the moment apply-manifest-fix was
            # registered (2026-08-16). The table showing every registered
            # action is the actual invariant; the count is incidental.
            from prash.cli import _build_dispatcher
            from prash.permissions import PermissionMode

            expected = len(_build_dispatcher(PermissionMode.ASK).available)
            assert len(table.rows) == expected
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


def _fake_confirm_args():
    """Minimal stand-ins for the (action, plan, ctx) triple ChatInteraction.confirm
    reads -- exercises the real interaction mechanism without needing a real
    dispatcher/connector/credentials, since this bug lives entirely in how the
    question gets from a worker thread to the chat log and back, not in any
    particular action."""

    class _Spec:
        id = "test-action"
        approval_hint = None

    class _Action:
        spec = _Spec()

    class _Plan:
        def describe(self) -> str:
            return "- do the thing"

    class _Target:
        resource = "some-resource"
        environment = "staging"

    class _Ctx:
        target = _Target()

    return _Action(), _Plan(), _Ctx()


def test_chat_confirm_round_trip_does_not_hang():
    """Real bug, found live 2026-08-26: a confirm-required action typed into
    Chat (`mute <monitor> for 30 minutes`) hung forever -- Prompt.ask() blocked
    on real stdin from a worker thread that could never receive it, since
    Textual's driver owns the terminal exclusively. Fixed with ChatInteraction:
    the question goes into the chat log, the worker blocks on a
    threading.Event, and on_input_submitted answers it from the main thread.
    This drives that exact path end to end and asserts it actually returns."""

    async def run():
        import threading

        from prash.tui import ChatInteraction, PrashApp

        async with PrashApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            for _ in range(60):
                await pilot.pause(0.5)
                if not app._chat_busy:
                    break

            interaction = ChatInteraction(app)
            result: dict = {}

            def worker() -> None:
                result["answer"] = interaction.confirm(*_fake_confirm_args())

            t = threading.Thread(target=worker)
            t.start()

            for _ in range(40):
                await pilot.pause(0.1)
                if app._chat_awaiting is not None:
                    break
            assert app._chat_awaiting is not None, "question never reached the chat surface"

            app.query_one("#chat-input").value = "y"
            await pilot.press("enter")

            t.join(timeout=5)
            assert not t.is_alive(), "worker thread never returned -- the hang reproduced"
            assert result["answer"] is True
            assert app._chat_awaiting is None

    _tui_test(run)


def test_chat_confirm_declines_on_no_input():
    async def run():
        import threading

        from prash.tui import ChatInteraction, PrashApp

        async with PrashApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            for _ in range(60):
                await pilot.pause(0.5)
                if not app._chat_busy:
                    break

            interaction = ChatInteraction(app)
            result: dict = {}

            def worker() -> None:
                result["answer"] = interaction.confirm(*_fake_confirm_args())

            t = threading.Thread(target=worker)
            t.start()

            for _ in range(40):
                await pilot.pause(0.1)
                if app._chat_awaiting is not None:
                    break
            assert app._chat_awaiting is not None

            app.query_one("#chat-input").value = "n"
            await pilot.press("enter")

            t.join(timeout=5)
            assert result["answer"] is False
            assert app._chat_awaiting is None

    _tui_test(run)


def test_chat_confirm_times_out_instead_of_hanging_forever():
    async def run():
        import threading

        from prash.tui import ChatInteraction, PrashApp

        async with PrashApp().run_test(size=(120, 40)) as pilot:
            app = pilot.app
            for _ in range(60):
                await pilot.pause(0.5)
                if not app._chat_busy:
                    break

            interaction = ChatInteraction(app)
            interaction._TIMEOUT_SECONDS = 0.3  # instance override, keeps the test fast
            result: dict = {}

            def worker() -> None:
                result["answer"] = interaction.confirm(*_fake_confirm_args())

            t = threading.Thread(target=worker)
            t.start()

            # Not t.join() here: the timeout path's cleanup calls
            # call_from_thread(restore), which needs this coroutine to keep
            # yielding to the event loop (via pilot.pause) to run -- a
            # blocking join() on the loop's own thread would starve it and
            # deadlock the test itself, not the code under test.
            for _ in range(40):
                await pilot.pause(0.1)
                if not t.is_alive():
                    break

            assert not t.is_alive(), "timeout path itself hung"
            assert result["answer"] is False
            assert app._chat_awaiting is None

    _tui_test(run)