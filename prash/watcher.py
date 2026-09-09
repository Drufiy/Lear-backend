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
from prash.connectors.datadog import DatadogConnector, DatadogError
from prash.connectors.pagerduty import PagerDutyConnector, PagerDutyError
from prash.connectors.github import GitHubConnector, GitHubError
from prash.connectors.gitlab import GitLabConnector, GitLabError
from prash.connectors.base import ConnectorEvent, ConnectorState
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

    Found live, verifying the Datadog loop on Windows (2026-09-07): plyer's
    win32 balloon backend packs the toast title/message into NOTIFYICONDATAW's
    fixed-size struct fields (packed at 64 chars in this build). Longer text
    raises "ValueError: string too long" inside plyer's own balloon_tip worker
    thread -- AFTER notify() has returned True -- so the caller can neither
    catch it nor know the toast never displayed. The only correct handling at
    this layer is to keep the strings within the packed limit: _toast_clamp
    below. The full text is unaffected everywhere else (console, team
    channels); the OS toast is the only surface with the hard cap.
    """
    try:
        from plyer import notification

        notification.notify(
            title=_toast_clamp(title), message=_toast_clamp(message), timeout=10
        )
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


def _toast_clamp(text: str, limit: int = 64) -> str:
    """Fit text into plyer's win32 balloon struct limit (see
    _send_desktop_notification's 2026-09-07 note). The trailing ellipsis
    marks truncation; the full text still reaches the console and every
    team channel -- only the OS toast is capped."""
    return text if len(text) <= limit else text[: limit - 1] + "…"


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


def _console_notify(console, text: str) -> None:
    """Render a console line without dying on consoles whose codepage can't
    encode it. Found live 2026-09-09: on a cp1252 legacy Windows console rich
    buffers the text and raises UnicodeEncodeError only at flush time -- the
    bad segment stays in the Console's buffer and kills the NEXT print too
    (even a plain-ASCII one), which is how the whole watch loop died on its
    first alert. So sanitize up front for the console's own encoding (the ⚠
    marker degrades to '?') and never hand rich an unencodable character."""
    if console is None:
        return
    try:
        text.encode(getattr(console, "encoding", None) or "ascii")
    except (UnicodeEncodeError, LookupError):
        text = text.encode("ascii", "replace").decode("ascii")
    console.print(text)


def _notify_datadog(event: ConnectorEvent, console=None, creds: dict | None = None) -> None:
    """Same desktop+team+console path as _notify/_notify_terraform, for a
    Datadog monitor state transition. Recoveries are notified too (unlike a
    resolved pod problem) -- a monitor returning to OK is actionable signal."""
    raw = event.get("raw") or {}
    monitor = raw.get("monitor_name") or raw.get("monitor_id") or event["summary"]
    title = f"Prash: {event['summary']}"
    message = (
        f"Datadog monitor {monitor}: {event['event_type']}. "
        f"Run `prash investigate {monitor} --provider datadog` to diagnose."
    )
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
        _console_notify(console, f"[bold red]⚠ {title}[/bold red]\n  {message}")


def resolve_datadog_monitors(spec: str | None, creds: dict | None = None) -> list[str]:
    """Turn a --resource spec (or the DATADOG_WATCH_MONITORS env value) into
    watch targets. Comma-separated monitor ids/names, or the literal `all`
    to watch every monitor on the site (capped at 100 -- polling a whole
    account is always an explicit choice, never a default)."""
    value = (spec or os.environ.get("DATADOG_WATCH_MONITORS") or "").strip()
    if not value:
        raise ValueError(
            "no Datadog watch targets: pass --resource monitor1,monitor2 "
            "or set DATADOG_WATCH_MONITORS (comma-separated names/ids, or `all`)"
        )
    if value.lower() == "all":
        connector = DatadogConnector(creds or {})
        monitors = connector.list_monitors(limit=100)
        return [monitor["name"] or str(monitor["monitor_id"]) for monitor in monitors]
    return [part.strip() for part in value.split(",") if part.strip()]


# ── Shared loop for the WatchHandle.poll() model (Datadog, PagerDuty) ──
# Distinct from run_connector_watch_loop below: here dedup lives INSIDE the
# connector's WatchHandle (poll() returns only new events since last call --
# e.g. PagerDuty's "same incident, same state -> silence" contract), not in
# the loop. Datadog's and PagerDuty's watch loops were two ~90-line, ~90%
# identical copies of the same build-handles/poll/notify/sleep shape; this is
# that pattern's one home, same principle as run_connector_watch_loop unifying
# the poll_state()+get_stats() family. Each connector keeps its own handle-
# building (target resolution needs provider-specific errors) and its own
# notify_fn (each renders a different message) -- only the loop body is shared.

def run_watchhandle_loop(
    handles: list,
    notify_fn,
    interval: int | None = None,
    console=None,
    max_iterations: int | None = None,
    creds: dict | None = None,
) -> None:
    """Poll a list of WatchHandles each cycle; `notify_fn(event, console, creds)`
    is the provider-specific notification path. A poll error (rate limit
    exhausted, network down) warns and skips that handle for the cycle -- the
    loop never dies on a bad API day. A notification error (dead toast path, a
    console whose codepage can't render the alert) warns and moves on for the
    same reason. max_iterations is None for the real `prash watch` command
    (runs until Ctrl+C); set to a small int in tests."""
    interval = interval or _interval_from_env()
    iterations = 0
    while max_iterations is None or iterations < max_iterations:
        for handle in handles:
            try:
                events = handle.poll()
            except Exception as exc:  # noqa: BLE001 — a bad API day can't kill the loop
                logger.warning(f"poll failed for {handle.target!r}: {exc}")
                continue
            for event in events:
                try:
                    notify_fn(event, console, creds)
                except Exception as exc:  # noqa: BLE001 — nor can a bad notification day
                    logger.warning(f"notify failed for {handle.target!r}: {exc}")
            if console is not None and not events:
                _console_notify(console, f"[dim]{handle.target}: poll OK, no state changes[/dim]")

        iterations += 1
        if max_iterations is None or iterations < max_iterations:
            time.sleep(interval)


def run_datadog_watch_loop(
    monitors: list[str],
    interval: int | None = None,
    console=None,
    max_iterations: int | None = None,
    creds: dict | None = None,
) -> None:
    """Poll Datadog monitors via each connector.watch() handle
    (CONNECTOR_REWRITE_SPEC §4a/§4d) -- a thin wrapper over the shared
    WatchHandle loop. Every state transition a handle reports (Alert/Warn
    entry, recovery) fires the same desktop+team notification path."""
    interval = interval or _interval_from_env()
    connector = DatadogConnector(creds or {})
    if not connector.authenticate():
        logger.warning("Datadog credentials failed validation — watch will likely poll nothing")

    handles = []
    for monitor in monitors:
        try:
            handles.append(connector.watch(monitor, interval=interval))
        except DatadogError as exc:
            logger.warning(f"could not watch monitor {monitor!r}: {exc}")
            if console is not None:
                console.print(f"[yellow]skipping monitor {monitor}: {exc}[/yellow]")
    if not handles:
        if console is not None:
            console.print("[yellow]no Datadog monitors to watch[/yellow]")
        return

    run_watchhandle_loop(handles, _notify_datadog, interval=interval, console=console,
                          max_iterations=max_iterations, creds=creds)


def _notify_pagerduty(event: ConnectorEvent, console=None, creds: dict | None = None) -> None:
    """Same desktop+team+console path as _notify_datadog, for a PagerDuty
    incident transition. Resolutions are notified too -- an incident closing
    is the "stand down" signal the team is waiting for."""
    raw = event.get("raw") or {}
    service = raw.get("service_name") or event.get("summary", "")
    title = f"Prash: {event['summary']}"
    message = (
        f"PagerDuty {service}: {event['event_type']}. "
        f"Run `prash investigate {service} --provider pagerduty` to diagnose."
    )
    if not _send_desktop_notification(title, message):
        logger.warning("Desktop notification failed on every available path — console only")
    if creds:
        results = send_team_notifications(creds, title, message)
        failed = [channel for channel, ok in results.items() if not ok]
        if failed:
            logger.warning(f"team notification failed: {', '.join(failed)}")
        elif results:
            logger.info(f"team notification sent: {', '.join(results)}")
    _console_notify(console, f"[bold red]⚠ {title}[/bold red]\n  {message}")


def resolve_pagerduty_services(spec: str | None, creds: dict | None = None) -> list[str]:
    """Turn a --resource spec (or the PAGERDUTY_WATCH_SERVICES env value) into
    watch targets. Comma-separated service names/ids, or the literal `all`
    to watch every service (capped at 100 -- watching the whole account pages
    on every trigger anywhere, which must always be explicit)."""
    value = (spec or os.environ.get("PAGERDUTY_WATCH_SERVICES") or "").strip()
    if not value:
        raise ValueError(
            "no PagerDuty watch targets: pass --resource service1,service2 "
            "or set PAGERDUTY_WATCH_SERVICES (comma-separated names/ids, or `all`)"
        )
    if value.lower() == "all":
        connector = PagerDutyConnector(creds or {})
        services = connector.list_services(limit=100)
        return [service["name"] or str(service["service_id"]) for service in services]
    return [part.strip() for part in value.split(",") if part.strip()]


def run_pagerduty_watch_loop(
    services: list[str],
    interval: int | None = None,
    console=None,
    max_iterations: int | None = None,
    creds: dict | None = None,
) -> None:
    """Poll PagerDuty services via each connector.watch() handle
    (CONNECTOR_REWRITE_SPEC §4a/§4d) -- a thin wrapper over the shared
    WatchHandle loop. Every incident transition a handle reports (new
    trigger, acknowledgment, resolution, escalation) fires the same
    desktop+team notification path."""
    interval = interval or _interval_from_env()
    connector = PagerDutyConnector(creds or {})
    if not connector.authenticate():
        logger.warning("PagerDuty credentials failed validation — watch will likely poll nothing")

    handles = []
    for service in services:
        try:
            handles.append(connector.watch(service, interval=interval))
        except PagerDutyError as exc:
            logger.warning(f"could not watch service {service!r}: {exc}")
            if console is not None:
                console.print(f"[yellow]skipping service {service}: {exc}[/yellow]")
    if not handles:
        if console is not None:
            console.print("[yellow]no PagerDuty services to watch[/yellow]")
        return

    run_watchhandle_loop(handles, _notify_pagerduty, interval=interval, console=console,
                          max_iterations=max_iterations, creds=creds)


def _notify_github(event: ConnectorEvent, console=None, creds: dict | None = None) -> None:
    """Same desktop+team+console path as _notify_datadog, for a GitHub Actions
    workflow-run transition. A run newly failing (or a rerun flipping outcome)
    is the actionable signal; `prash fix <repo> --ci` is the diagnose entry."""
    raw = event.get("raw") or {}
    repo = raw.get("repo") or event.get("summary", "")
    title = f"Prash: {event['summary']}"
    message = (
        f"GitHub Actions {repo}: {event['event_type']}. "
        f"Run `prash fix {repo} --ci` to diagnose."
    )
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


def resolve_github_repos(spec: str | None, creds: dict | None = None) -> list[str]:
    """Turn a --resource spec (or the GITHUB_WATCH_REPOS env value) into watch
    targets: comma-separated `owner/repo` entries. No `all` option -- a token
    can reach thousands of repos, so watched repos are always explicit."""
    value = (spec or os.environ.get("GITHUB_WATCH_REPOS") or "").strip()
    if not value:
        raise ValueError(
            "no GitHub watch targets: pass --resource owner/repo1,owner/repo2 "
            "or set GITHUB_WATCH_REPOS (comma-separated owner/repo)"
        )
    return [part.strip() for part in value.split(",") if part.strip()]


def run_github_watch_loop(
    repos: list[str],
    interval: int | None = None,
    console=None,
    max_iterations: int | None = None,
    creds: dict | None = None,
) -> None:
    """Watch GitHub repos' workflow runs via each connector.watch() handle
    (§4a) -- a thin wrapper over the shared WatchHandle loop. A run newly
    completing as failure (or a rerun flipping outcome) fires the same
    desktop+team notification path as the other connectors."""
    interval = interval or _interval_from_env()
    connector = GitHubConnector(creds or {})
    if not connector.authenticate():
        logger.warning("GitHub credentials failed validation — watch will likely poll nothing")

    handles = []
    for repo in repos:
        try:
            handles.append(connector.watch(repo, interval=interval))
        except GitHubError as exc:
            logger.warning(f"could not watch repo {repo!r}: {exc}")
            if console is not None:
                console.print(f"[yellow]skipping repo {repo}: {exc}[/yellow]")
    if not handles:
        if console is not None:
            console.print("[yellow]no GitHub repos to watch[/yellow]")
        return

    run_watchhandle_loop(handles, _notify_github, interval=interval, console=console,
                          max_iterations=max_iterations, creds=creds)


def _notify_gitlab(event: ConnectorEvent, console=None, creds: dict | None = None) -> None:
    """Same desktop+team+console path as _notify_github, for a GitLab pipeline
    transition. A pipeline newly failing (or a retry flipping status) is the
    actionable signal; `prash fix <project> --ci --provider gitlab` diagnoses."""
    raw = event.get("raw") or {}
    project = raw.get("project") or event.get("summary", "")
    title = f"Prash: {event['summary']}"
    message = (
        f"GitLab CI {project}: {event['event_type']}. "
        f"Run `prash fix {project} --ci --provider gitlab` to diagnose."
    )
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


def resolve_gitlab_projects(spec: str | None, creds: dict | None = None) -> list[str]:
    """Turn a --resource spec (or the GITLAB_WATCH_PROJECTS env value) into
    watch targets: comma-separated `namespace/project` entries (subgroups
    allowed). No `all` -- watched projects are always explicit."""
    value = (spec or os.environ.get("GITLAB_WATCH_PROJECTS") or "").strip()
    if not value:
        raise ValueError(
            "no GitLab watch targets: pass --resource namespace/project1,namespace/project2 "
            "or set GITLAB_WATCH_PROJECTS (comma-separated namespace/project)"
        )
    return [part.strip() for part in value.split(",") if part.strip()]


def run_gitlab_watch_loop(
    projects: list[str],
    interval: int | None = None,
    console=None,
    max_iterations: int | None = None,
    creds: dict | None = None,
) -> None:
    """Watch GitLab projects' pipelines via each connector.watch() handle
    (§4a) -- a thin wrapper over the shared WatchHandle loop. A pipeline newly
    failing (or a retry flipping status) fires the same desktop+team
    notification path as the other connectors."""
    interval = interval or _interval_from_env()
    connector = GitLabConnector(creds or {})
    if not connector.authenticate():
        logger.warning("GitLab credentials failed validation — watch will likely poll nothing")

    handles = []
    for project in projects:
        try:
            handles.append(connector.watch(project, interval=interval))
        except GitLabError as exc:
            logger.warning(f"could not watch project {project!r}: {exc}")
            if console is not None:
                console.print(f"[yellow]skipping project {project}: {exc}[/yellow]")
    if not handles:
        if console is not None:
            console.print("[yellow]no GitLab projects to watch[/yellow]")
        return

    run_watchhandle_loop(handles, _notify_gitlab, interval=interval, console=console,
                          max_iterations=max_iterations, creds=creds)


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
