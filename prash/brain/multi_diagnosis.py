"""Track D tier 2 — the multi-failure fix. See PRASH_V2.md §6/§9.

The atomic-fix model breaks on real repos: "one root cause -> one diagnosis
-> one PR" assumes N=1 independent failure, but real broken CI is usually
N independent failures across N jobs. The AgentCore case (2026-08-03, see
ROADMAP.md) had 4: backend ruff errors, a contracts drift, frontend biome
errors, a mobile parity issue -- completely unrelated causes in completely
unrelated jobs. The old pipeline either picked one job and left the rest
unfixed (silently reported as if the whole thing were resolved), or gave up
entirely with a single manual_required covering none of them.

The fix: split by failing job, diagnose each independently (they're
independent problems, not fragments of one), and report "fixed 3 of 4" as
a real partial success -- not "verified: true/false" as the only two
possible outcomes. Fixing most of a multi-failure run is real progress;
scoring it as total failure because it wasn't literally everything is
exactly the bug this closes.

Done when: an AgentCore-shaped case (N independent failures, not all
fixable) produces N-1 real fixes instead of one manual_required covering
nothing. Validated live against a synthetic case matching that shape
(PRASH_V2.md §10, 2026-08-09) -- the original AgentCore run itself isn't
re-fetchable here, this repo has no access to v1's specific historical
GitHub run.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field

from prash.brain.diagnosis_agent import diagnose_failure
from prash.brain.schemas import Diagnosis, FileChange

logger = logging.getLogger(__name__)

_SECTION_HEADER_RE = re.compile(r"(?m)^=== (.+) ===$")


def _split_by_job_sections(logs: str) -> dict[str, str]:
    """Reverse of the '=== {header} ===' concatenation log_fetcher.py's
    _parse_zip_logs() already produces -- recovers per-job chunks from the
    same blob diagnose_failure() normally consumes as one string, without
    needing log_fetcher.py (which stays CI-only/verbatim, untouched) to
    expose a second, dict-shaped return path.

    Headers are per-STEP-file (e.g. "backend/2_Run ruff.txt"), not per-job --
    multiple headers naturally share one job prefix ("backend/..."), so
    sections are grouped by the part before the first '/' when present,
    falling back to the flat "0_JobName.txt" numbered-file convention
    otherwise. Content with no headers at all returns a single "" key.
    """
    headers = _SECTION_HEADER_RE.findall(logs)
    if not headers:
        return {"": logs}

    bodies = _SECTION_HEADER_RE.split(logs)[1:]  # alternating [header, body, header, body, ...]
    sections: dict[str, str] = {}
    for i in range(0, len(bodies), 2):
        header = bodies[i]
        body = bodies[i + 1] if i + 1 < len(bodies) else ""
        job = header.split("/")[0].strip() if "/" in header else re.sub(r"^\d+_", "", header).rsplit(".txt", 1)[0].strip()
        sections.setdefault(job, "")
        sections[job] += f"\n=== {header} ===\n{body}"
    return sections


@dataclass
class MultiFailureResult:
    diagnoses: list[Diagnosis]
    job_names: list[str] = field(default_factory=list)  # parallel to diagnoses, best-effort

    @property
    def total_count(self) -> int:
        return len(self.diagnoses)

    @property
    def fixed_count(self) -> int:
        return sum(1 for d in self.diagnoses if d.files_changed)

    def combined_files_changed(self) -> list[FileChange]:
        """Union of every fixed sub-diagnosis's files, deduped by path. A
        real conflict (two independent failures editing the same file) is
        rare for genuinely INDEPENDENT failures by definition, but not
        impossible -- first diagnosis to touch a path wins, logged so it's
        visible rather than silently dropped."""
        combined: dict[str, FileChange] = {}
        for d in self.diagnoses:
            for fc in d.files_changed:
                if fc.path in combined:
                    logger.warning(f"Multi-failure fix conflict: {fc.path} touched by more than one sub-diagnosis — keeping the first")
                    continue
                combined[fc.path] = fc
        return list(combined.values())

    def summary(self) -> str:
        # Deliberately not "Fixed X of N": this class only diagnoses and
        # proposes file changes -- nothing here has opened a PR or changed
        # anything in the real repository yet. Real bug, caught live
        # (2026-08-15): the old wording said "Fixed" and every reader of
        # `prash fix --ci` reasonably believed their CI was unblocked when
        # it was exactly as broken as before. See PRASH_V2.md §9.
        return f"Diagnosed {self.fixed_count} of {self.total_count} independent failures with a proposed fix"

    def unresolved_summaries(self) -> list[str]:
        return [d.problem_summary for d in self.diagnoses if not d.files_changed]


async def diagnose_multi_failure(
    logs: str,
    repo_full_name: str,
    commit_message: str,
    workflow_name: str,
    failing_job_names: set[str] | None = None,
    model: str = "auto",
    max_concurrency: int = 3,
    **diagnose_kwargs,
) -> MultiFailureResult:
    """Split `logs` by failing job and diagnose each independently.

    Falls back to a single diagnose_failure() call (wrapped in the same
    MultiFailureResult shape, total_count=1) when there's nothing to split --
    either failing_job_names has 0-1 entries, or the log has no job section
    markers to split on at all (e.g. the non-ZIP push_handler.py path). This
    makes it a safe drop-in for every case, not just known-multi ones.

    max_concurrency defaults to 3 -- found live (2026-08-09), not guessed:
    firing every sub-diagnosis at once via bare asyncio.gather hit a real
    Kimi account rate limit ("max organization concurrency: 3") the moment
    a case had 4 independent failures. Matches evals/run_eval.py's own
    default concurrency for the same reason.
    """
    sections = _split_by_job_sections(logs)

    if failing_job_names:
        sections = {job: body for job, body in sections.items() if job in failing_job_names} or sections

    if len(sections) <= 1:
        diagnosis = await diagnose_failure(
            logs=logs, repo_full_name=repo_full_name, commit_message=commit_message,
            workflow_name=workflow_name, model=model, **diagnose_kwargs,
        )
        return MultiFailureResult(diagnoses=[diagnosis], job_names=list(sections.keys()) or [""])

    semaphore = asyncio.Semaphore(max_concurrency)

    async def _diagnose_one(job: str, body: str) -> tuple[str, Diagnosis | None]:
        try:
            async with semaphore:
                # diagnose_failure() computes its own internal call_type from
                # iteration/repeated_failure/force_fix -- it's not a passthrough
                # kwarg. run_id IS a real param and shows up in the (now-local)
                # agent-call logging, which is enough to tell sub-calls apart.
                d = await diagnose_failure(
                    logs=body, repo_full_name=repo_full_name, commit_message=commit_message,
                    workflow_name=workflow_name, model=model,
                    run_id=f"multi_failure_{job}", **diagnose_kwargs,
                )
            return job, d
        except Exception as e:  # noqa: BLE001 — one job's failure must not sink the other independent diagnoses
            logger.warning(f"Multi-failure sub-diagnosis for job {job!r} failed: {e}")
            return job, None

    results = await asyncio.gather(*[_diagnose_one(job, body) for job, body in sections.items()])

    job_names = [job for job, d in results if d is not None]
    diagnoses = [d for _job, d in results if d is not None]

    logger.info(f"Multi-failure diagnosis for {repo_full_name}: {len(diagnoses)}/{len(sections)} jobs produced a diagnosis")
    return MultiFailureResult(diagnoses=diagnoses, job_names=job_names)
