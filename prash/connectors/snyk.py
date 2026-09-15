"""Snyk connector (Sprint 2 Tier 3, PRASH_V2.md §7b).

Read-only for this sprint, same posture Datadog/Grafana shipped with --
security scanning state is worth surfacing before it's worth acting on
automatically (unlike PagerDuty, where Aradhya explicitly asked for write
actions from the start).

Snyk is org-scoped end to end: every project lives under an org id, so
SNYK_ORG_ID is a required credential, not optional -- there is no
account-wide "just give me everything" call. `resource` is a project id
(a UUID) or project name, resolved by listing `/v1/org/{orgId}/projects`
and matching client-side (no server-side name filter on that endpoint,
same known limitation already documented in the Grafana connector for the
same reason -- fine for v1, worth revisiting against an org with many
projects).

KNOWN BROKEN (found live, 2026-09-16): Snyk's v1 API is now fully removed,
not just deprecated -- /v1/org/{id} 404s with "unsupported url" against a
real account, confirmed live. authenticate() was migrated to the REST
equivalent (/rest/orgs/{id}), with the org-name lookup made best-effort
(the /rest/self check alone proves the token is live, per its own
default_org_context field) since a real token on a real account 403'd on
that specific call -- a token-scope gap, not proof of a bad connection.
locate() (line ~101) and ignore_issue()'s write path (line ~158) are NOT
yet migrated -- they still call the dead v1 API and will fail. Left
unmigrated deliberately: the only live token available to verify against
403s on every org-scoped REST call tried (both /rest/orgs/{id} and
/rest/orgs/{id}/projects), so a locate() rewrite couldn't be verified to
actually work, and ignore_issue() is a write action that shouldn't be
migrated blind without a way to test-fire it safely. Needs a token with
proper org-read scope (and org-write for ignore_issue) before finishing
this migration.

Snyk's own `issueCountsBySeverity` rollup on a project (critical/high/
medium/low counts) is the direct analog of a Datadog monitor's
overall_state or a Grafana alert rule's firing state -- one number per
project that answers "is this currently a problem" without a second API
call, so poll_state() uses it directly. Severity->ConnectorState mapping
follows the common security-team gating convention: critical or high
counts as FAILED (block-worthy), medium alone as DEGRADED (watch), only
low or clean as HEALTHY.

fetch_logs() deliberately does NOT call Snyk's per-issue listing endpoint
-- its exact request shape (POST with a filter body on the v1 API) isn't
something this file verifies against a real account, and guessing at an
endpoint's shape and shipping it unverified is worse than not having it.
Instead it returns the same severity breakdown poll_state() already has,
formatted as lines -- an honest, always-correct primitive rather than a
promise this connector can't currently keep. Revisit once live-verified
against a real Snyk org.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Mapping

from .base import Connector, ConnectorState, ResourceState

API_URL = "https://api.snyk.io"


class SnykError(RuntimeError):
    pass


class SnykConnector(Connector):
    name = "snyk"
    read_capabilities = ("project_issue_state",)
    write_capabilities = ("ignore_issue",)

    def __init__(self, credentials: Mapping[str, Any]):
        super().__init__(credentials)
        self.api_token = credentials.get("SNYK_API_TOKEN")
        self.org_id = credentials.get("SNYK_ORG_ID")

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"token {self.api_token or ''}", "Content-Type": "application/json"}

    def _request(self, method: str, path: str, body: Any = None) -> Any:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(f"{API_URL}{path}", data=data, headers=self._headers(), method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raise SnykError(f"Snyk API {exc.code}: {exc.read().decode('utf-8', errors='replace')[:300]}") from exc

    def authenticate(self) -> bool:
        if not self.api_token:
            self.auth_error = "Snyk API token is required"
            return False
        if not self.org_id:
            self.auth_error = "Snyk org ID is required"
            return False
        try:
            # Verify the token against Snyk's self endpoint -- this alone
            # proves the token is real and live, and its own response
            # includes default_org_context (the org id), so a failure past
            # this point is never "not authenticated," only "couldn't fetch
            # a friendlier org name."
            self._request("GET", "/rest/self?version=2024-10-15")
        except SnykError as exc:
            self.auth_identity = {}
            self.auth_error = str(exc)
            return False

        # Best-effort org name lookup. /v1/org/{id} is Snyk's now-fully-
        # removed v1 API (confirmed live 2026-09-16: 404 "unsupported url",
        # not a deprecation warning -- it's gone). /rest/orgs/{id} is the
        # replacement, but even with a valid token some tokens' scopes don't
        # include org read (confirmed live: 403 Forbidden on a real account
        # with a real token) -- that's a token-scope problem, not proof the
        # connection is bad, so it must not fail authenticate() outright.
        try:
            org = self._request("GET", f"/rest/orgs/{urllib.parse.quote(self.org_id)}?version=2024-10-15")
            attrs = (org.get("data") or {}).get("attributes") or {}
            name = attrs.get("name") or attrs.get("slug")
            self.auth_identity = {"org": name} if name else {"org": self.org_id}
        except SnykError:
            self.auth_identity = {"org": self.org_id}
        self.auth_error = None
        return True

    def locate(self, resource: str) -> Dict[str, Any]:
        if not self.api_token or not self.org_id:
            return {}
        try:
            resp = self._request("GET", f"/v1/org/{urllib.parse.quote(self.org_id)}/projects")
        except SnykError:
            return {}
        projects = resp.get("projects", []) if isinstance(resp, dict) else []
        for project in projects:
            if project.get("id") == resource or project.get("name") == resource:
                return {"project_id": project.get("id"), "name": project.get("name", ""), "project": project}
        return {}

    def poll_state(self, resource: str, **kwargs: Any) -> ResourceState:
        handle = self.locate(resource)
        if not handle:
            return ResourceState(resource, ConnectorState.NOT_FOUND, {})
        counts = (handle["project"].get("issueCountsBySeverity") or {})
        critical = counts.get("critical", 0)
        high = counts.get("high", 0)
        medium = counts.get("medium", 0)
        low = counts.get("low", 0)
        if critical > 0 or high > 0:
            state = ConnectorState.FAILED
        elif medium > 0:
            state = ConnectorState.DEGRADED
        else:
            state = ConnectorState.HEALTHY
        return ResourceState(
            resource, state,
            {
                "project_id": handle["project_id"], "name": handle["name"],
                "critical": critical, "high": high, "medium": medium, "low": low,
            },
        )

    def fetch_logs(self, resource: str, **kwargs: Any) -> list[str]:
        handle = self.locate(resource)
        if not handle:
            return []
        counts = (handle["project"].get("issueCountsBySeverity") or {})
        return [f"{sev}: {counts.get(sev, 0)}" for sev in ("critical", "high", "medium", "low")]

    def ignore_issue(self, project_id: str, issue_id: str, reason: str, expires_days: int = 30) -> Dict[str, Any]:
        """Ignore a specific vulnerability on a project for a bounded time.
        Write action added 2026-08-19 (PRASH_V2.md §7b), deliberately
        APPROVAL-tier at the action layer -- accepting a known security risk
        is a real judgment call, not a neutral operation, so it always
        prompts. `reasonType` is fixed to "temporary-ignore" (not
        "wont-fix"/"not-vulnerable") specifically because it's time-bounded
        by `expires_days` -- an ignore that silently became permanent would
        misrepresent what was actually approved."""
        expires = (datetime.now(timezone.utc) + timedelta(days=expires_days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        body = {
            "reason": reason,
            "reasonType": "temporary-ignore",
            "ignoredBy": {"name": "Prash"},
            "expires": expires,
        }
        return self._request(
            "POST",
            f"/v1/org/{urllib.parse.quote(self.org_id or '')}/project/{project_id}/ignore/{issue_id}",
            body=body,
        )
