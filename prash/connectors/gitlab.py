"""GitLab connector (Sprint 2 Tier 2, PRASH_V2.md §7b — Aradhya, "highest
overlap, proven connector pattern"). Mirrors GitHubConnector's shape
(authenticate -> locate -> fetch logs -> poll state) so the rest of the
pipeline (fix.py, apply_gitlab_ci_fix.py) reads the same way it does for
GitHub -- but the write path is genuinely simpler here, not just renamed:
GitLab's Commits API creates a branch (via ``start_branch``) and a commit
with multiple file actions in a single call, with no GitHub-style
blob/tree/commit dance.

Uses only the standard library (urllib), same reasoning as github.py: zero
network deps beyond what ships with Python.

Scoped to gitlab.com only for v1 -- self-hosted GitLab (a configurable API
base URL) is real functionality some teams will want, but nobody has asked
for it yet and it's a one-line change to add later. Not building it
speculatively.
"""

from __future__ import annotations

import datetime
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Mapping, Optional

from .base import Connector, ConnectorEvent, ConnectorState, ResourceState, WatchHandle

API_URL = "https://gitlab.com/api/v4"

# Rate-limit / transient handling for the watch loop, mirroring the GitHub
# connector. GitLab.com allows 2000 req/min authenticated; a watch poll is
# one call per project.
_TRANSIENT_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_BACKOFF_CAP = 30.0

# GitLab pipeline status -> ConnectorEvent type. Anything not terminal
# (running/pending/created/preparing/...) is treated as in-progress.
_PIPELINE_EVENT_TYPE = {
    "failed": "ci_failure",
    "success": "ci_success",
    "canceled": "ci_cancelled",
}


class GitLabError(RuntimeError):
    pass


def _parse_ts(value: Optional[str]) -> Optional[datetime.datetime]:
    """Parse a GitLab ISO-8601 timestamp to tz-aware UTC. None/unparseable
    -> None (skipped by callers)."""
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(datetime.timezone.utc)
    except (TypeError, ValueError):
        return None


class GitLabConnector(Connector):
    name = "gitlab"
    read_capabilities = ("pipeline_logs", "repo", "jobs", "watch", "stats")
    write_capabilities = ("open_mr", "apply_fix", "alert")

    def __init__(self, credentials: Mapping[str, Any]):
        super().__init__(credentials)
        self.token = credentials.get("GITLAB_TOKEN")
        self.headers = {"Accept": "application/json"}
        if self.token:
            self.headers["PRIVATE-TOKEN"] = self.token

    @staticmethod
    def _backoff_seconds(attempt: int, exc: urllib.error.HTTPError) -> float:
        """Capped exponential backoff; honor GitLab's rate-limit signals. A 429
        may send `Retry-After` (seconds); GitLab also sends `RateLimit-Remaining`
        + `RateLimit-Reset` (epoch seconds) -- wait until reset, capped, so a
        watch loop never busy-spins an exhausted quota."""
        headers = getattr(exc, "headers", None)
        if headers is not None:
            retry_after = headers.get("Retry-After")
            if retry_after:
                try:
                    return min(float(retry_after), _BACKOFF_CAP)
                except (TypeError, ValueError):
                    pass
            if headers.get("RateLimit-Remaining") == "0":
                reset = headers.get("RateLimit-Reset")
                try:
                    delta = float(reset) - time.time()
                    if delta > 0:
                        return min(delta, _BACKOFF_CAP)
                except (TypeError, ValueError):
                    pass
        return min(2 ** attempt, _BACKOFF_CAP)

    def _request(self, method: str, path: str, body: Any = None) -> Any:
        url = f"{API_URL}{path}"
        data = None
        headers = dict(self.headers)
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        attempt = 0
        while True:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    raw = resp.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as exc:
                if exc.code in _TRANSIENT_STATUS and attempt < _MAX_RETRIES:
                    time.sleep(self._backoff_seconds(attempt, exc))
                    attempt += 1
                    continue
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                raise GitLabError(f"GitLab API {exc.code}: {detail}") from exc
            except (TimeoutError, urllib.error.URLError) as exc:
                if attempt < _MAX_RETRIES:
                    time.sleep(min(2 ** attempt, _BACKOFF_CAP))
                    attempt += 1
                    continue
                raise GitLabError(f"GitLab API unreachable: {exc}") from exc

    def _request_text(self, path: str) -> str:
        """Like _request, but for endpoints that return plain text (job
        traces), not JSON -- GitLab's trace endpoint is the one place in
        this connector where the response isn't a JSON document."""
        url = f"{API_URL}{path}"
        req = urllib.request.Request(url, headers=self.headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise GitLabError(f"GitLab API {exc.code}: {detail}") from exc

    def authenticate(self) -> bool:
        if not self.token:
            return False
        try:
            self._request("GET", "/user")
            return True
        except GitLabError:
            return False

    def locate(self, resource: str) -> Dict[str, Any]:
        if resource.count("/") < 1:
            raise GitLabError(f"expected 'namespace/project' (subgroups allowed), got {resource!r}")
        return {"project": resource, "project_id": urllib.parse.quote(resource, safe="")}

    def get_repo(self, project: str) -> Dict[str, Any]:
        pid = self.locate(project)["project_id"]
        return self._request("GET", f"/projects/{pid}")

    def get_branch_head_sha(self, project: str, branch: str) -> str:
        pid = self.locate(project)["project_id"]
        ref = self._request("GET", f"/projects/{pid}/repository/branches/{urllib.parse.quote(branch, safe='')}")
        return ref["commit"]["id"]

    def get_file_content(self, project: str, path: str, ref: str) -> str:
        """Fetch a file's current raw text content at a specific ref (commit
        SHA or branch). GitLab's raw-file endpoint returns the content
        directly as text -- no base64 decode step, unlike GitHub's Contents
        API."""
        pid = self.locate(project)["project_id"]
        quoted_path = urllib.parse.quote(path, safe="")
        return self._request_text(f"/projects/{pid}/repository/files/{quoted_path}/raw?ref={urllib.parse.quote(ref, safe='')}")

    def create_commit(
        self,
        project: str,
        branch: str,
        message: str,
        actions: List[Dict[str, Any]],
        start_branch: str | None = None,
    ) -> Dict[str, Any]:
        """One-shot branch-create + multi-file commit via GitLab's Commits
        API. When ``start_branch`` is given and ``branch`` doesn't already
        exist, GitLab creates it from ``start_branch`` as part of this same
        call -- the GitHub connector needs create_ref as a separate step
        (git.py's blob/tree/commit/ref sequence) because the Git Data API
        has no equivalent one-call primitive.

        Each action is a dict shaped like GitLab's API expects, e.g.
        {"action": "update", "file_path": "...", "content": "..."}.
        """
        pid = self.locate(project)["project_id"]
        payload: Dict[str, Any] = {"branch": branch, "commit_message": message, "actions": actions}
        if start_branch:
            payload["start_branch"] = start_branch
        return self._request("POST", f"/projects/{pid}/repository/commits", payload)

    def create_mr(self, project: str, title: str, source_branch: str, target_branch: str, body: str = "") -> Dict[str, Any]:
        pid = self.locate(project)["project_id"]
        payload = {
            "source_branch": source_branch,
            "target_branch": target_branch,
            "title": title,
            "description": body,
        }
        return self._request("POST", f"/projects/{pid}/merge_requests", payload)

    def get_mr(self, project: str, iid: int) -> Dict[str, Any]:
        pid = self.locate(project)["project_id"]
        return self._request("GET", f"/projects/{pid}/merge_requests/{iid}")

    def create_issue(self, project: str, title: str, body: str = "") -> Dict[str, Any]:
        """Open a GitLab issue (the gitlab-open-issue alert action, §4b). Needs
        the token to have `api` scope (issue write)."""
        pid = self.locate(project)["project_id"]
        return self._request("POST", f"/projects/{pid}/issues", {"title": title, "description": body})

    def get_issue(self, project: str, iid: int) -> Dict[str, Any]:
        pid = self.locate(project)["project_id"]
        return self._request("GET", f"/projects/{pid}/issues/{iid}")

    def list_pipelines(self, project: str, ref: str = "", limit: int = 5) -> List[Dict[str, Any]]:
        pid = self.locate(project)["project_id"]
        qs = f"?per_page={limit}" + (f"&ref={urllib.parse.quote(ref, safe='')}" if ref else "")
        return self._request("GET", f"/projects/{pid}/pipelines{qs}")

    def pipeline_jobs(self, project: str, pipeline_id: int) -> List[Dict[str, Any]]:
        pid = self.locate(project)["project_id"]
        return self._request("GET", f"/projects/{pid}/pipelines/{pipeline_id}/jobs?per_page=100")

    def job_trace(self, project: str, job_id: int) -> str:
        pid = self.locate(project)["project_id"]
        return self._request_text(f"/projects/{pid}/jobs/{job_id}/trace")

    def poll_state(self, resource: str, **kwargs: Any) -> ResourceState:
        pipelines = self.list_pipelines(resource, ref=kwargs.get("branch", ""))
        if not pipelines:
            return ResourceState(resource, ConnectorState.NOT_FOUND, {"pipelines": 0})
        status = pipelines[0].get("status")
        state = {
            "success": ConnectorState.HEALTHY,
            "failed": ConnectorState.FAILED,
            "running": ConnectorState.DEPLOYING,
            "pending": ConnectorState.DEPLOYING,
            "canceled": ConnectorState.DEGRADED,
        }.get(status, ConnectorState.UNKNOWN)
        return ResourceState(resource, state, {"latest_pipeline": pipelines[0]})

    # ── watch()/get_stats() — the autonomous-loop read surface (§4a) ──

    def _pipeline_to_event(self, project: str, pipeline: Dict[str, Any]) -> ConnectorEvent:
        """One pipeline -> one ConnectorEvent. event_type keys off status
        (failed/success/canceled), or ci_in_progress for a non-terminal
        pipeline. timestamp is updated_at, falling back to created_at."""
        status = pipeline.get("status")
        event_type = _PIPELINE_EVENT_TYPE.get(status or "", "ci_in_progress")
        ts = _parse_ts(pipeline.get("updated_at")) or _parse_ts(pipeline.get("created_at")) or datetime.datetime.now(datetime.timezone.utc)
        ref = pipeline.get("ref") or "?"
        sha = (pipeline.get("sha") or "")[:8]
        return ConnectorEvent(
            timestamp=ts,
            connector=self.name,
            event_type=event_type,
            summary=f"pipeline #{pipeline.get('id', '?')} {status or 'unknown'} on {ref} ({sha})",
            raw={"pipeline_id": pipeline.get("id"), "pipeline": pipeline, "project": project},
        )

    def get_stats(self, target: str, since: Optional[datetime.datetime] = None, **kwargs: Any) -> List[ConnectorEvent]:
        """Normalized timeline of recent pipelines for a project (§4a) -- the
        time-series complement of poll_state()'s point-in-time health.
        Ascending by timestamp; everything at/after `since` (default: last
        hour). [] when the project has no pipelines or can't be reached."""
        if since is None:
            since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
        elif since.tzinfo is None:
            since = since.replace(tzinfo=datetime.timezone.utc)
        try:
            pipelines = self.list_pipelines(target, ref=kwargs.get("branch", ""), limit=kwargs.get("limit", 30))
        except GitLabError:
            return []
        events = [self._pipeline_to_event(target, p) for p in pipelines]
        events = [event for event in events if event["timestamp"] >= since]
        events.sort(key=lambda event: event["timestamp"])
        return events

    def watch(self, target: str, interval: int = 30) -> WatchHandle:
        """Begin watching a project's pipelines (§4a). The returned handle
        polls /pipelines and emits a ConnectorEvent only when a pipeline newly
        fails, or a previously-seen pipeline changes status (e.g. a retry turns
        failed -> success). Dedup by pipeline id + status -- same incident-dedup
        model as PagerDuty/GitHub, so the same failed pipeline never re-notifies."""
        self.locate(target)  # validate 'namespace/project' shape up front
        return _GitLabWatchHandle(self, target, interval, last_state={})


class _GitLabWatchHandle(WatchHandle):
    """Per-project watch handle: one poll() = one /pipelines list, diffed per
    pipeline. Dedup contract: the same pipeline in the same status across polls
    is silent -- only a pipeline newly failing, or an already-seen pipeline
    changing status, emits an event."""

    def __init__(self, connector: "GitLabConnector", project: str, interval: int,
                 last_state: Dict[Any, str]):
        self.connector = connector.name
        self.target = project
        self.interval = interval
        self._gl = connector
        self._project = project
        self._last_state = last_state  # {pipeline_id: status}

    def poll(self) -> List[ConnectorEvent]:
        pipelines = self._gl.list_pipelines(self._project, limit=30)
        events: List[ConnectorEvent] = []
        for pipeline in pipelines:
            pid = pipeline.get("id")
            if pid is None:
                continue
            status = pipeline.get("status")
            previous = self._last_state.get(pid)
            self._last_state[pid] = status
            if previous is None:
                # First sighting: a currently-failed pipeline is worth
                # surfacing now; anything else predates the watch -> baseline
                # silently (mirrors GitHub/PagerDuty first-sight rule).
                if status == "failed":
                    events.append(self._gl._pipeline_to_event(self._project, pipeline))
                continue
            if previous != status:
                events.append(self._gl._pipeline_to_event(self._project, pipeline))
        return events
