"""GitHub connector. Drives the open-pr action end to end via the REST API.

Uses only the standard library (urllib) so the agent has zero network deps
beyond what ships with Python.
"""

from __future__ import annotations

import base64
import datetime
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Mapping, Optional

from .base import Connector, ConnectorEvent, ConnectorState, ResourceState, WatchHandle

API_URL = "https://api.github.com"
VERSION = "2022-11-28"

# Rate-limit / transient-error handling for the watch loop, matching the
# Datadog/PagerDuty connectors' posture (429 + Retry-After honored). GitHub's
# REST API is 5000 req/hr authenticated; a watch poll is 1 call per repo.
_TRANSIENT_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_BACKOFF_CAP = 30.0

# Which workflow-run outcomes map to which ConnectorEvent type.
_RUN_EVENT_TYPE = {
    "failure": "ci_failure",
    "timed_out": "ci_failure",
    "startup_failure": "ci_failure",
    "success": "ci_success",
    "neutral": "ci_success",
    "cancelled": "ci_cancelled",
}


class GitHubError(RuntimeError):
    pass


def _parse_ts(value: Optional[str]) -> Optional[datetime.datetime]:
    """Parse a GitHub ISO-8601 timestamp (e.g. '2026-09-06T20:33:51Z') to a
    tz-aware UTC datetime. None/unparseable -> None (skipped by callers)."""
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(datetime.timezone.utc)
    except (TypeError, ValueError):
        return None


class GitHubConnector(Connector):
    name = "github"
    read_capabilities = ("workflow_logs", "repo", "check_runs", "watch", "stats")
    write_capabilities = ("open_pr", "re_run_job", "apply_fix", "alert")

    def __init__(self, credentials: Mapping[str, Any]):
        super().__init__(credentials)
        self.token = credentials.get("GITHUB_TOKEN")
        self.headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": VERSION,
        }
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"

    @staticmethod
    def _backoff_seconds(attempt: int, exc: urllib.error.HTTPError) -> float:
        """Capped exponential backoff; honor GitHub's rate-limit signals when
        present. A 429 (secondary limit) sends `Retry-After` (seconds); a
        primary-limit 403 sends `X-RateLimit-Remaining: 0` + `X-RateLimit-Reset`
        (epoch seconds) -- wait until reset, capped, so a watch loop never busy-
        spins against an exhausted quota."""
        headers = getattr(exc, "headers", None)
        if headers is not None:
            retry_after = headers.get("Retry-After")
            if retry_after:
                try:
                    return min(float(retry_after), _BACKOFF_CAP)
                except (TypeError, ValueError):
                    pass
            if headers.get("X-RateLimit-Remaining") == "0":
                reset = headers.get("X-RateLimit-Reset")
                try:
                    delta = float(reset) - time.time()
                    if delta > 0:
                        return min(delta, _BACKOFF_CAP)
                except (TypeError, ValueError):
                    pass
        return min(2 ** attempt, _BACKOFF_CAP)

    def _is_rate_limited_403(self, exc: urllib.error.HTTPError) -> bool:
        headers = getattr(exc, "headers", None)
        return exc.code == 403 and headers is not None and headers.get("X-RateLimit-Remaining") == "0"

    def _request(self, method: str, path: str, body: Any = None) -> Any:
        url = f"{API_URL}{path}"
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            self.headers["Content-Type"] = "application/json"
        attempt = 0
        while True:
            req = urllib.request.Request(url, data=data, headers=self.headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    raw = resp.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as exc:
                retryable = exc.code in _TRANSIENT_STATUS or self._is_rate_limited_403(exc)
                if retryable and attempt < _MAX_RETRIES:
                    time.sleep(self._backoff_seconds(attempt, exc))
                    attempt += 1
                    continue
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                raise GitHubError(f"GitHub API {exc.code}: {detail}") from exc
            except (TimeoutError, urllib.error.URLError) as exc:
                if attempt < _MAX_RETRIES:
                    time.sleep(min(2 ** attempt, _BACKOFF_CAP))
                    attempt += 1
                    continue
                raise GitHubError(f"GitHub API unreachable: {exc}") from exc

    def authenticate(self) -> bool:
        if not self.token:
            return False
        try:
            self._request("GET", "/user")
            return True
        except GitHubError:
            return False

    def locate(self, resource: str) -> Dict[str, Any]:
        if resource.count("/") != 1:
            raise GitHubError(f"expected 'owner/repo', got {resource!r}")
        return {"repo": resource}

    def create_pr(self, repo: str, title: str, head: str, base: str, body: str = "") -> Dict[str, Any]:
        payload = {"title": title, "head": head, "base": base, "body": body}
        return self._request("POST", f"/repos/{repo}/pulls", payload)

    def get_repo(self, repo: str) -> Dict[str, Any]:
        return self._request("GET", f"/repos/{repo}")

    def get_branch_head_sha(self, repo: str, branch: str) -> str:
        ref = self._request("GET", f"/repos/{repo}/git/ref/heads/{branch}")
        return ref["object"]["sha"]

    def get_commit_tree_sha(self, repo: str, commit_sha: str) -> str:
        commit = self._request("GET", f"/repos/{repo}/git/commits/{commit_sha}")
        return commit["tree"]["sha"]

    def get_file_content(self, repo: str, path: str, ref: str) -> str:
        """Fetch a file's current raw text content at a specific ref (commit SHA or branch).

        Used to apply FileChange.edits against the real content right before
        writing the fix commit -- the same file identity apply_ci_fix.py just
        resolved base_sha from, so this reads exactly what the new commit
        will be built on top of.
        """
        quoted = urllib.parse.quote(path)
        data = self._request("GET", f"/repos/{repo}/contents/{quoted}?ref={ref}")
        if isinstance(data, list):
            raise GitHubError(f"{path} is a directory, not a file")
        content = data.get("content", "")
        return base64.b64decode(content).decode("utf-8")

    def create_blob(self, repo: str, content: str) -> str:
        blob = self._request("POST", f"/repos/{repo}/git/blobs", {"content": content, "encoding": "utf-8"})
        return blob["sha"]

    def create_tree(self, repo: str, base_tree_sha: str, entries: list[Dict[str, Any]]) -> str:
        tree = self._request("POST", f"/repos/{repo}/git/trees", {"base_tree": base_tree_sha, "tree": entries})
        return tree["sha"]

    def create_commit(self, repo: str, message: str, tree_sha: str, parent_sha: str) -> str:
        commit = self._request(
            "POST", f"/repos/{repo}/git/commits", {"message": message, "tree": tree_sha, "parents": [parent_sha]}
        )
        return commit["sha"]

    def create_ref(self, repo: str, branch: str, commit_sha: str) -> None:
        self._request("POST", f"/repos/{repo}/git/refs", {"ref": f"refs/heads/{branch}", "sha": commit_sha})

    def get_pr(self, repo: str, number: int) -> Dict[str, Any]:
        return self._request("GET", f"/repos/{repo}/pulls/{number}")

    def create_issue(self, repo: str, title: str, body: str = "") -> Dict[str, Any]:
        """Open a GitHub issue (the github-open-issue alert action, §4b). Needs
        `issues:write` (fine-grained) or `repo` (classic) on the token."""
        return self._request("POST", f"/repos/{repo}/issues", {"title": title, "body": body})

    def get_issue(self, repo: str, number: int) -> Dict[str, Any]:
        return self._request("GET", f"/repos/{repo}/issues/{number}")

    def re_run_job(self, repo: str, run_id: int) -> Dict[str, Any]:
        return self._request("POST", f"/repos/{repo}/actions/runs/{run_id}/rerun")

    def workflow_runs(self, repo: str, branch: str = "", limit: int = 5) -> list[Dict[str, Any]]:
        qs = f"?per_page={limit}" + (f"&branch={branch}" if branch else "")
        return self._request("GET", f"/repos/{repo}/actions/runs{qs}")["workflow_runs"]

    def run_jobs(self, repo: str, run_id: int) -> list[Dict[str, Any]]:
        """Jobs (with per-job conclusion) for one workflow run. Used to scope
        CI diagnosis to the jobs that actually failed, instead of every job in
        the run's log ZIP (a passing job's log has no failure to diagnose, and
        feeding it to the brain invites false positives — e.g. reporting a
        non-blocking lint warning as the failure)."""
        return self._request("GET", f"/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100").get("jobs", [])

    def failed_job_names(self, repo: str, run_id: int) -> set[str]:
        """Names of the jobs in a run whose conclusion is a genuine failure
        (failure/timed_out/startup_failure) -- cancelled/skipped/success are
        not diagnosable failures. Best-effort: [] set on any API error, so a
        caller falls back to diagnosing the whole run rather than nothing."""
        try:
            jobs = self.run_jobs(repo, run_id)
        except GitHubError:
            return set()
        failed = {"failure", "timed_out", "startup_failure"}
        return {j["name"] for j in jobs if j.get("conclusion") in failed and j.get("name")}

    def get_dependabot_alerts(self, repo: str, state: str = "open") -> list[Dict[str, Any]]:
        """Dependabot alerts (Sprint 2 Tier 3, PRASH_V2.md §7b) -- not a new
        connector, since this is a GitHub API capability, not a separate
        product with its own credentials. Needs the token to have Dependabot
        alerts read access (fine-grained PAT scope, or `security_events`/
        `repo` on a classic token for private repos). state defaults to
        "open" -- the ones actually worth a human's attention; pass "" for
        every alert regardless of state."""
        qs = f"?state={state}" if state else ""
        return self._request("GET", f"/repos/{repo}/dependabot/alerts{qs}")

    _STATE_SEVERITY = {
        ConnectorState.HEALTHY: 0,
        ConnectorState.DEPLOYING: 1,
        ConnectorState.DEGRADED: 2,
        ConnectorState.FAILED: 3,
    }

    @staticmethod
    def _run_state(run: Dict[str, Any]) -> ConnectorState:
        status, conclusion = run.get("status"), run.get("conclusion")
        if status == "in_progress":
            return ConnectorState.DEPLOYING
        if status == "completed" and conclusion == "failure":
            return ConnectorState.FAILED
        if status == "completed" and conclusion in ("success", "neutral"):
            return ConnectorState.HEALTHY
        return ConnectorState.DEGRADED

    def poll_state(self, resource: str, **kwargs: Any) -> ResourceState:
        run = self.locate(resource)
        runs = self.workflow_runs(run["repo"], branch=kwargs.get("branch", ""), limit=kwargs.get("limit", 20))
        if not runs:
            return ResourceState(resource, ConnectorState.NOT_FOUND, {"runs": 0})

        # A repo can have several workflows (CI, CodeQL, etc). Runs come back
        # newest-first across ALL of them, so the single most-recent run is
        # not a reliable health signal -- e.g. a fast CodeQL success completing
        # right after a genuinely broken CI run would mask the failure. Take
        # the latest run per workflow instead and surface the worst state.
        latest_per_workflow: Dict[Any, Dict[str, Any]] = {}
        for r in runs:
            wf_id = r.get("workflow_id")
            if wf_id not in latest_per_workflow:
                latest_per_workflow[wf_id] = r

        worst_run = None
        worst_state = ConnectorState.HEALTHY
        for r in latest_per_workflow.values():
            candidate = self._run_state(r)
            if self._STATE_SEVERITY[candidate] >= self._STATE_SEVERITY[worst_state]:
                worst_state = candidate
                worst_run = r

        return ResourceState(
            resource,
            worst_state,
            {"latest_run": worst_run, "runs_by_workflow": latest_per_workflow},
        )

    # ── watch()/get_stats() — the autonomous-loop read surface (§4a) ──

    def _run_to_event(self, repo: str, run: Dict[str, Any]) -> ConnectorEvent:
        """One workflow run -> one ConnectorEvent. event_type keys off the
        run's conclusion (failure/success/cancelled), or ci_in_progress for a
        run still executing. timestamp is updated_at (the state we're reacting
        to), falling back to created_at."""
        status, conclusion = run.get("status"), run.get("conclusion")
        if status != "completed":
            event_type = "ci_in_progress"
        else:
            event_type = _RUN_EVENT_TYPE.get(conclusion or "", "ci_other")
        ts = _parse_ts(run.get("updated_at")) or _parse_ts(run.get("created_at")) or datetime.datetime.now(datetime.timezone.utc)
        workflow = run.get("name") or run.get("display_title") or "workflow"
        branch = run.get("head_branch") or "?"
        sha = (run.get("head_sha") or "")[:7]
        outcome = conclusion or status or "unknown"
        return ConnectorEvent(
            timestamp=ts,
            connector=self.name,
            event_type=event_type,
            summary=f"{workflow} run #{run.get('run_number', '?')} {outcome} on {branch} ({sha})",
            raw={"run_id": run.get("id"), "run": run, "repo": repo},
        )

    def get_stats(self, target: str, since: Optional[datetime.datetime] = None, **kwargs: Any) -> List[ConnectorEvent]:
        """Normalized timeline of recent workflow runs for a repo (§4a) --
        the time-series complement of poll_state()'s point-in-time health.
        Ascending by timestamp; everything at/after `since` (default: last
        hour). [] when the repo has no runs or can't be reached, matching
        poll_state()'s not-found posture."""
        if since is None:
            since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
        elif since.tzinfo is None:
            since = since.replace(tzinfo=datetime.timezone.utc)
        handle = self.locate(target)
        try:
            runs = self.workflow_runs(handle["repo"], branch=kwargs.get("branch", ""), limit=kwargs.get("limit", 30))
        except GitHubError:
            return []
        events = [self._run_to_event(handle["repo"], run) for run in runs]
        events = [event for event in events if event["timestamp"] >= since]
        events.sort(key=lambda event: event["timestamp"])
        return events

    def watch(self, target: str, interval: int = 30) -> WatchHandle:
        """Begin watching a repo's workflow runs (§4a). The returned handle
        polls /actions/runs and emits a ConnectorEvent only when a run newly
        completes as a failure, or a previously-seen run changes outcome
        (e.g. a rerun turns failure -> success). Dedup is by run id +
        (status, conclusion) -- the same incident-dedup model as PagerDuty,
        so the same failed run never re-notifies across polls."""
        handle = self.locate(target)
        return _GitHubWatchHandle(self, handle["repo"], interval, last_state={})


class _GitHubWatchHandle(WatchHandle):
    """Per-repo watch handle: one poll() = one /actions/runs list, diffed per
    run. Dedup contract: the same run in the same (status, conclusion) across
    polls is silent -- only a run newly completing as failure, or an
    already-seen run changing outcome, emits an event."""

    def __init__(self, connector: "GitHubConnector", repo: str, interval: int,
                 last_state: Dict[Any, tuple]):
        self.connector = connector.name
        self.target = repo
        self.interval = interval
        self._gh = connector
        self._repo = repo
        self._last_state = last_state  # {run_id: (status, conclusion)}

    def poll(self) -> List[ConnectorEvent]:
        runs = self._gh.workflow_runs(self._repo, limit=30)
        events: List[ConnectorEvent] = []
        for run in runs:
            run_id = run.get("id")
            if run_id is None:
                continue
            key = (run.get("status"), run.get("conclusion"))
            previous = self._last_state.get(run_id)
            self._last_state[run_id] = key
            if previous is None:
                # First sighting: a run that's already broken is worth
                # surfacing now; a passing/in-progress run predates the watch
                # -> baseline it silently (mirrors PagerDuty's resolved-on-
                # -first-sight rule).
                if key[0] == "completed" and _RUN_EVENT_TYPE.get(key[1] or "") == "ci_failure":
                    events.append(self._gh._run_to_event(self._repo, run))
                continue
            if previous != key:
                # Outcome changed since last poll: a new failure, or a rerun
                # that flipped the result -- both are fresh signal.
                events.append(self._gh._run_to_event(self._repo, run))
        return events


class GitHubRunner:
    """Re-triggers the most recent failed run of a repo.

    Wired to request-secret so that after the value is stored locally, Prash
    actually re-runs the blocked job instead of reporting it needs manual
    follow-up. This closes the v1 `needs_secret` dead end end to end.
    """

    def __init__(self, connector: GitHubConnector):
        self.gh = connector

    def re_run(self, repo: str) -> int:
        runs = self.gh.workflow_runs(repo, limit=3)
        failed = [
            r for r in runs
            if r.get("status") == "completed" and r.get("conclusion") == "failure"
        ]
        if not failed:
            raise RuntimeError(f"no completed failed run found to re-run for {repo}")
        run_id = int(failed[0]["id"])
        self.gh.re_run_job(repo, run_id)
        return run_id
