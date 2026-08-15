"""GitHub connector. Drives the open-pr action end to end via the REST API.

Uses only the standard library (urllib) so the agent has zero network deps
beyond what ships with Python.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Mapping

from .base import Connector, ConnectorState, ResourceState

API_URL = "https://api.github.com"
VERSION = "2022-11-28"


class GitHubError(RuntimeError):
    pass


class GitHubConnector(Connector):
    name = "github"
    read_capabilities = ("workflow_logs", "repo", "check_runs")
    write_capabilities = ("open_pr", "re_run_job", "apply_fix")

    def __init__(self, credentials: Mapping[str, Any]):
        super().__init__(credentials)
        self.token = credentials.get("GITHUB_TOKEN")
        self.headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": VERSION,
        }
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"

    def _request(self, method: str, path: str, body: Any = None) -> Any:
        url = f"{API_URL}{path}"
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            self.headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=self.headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise GitHubError(f"GitHub API {exc.code}: {detail}") from exc

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

    def re_run_job(self, repo: str, run_id: int) -> Dict[str, Any]:
        return self._request("POST", f"/repos/{repo}/actions/runs/{run_id}/rerun")

    def workflow_runs(self, repo: str, branch: str = "", limit: int = 5) -> list[Dict[str, Any]]:
        qs = f"?per_page={limit}" + (f"&branch={branch}" if branch else "")
        return self._request("GET", f"/repos/{repo}/actions/runs{qs}")

    def poll_state(self, resource: str, **kwargs: Any) -> ResourceState:
        run = self.locate(resource)
        runs = self.workflow_runs(run["repo"], branch=kwargs.get("branch", ""))
        if not runs:
            return ResourceState(resource, ConnectorState.NOT_FOUND, {"runs": 0})
        status = runs[0].get("status"), runs[0].get("conclusion")
        state = ConnectorState.FAILED if status[1] == "failure" else ConnectorState.DEGRADED
        if status[0] == "completed" and status[1] in ("success", "neutral"):
            state = ConnectorState.HEALTHY
        elif status[0] == "in_progress":
            state = ConnectorState.DEPLOYING
        return ResourceState(resource, state, {"latest_run": runs[0]})


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
