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

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Mapping

from .base import Connector, ConnectorState, ResourceState

API_URL = "https://gitlab.com/api/v4"


class GitLabError(RuntimeError):
    pass


class GitLabConnector(Connector):
    name = "gitlab"
    read_capabilities = ("pipeline_logs", "repo", "jobs")
    write_capabilities = ("open_mr", "apply_fix")

    def __init__(self, credentials: Mapping[str, Any]):
        super().__init__(credentials)
        self.token = credentials.get("GITLAB_TOKEN")
        self.headers = {"Accept": "application/json"}
        if self.token:
            self.headers["PRIVATE-TOKEN"] = self.token

    def _request(self, method: str, path: str, body: Any = None) -> Any:
        url = f"{API_URL}{path}"
        data = None
        headers = dict(self.headers)
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise GitLabError(f"GitLab API {exc.code}: {detail}") from exc

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
