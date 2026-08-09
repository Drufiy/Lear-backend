"""Track E — the watcher. Owner: Aradhya. See PRASH_V2.md §6, days 9-11.

Poll loop over Track B's Kubernetes connector, watching for the four states
Track D's brain is taught to diagnose (§8): CrashLoopBackOff, OOMKilled,
ImagePullBackOff, and stuck-pending — the connector's own _classify() already
does the hard detection work, so this module's job is narrower: poll on an
interval, remember what's already been reported so it doesn't re-notify every
cycle for an ongoing problem, and fire a desktop notification on the moment a
NEW problem appears. One source done properly, not many done shallowly (§6).

Not a background daemon (§2's "always-on" framing is a later-sprint question,
explicitly out of scope this sprint per §7 — no hosted layer). This is a
foreground `prash watch` process the user runs and leaves open, matching the
CLI-only scope this sprint committed to.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time

from prash.connectors.kubernetes import PodStatus, get_pod_status

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 30


def _interval_from_env() -> int:
    raw = os.environ.get("PRASH_WATCH_INTERVAL_SECONDS")
    if raw:
        try:
            return int(raw)
        except ValueError:
            logger.warning(f"PRASH_WATCH_INTERVAL_SECONDS={raw!r} is not an integer — using default")
    return DEFAULT_INTERVAL_SECONDS


def _pod_key(pod: PodStatus) -> str:
    return f"{pod.namespace}/{pod.name}"


def detect_changes(
    pods: list[PodStatus], previous_state: dict[str, str | None]
) -> tuple[list[PodStatus], dict[str, str | None]]:
    """Compare this poll's pod statuses against the last known state.

    Returns (pods with a newly-appeared or newly-changed problem, updated
    state). A pod stays silent across repeated polls once its problem has
    already been reported once -- only a transition (healthy -> problem, or
    problem A -> problem B) triggers a notification. A pod resolving
    (problem -> None) is recorded but never notified about -- there's
    nothing to alert on. A pod that disappears (deleted/recreated, e.g. by
    restart_pod) simply drops out of the state; its replacement starts fresh,
    which is correct -- a fresh notification if the new pod also breaks is
    exactly what should happen, not something to suppress.
    """
    new_state: dict[str, str | None] = {}
    changed: list[PodStatus] = []
    for pod in pods:
        key = _pod_key(pod)
        new_state[key] = pod.problem
        if pod.problem is not None and pod.problem != previous_state.get(key):
            changed.append(pod)
    return changed, new_state


def _notify(pod: PodStatus, console=None) -> None:
    title = f"Prash: {pod.problem} — {pod.name}"
    message = (
        f"{pod.namespace}/{pod.name} (restart_count={pod.restart_count}). "
        f"Run `prash fix {pod.namespace}/{pod.name}` to diagnose."
    )
    if not _send_desktop_notification(title, message):
        logger.warning("Desktop notification failed on every available path — console only")
    if console is not None:
        console.print(f"[bold red]⚠ {title}[/bold red]\n  {message}")


def _send_desktop_notification(title: str, message: str) -> bool:
    """True if a real OS notification was sent. Tries plyer first (works on
    Windows/Linux); on macOS specifically it falls back to `osascript`.

    Found live, verifying the watcher against the actual cluster (2026-08-09):
    plyer's macOS backend uses NSUserNotificationCenter, which returns None
    (AttributeError: 'NoneType' object has no attribute 'setDelegate_') for
    processes without a proper app-bundle identifier -- true of any plain CLI
    script, not fixable by installing more packages. `osascript -e 'display
    notification'` is the standard, dependency-free mechanism CLI tools use
    on macOS instead; it doesn't need a bundle identity.
    """
    try:
        from plyer import notification

        notification.notify(title=title, message=message, timeout=10)
        return True
    except Exception as e:  # noqa: BLE001 — a failed OS notification must never kill the watch loop
        logger.info(f"plyer notification failed ({e}), trying platform fallback")

    if sys.platform == "darwin":
        try:
            script = (
                f'display notification "{_applescript_escape(message)}" '
                f'with title "{_applescript_escape(title)}"'
            )
            subprocess.run(["osascript", "-e", script], check=True, capture_output=True, timeout=5)
            return True
        except Exception as e:  # noqa: BLE001 — same reasoning, never kill the loop
            logger.warning(f"osascript notification fallback also failed: {e}")

    return False


def _applescript_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def run_watch_loop(
    namespace: str,
    interval: int | None = None,
    console=None,
    max_iterations: int | None = None,
) -> dict[str, str | None]:
    """The actual loop. `max_iterations` is None for the real `prash watch`
    command (runs until Ctrl+C, caught by cli.py's main()) -- set to a small
    int in tests so a single call can't hang forever."""
    interval = interval or _interval_from_env()
    state: dict[str, str | None] = {}
    iterations = 0

    while max_iterations is None or iterations < max_iterations:
        pods = get_pod_status(namespace)
        changed, state = detect_changes(pods, state)
        for pod in changed:
            _notify(pod, console)
        if console is not None and not changed:
            console.print(f"[dim]{namespace}: {len(pods)} pod(s), no new problems[/dim]")

        iterations += 1
        if max_iterations is None or iterations < max_iterations:
            time.sleep(interval)

    return state
