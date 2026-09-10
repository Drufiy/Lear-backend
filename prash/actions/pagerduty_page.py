"""Action: pagerduty-page (connector rewrite, Phase 3 rollout — PagerDuty).

APPROVAL tier, hardcoded: paging the on-call engineer is the most
disruptive thing Prash can do -- a real human gets woken up -- and it is
irreversible in every sense that matters: the Events API has no un-page,
the incident can't be un-triggered (the only path "back" is someone
manually resolving it), and the phone already buzzed. Outbound +
irreversible + wakes a human is exactly the spec's default for APPROVAL
(same reasoning as pagerduty-resolve); nothing about this action is
internal, quiet, or undoable, so SAFE was never on the table.

The mechanism is the Events API v2 (PAGERDUTY_ROUTING_KEY), not the REST
API -- triggering a NEW incident and updating an EXISTING one are
different PagerDuty products with different auth models (see the
connector's module docstring). verify() closes the loop honestly: the
Events API response carries no incident id, so it looks up the incident
by dedup key (server-side incident_key filter, alert_key fallback) with
a bounded retry for PagerDuty's intake -> listable propagation -- and
reports "not visible yet" rather than success if it never shows up.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone

from .contract import (
    Action,
    ActionContext,
    ActionResult,
    ActionResultStatus,
    ActionSpec,
    Plan,
    PlanStep,
    RiskTier,
    VerificationResult,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value) -> "datetime | None":
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


class PagerdutyPageAction(Action):
    spec = ActionSpec(
        id="pagerduty-page",
        summary="Page the on-call engineer with a new PagerDuty incident",
        risk_tier=RiskTier.APPROVAL,
        reversible=False,
        capabilities=("page_oncall",),
        approval_hint="This will wake up the on-call engineer — a real human gets paged, and it cannot be undone",
    )

    def plan(self, ctx: ActionContext) -> Plan:
        summary = ctx.extra.get("summary") or f"Prash page: {ctx.target.resource}"
        severity = ctx.extra.get("severity", "critical")
        return Plan(
            action_id=self.spec.id,
            reversible=False,
            risk_tier=self.spec.risk_tier,
            steps=[
                PlanStep(
                    description=f"Trigger PagerDuty incident '{summary}' (severity {severity}) via the Events API routing key",
                    impact="Pages the on-call engineer now; the incident cannot be un-triggered and must be resolved by hand",
                )
            ],
        )

    def execute(self, ctx: ActionContext) -> ActionResult:
        pd = ctx.extra.get("connectors", {}).get("pagerduty")
        if not pd:
            return ActionResult(status=ActionResultStatus.FAILED, summary="PagerDuty connector is missing or not configured.")
        summary = ctx.extra.get("summary") or f"Prash page: {ctx.target.resource}"
        severity = ctx.extra.get("severity", "critical")
        source = ctx.extra.get("source", "prash")
        dedup_key = ctx.extra.get("dedup_key") or f"prash-page-{uuid.uuid4().hex[:12]}"
        posted_at = _utcnow()
        try:
            resp = pd.page_oncall(
                summary, source, severity=severity, dedup_key=dedup_key,
                custom_details=ctx.extra.get("custom_details"),
            )
        except Exception as exc:  # noqa: BLE001 — report honestly, never fake a result
            return ActionResult(status=ActionResultStatus.FAILED, summary=f"page failed: {exc}")
        status = resp.get("status", "") if isinstance(resp, dict) else ""
        if status != "success":
            return ActionResult(status=ActionResultStatus.FAILED, summary=f"page not accepted by PagerDuty: {resp}")
        return ActionResult(
            status=ActionResultStatus.SUCCEEDED,
            summary=f"on-call paged: '{summary}' (dedup key {dedup_key})",
            detail={"dedup_key": dedup_key, "severity": severity, "summary": summary,
                    "posted_at": posted_at.isoformat()},
        )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        pd = ctx.extra.get("connectors", {}).get("pagerduty")
        if not pd:
            return VerificationResult(ok=False, detail="could not verify: PagerDuty connector missing")
        dedup_key = result.detail.get("dedup_key")
        if not dedup_key:
            return VerificationResult(ok=False, detail="could not verify: no dedup key was recorded")
        posted_at = _parse_ts(result.detail.get("posted_at")) or _utcnow() - timedelta(minutes=30)
        # Found live (2026-09-09): a just-triggered Events v2 incident is not
        # listable via REST for a few seconds (intake -> incident propagation),
        # so a single immediate lookup reports "not verified" for a page that
        # is real. Same bounded retry as datadog_alert.verify: confirm as soon
        # as reality catches up; if it never does, report exactly that instead
        # of claiming a verified success.
        last = "could not verify: no lookup was attempted"
        for attempt in range(3):
            try:
                incident = pd.find_incident_by_incident_key(dedup_key, since=posted_at)
            except Exception as exc:  # noqa: BLE001 — verification must report, never crash
                last = f"could not verify: {exc}"
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
                continue
            if incident is not None:
                return VerificationResult(
                    ok=True,
                    detail=f"incident {incident.get('id')} exists ({incident.get('status')}), matched by dedup key",
                )
            # The Events API accepted the trigger (execute() would have
            # failed otherwise), but the incident isn't visible in the REST
            # window yet -- report that honestly instead of claiming success.
            last = f"no incident with incident_key {dedup_key} in the recent window (page may still be propagating)"
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
        return VerificationResult(ok=False, detail=last)
