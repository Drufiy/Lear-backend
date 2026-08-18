"""GitLab pipeline log fetching (Sprint 2 Tier 2, PRASH_V2.md §7b).

Same job as log_fetcher.py's fetch_workflow_logs, different shape on the
wire: GitHub Actions hands back one ZIP of per-step .txt files for a whole
run; GitLab has no equivalent bundle endpoint, so this lists the pipeline's
jobs and fetches each job's plain-text trace individually, then reuses
log_fetcher's error-relevant preprocessing (_preprocess_logs) on the
concatenated result -- that logic is already provider-agnostic text
processing, not GitHub-specific, so there is nothing to duplicate here.
"""

from __future__ import annotations

import asyncio
import logging

from ..connectors.gitlab import GitLabConnector, GitLabError
from .log_fetcher import MAX_LOG_CHARS, LogFetchError, LogsNotAvailableError, _preprocess_logs

logger = logging.getLogger(__name__)


async def fetch_pipeline_logs(pipeline_id: int, project: str, access_token: str) -> str:
    """Fetch and concatenate every job's trace for a GitLab pipeline,
    failing jobs sorted last (same failure-aware ordering rationale as
    GitHub's M2 fix in log_fetcher.py: the hard length cut below keeps the
    tail, so a small failing job must not get pushed out by a large passing
    one)."""
    gl = GitLabConnector({"GITLAB_TOKEN": access_token})

    def _fetch_sync() -> str:
        try:
            jobs = gl.pipeline_jobs(project, pipeline_id)
        except GitLabError as exc:
            if "404" in str(exc):
                raise LogsNotAvailableError(f"Pipeline {pipeline_id} not found for {project}") from exc
            raise LogFetchError(str(exc)) from exc

        if not jobs:
            raise LogsNotAvailableError(f"Pipeline {pipeline_id} has no jobs")

        jobs_sorted = sorted(jobs, key=lambda j: j.get("status") == "failed")

        parts = []
        for job in jobs_sorted:
            name = job.get("name", f"job-{job.get('id')}")
            try:
                trace = gl.job_trace(project, job["id"])
            except GitLabError as exc:
                logger.warning(f"Could not fetch trace for job {name} ({job.get('id')}): {exc}")
                continue
            parts.append(f"\n\n=== {name} ({job.get('status')}) ===\n{trace}")

        if not parts:
            return "No logs available for this pipeline."
        return "".join(parts)

    concatenated = await asyncio.to_thread(_fetch_sync)

    # include_raw_tail=False: this feeds diagnose_multi_failure, which splits
    # on === headers per independent failure -- see _preprocess_logs docstring.
    concatenated = _preprocess_logs(concatenated, include_raw_tail=False)
    if len(concatenated) > MAX_LOG_CHARS:
        concatenated = "... [earlier logs truncated] ...\n" + concatenated[-MAX_LOG_CHARS:]
    return concatenated
