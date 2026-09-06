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
from concurrent.futures import ThreadPoolExecutor

from prash.connectors.kubernetes import PodStatus, get_pod_status
from prash.connectors.terraform import TerraformConnector
from prash.connectors.aws import AWSConnector
from prash.connectors.base import ConnectorState
from prash.notifications import send_team_notifications

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


def _notify(pod: PodStatus, console=None, creds: dict | None = None) -> None:
    title = f"Prash: {pod.problem} — {pod.name}"
    message = (
        f"{pod.namespace}/{pod.name} (restart_count={pod.restart_count}). "
        f"Run `prash fix {pod.namespace}/{pod.name}` to diagnose."
    )
    if not _send_desktop_notification(title, message):
        logger.warning("Desktop notification failed on every available path — console only")
    if creds:
        # Sprint 2 Tier 2: push the same ping to every configured team channel
        # (Slack/Discord webhooks). Never raises; a dead channel is logged by
        # send_team_notifications and reported here, it doesn't kill the loop.
        results = send_team_notifications(creds, title, message)
        failed = [channel for channel, ok in results.items() if not ok]
        if failed:
            logger.warning(f"team notification failed: {', '.join(failed)}")
        elif results:
            logger.info(f"team notification sent: {', '.join(results)}")
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
    creds: dict | None = None,
) -> dict[str, str | None]:
    """The actual loop. `max_iterations` is None for the real `prash watch`
    command (runs until Ctrl+C, caught by cli.py's main()) -- set to a small
    int in tests so a single call can't hang forever. `creds` is the local
    .env dict; when present, each new-problem ping is also pushed to any
    configured Slack/Discord team channels."""
    interval = interval or _interval_from_env()
    state: dict[str, str | None] = {}
    iterations = 0

    while max_iterations is None or iterations < max_iterations:
        pods = get_pod_status(namespace)
        changed, state = detect_changes(pods, state)
        for pod in changed:
            _notify(pod, console, creds)
        if console is not None and not changed:
            console.print(f"[dim]{namespace}: {len(pods)} pod(s), no new problems[/dim]")

        iterations += 1
        if max_iterations is None or iterations < max_iterations:
            time.sleep(interval)

    return state


def _notify_terraform(resource: str, state_val: str, info: str, console=None, creds: dict | None = None) -> None:
    title = f"Prash: Terraform {state_val} — {resource}"
    message = f"Terraform state changed to {state_val}: {info}. Run `prash fix {resource}` to diagnose."
    if not _send_desktop_notification(title, message):
        logger.warning("Desktop notification failed on every available path — console only")
    if creds:
        results = send_team_notifications(creds, title, message)
        failed = [channel for channel, ok in results.items() if not ok]
        if failed:
            logger.warning(f"team notification failed: {', '.join(failed)}")
        elif results:
            logger.info(f"team notification sent: {', '.join(results)}")
    if console is not None:
        console.print(f"[bold red]⚠ {title}[/bold red]\n  {message}")


def run_terraform_watch_loop(
    resource: str,
    interval: int | None = None,
    console=None,
    max_iterations: int | None = None,
    creds: dict | None = None,
):
    """Poll Terraform state to detect drift or state lock errors."""
    interval = interval or _interval_from_env()
    state = None
    iterations = 0
    connector = TerraformConnector(creds or {})
    
    while max_iterations is None or iterations < max_iterations:
        # Check drift if configured, otherwise just parse state
        check_drift = str((creds or {}).get("TERRAFORM_WATCH_DRIFT", "false")).lower() == "true"
        current_res = connector.poll_state(resource, check_drift=check_drift)
        
        current_problem = None
        if current_res.state in (ConnectorState.DEGRADED, ConnectorState.FAILED):
            current_problem = current_res.detail.get("error") or current_res.detail.get("info") or current_res.state.value
            
        if current_problem is not None and current_problem != state:
            _notify_terraform(resource, current_res.state.value, current_problem, console, creds)
            state = current_problem
        elif current_problem is None and state is not None:
             state = None # resolved
             
        if console is not None and current_problem == state:
            console.print(f"[dim]{resource}: State {current_res.state.value}, no new problems[/dim]")
            
        iterations += 1
        if max_iterations is None or iterations < max_iterations:
            time.sleep(interval)

    return state


# ── M5 (spec §4d): one multi-connector watch loop over the Connector interface ──
# Before this, AWS and GCP each had their own near-identical ~55-line loop, and a
# third (terraform) and the k8s pod-problem loop lived separately. The AWS/GCP
# pair was pure copy-paste over the same interface calls (poll_state + get_stats),
# so they now share ONE loop that drives *any* connector — and reads every watch
# in a cycle in PARALLEL, not one-after-another (the §3 "parallel vs sequential"
# speed lever). k8s's richer pod-problem model (run_watch_loop / detect_changes)
# and terraform's drift model stay specialized — they aren't get_stats time
# series — so no connector loses a capability it had (§4e).

def _notify_event(provider: str, target: str, event_type: str, summary: str,
                  console=None, creds: dict | None = None) -> None:
    """One notification path for every interface-driven connector watch."""
    title = f"Prash: {provider} {event_type} — {target}"
    fix_hint = f"prash fix {target}" + (f" --provider {provider}" if provider != "kubernetes" else "")
    message = f"{summary}. Run `{fix_hint}` to diagnose."
    if not _send_desktop_notification(title, message):
        logger.warning("Desktop notification failed on every available path — console only")
    if creds:
        results = send_team_notifications(creds, title, message)
        failed = [channel for channel, ok in results.items() if not ok]
        if failed:
            logger.warning(f"team notification failed: {', '.join(failed)}")
        elif results:
            logger.info(f"team notification sent: {', '.join(results)}")
    if console is not None:
        console.print(f"[bold red]⚠ {title}[/bold red]\n  {message}")


def _read_watch(connector, target: str, since):
    """Read one connector's poll_state + get_stats for `target`. Never raises —
    a single flaky connector must not take down a multi-connector cycle; it
    returns (state_value_or_None, events, error_or_None)."""
    state_value = None
    events: list = []
    err = None
    try:
        state_value = connector.poll_state(target).state.value
    except Exception as exc:  # noqa: BLE001 — one bad read can't kill the loop
        err = exc
    try:
        events = connector.get_stats(target, since=since)
    except NotImplementedError:
        pass  # connector doesn't expose a time series; poll_state alone is fine
    except Exception as exc:  # noqa: BLE001
        err = err or exc
    return state_value, events, err


def run_connector_watch_loop(
    watches: list[tuple],
    interval: int | None = None,
    console=None,
    max_iterations: int | None = None,
    creds: dict | None = None,
) -> dict:
    """The one interface-driven watch loop. `watches` is a list of
    (connector, target, provider_label). Each cycle reads every watch in
    PARALLEL, then notifies once per state change and once per new get_stats
    event (the same dedup model the old AWS/GCP loops used). Returns the
    per-watch dedup state keyed by (provider_label, target)."""
    import datetime

    interval = interval or _interval_from_env()
    seen: dict[tuple, dict] = {(p, t): {} for (_c, t, p) in watches}
    iterations = 0
    last_poll = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=interval)

    while max_iterations is None or iterations < max_iterations:
        # Parallel fan-out: N connector reads take ~max(one read), not the sum.
        if len(watches) > 1:
            with ThreadPoolExecutor(max_workers=len(watches)) as pool:
                results = list(pool.map(lambda w: _read_watch(w[0], w[1], last_poll), watches))
        else:
            results = [_read_watch(watches[0][0], watches[0][1], last_poll)] if watches else []

        for (_conn, target, provider), (state_value, events, err) in zip(watches, results):
            st = seen[(provider, target)]
            if err is not None and console is not None:
                console.print(f"[yellow]Error polling {provider} {target}: {err}[/yellow]")

            # State-change notification (degraded/failed/unknown -> notify once).
            if state_value in ("degraded", "failed", "unknown"):
                if st.get("instance_state") != state_value:
                    _notify_event(provider, target, state_value,
                                  f"Instance is in state: {state_value}", console, creds)
                    st["instance_state"] = state_value
            elif state_value == "healthy":
                st["instance_state"] = "healthy"

            # New-event notifications from get_stats.
            new_events = False
            for event in events:
                et = event["event_type"]
                ts = event["timestamp"]
                if hasattr(ts, "tzinfo") and ts.tzinfo is None:
                    ts = ts.replace(tzinfo=datetime.timezone.utc)
                if et not in st or st[et] < ts:
                    _notify_event(provider, target, et, event["summary"], console, creds)
                    st[et] = ts
                    new_events = True

            if console is not None and st.get("instance_state") == "healthy" and not new_events:
                console.print(f"[dim]{target}: Healthy, no new issues[/dim]")

        last_poll = datetime.datetime.now(datetime.timezone.utc)
        iterations += 1
        if max_iterations is None or iterations < max_iterations:
            time.sleep(interval)

    return seen


def run_aws_watch_loop(target, interval=None, console=None, max_iterations=None, creds=None):
    """AWS EC2 watch — now a thin wrapper over the shared interface loop."""
    conn = AWSConnector(creds or {})
    seen = run_connector_watch_loop(
        [(conn, target, "aws")], interval=interval, console=console,
        max_iterations=max_iterations, creds=creds,
    )
    return seen.get(("aws", target), {})


def run_gcp_watch_loop(target, interval=None, console=None, max_iterations=None, creds=None):
    """GCP Compute watch — now a thin wrapper over the shared interface loop."""
    from .connectors.gcp import GCPConnector

    conn = GCPConnector(creds or {})
    seen = run_connector_watch_loop(
        [(conn, target, "gcp")], interval=interval, console=console,
        max_iterations=max_iterations, creds=creds,
    )
    return seen.get(("gcp", target), {})
