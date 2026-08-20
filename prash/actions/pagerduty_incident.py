"""Actions: pagerduty-acknowledge, pagerduty-resolve (Sprint 2 Tier 3,
PRASH_V2.md §7b).

Two distinct action ids sharing one base, same shape as edit-configmap/
edit-secret (prash/actions/edit_config.py) -- the plan/execute/verify
pattern is identical, only which status transition each requests differs.

Risk tiers deliberately differ from each other, not copy-pasted:
- **acknowledge is SAFE.** Low blast radius, and it's literally the first
  thing an on-call engineer does by hand -- claiming "someone is looking at
  this" is a low-stakes, easily-corrected statement. Matches restart-pod's
  SAFE reasoning: routine, low-risk.
- **resolve is APPROVAL.** Declaring an incident resolved is a claim of
  fact that, if wrong, can suppress a real ongoing outage -- nobody gets
  paged again unless the underlying monitor independently re-triggers.
  Always needs an explicit human yes, matching rollback/scale/config-edit's
  existing reasoning in RiskTier's own docstring.

Neither is marked reversible: PagerDuty's stable v2 API has no supported
transition back from acknowledged->triggered or resolved->anything -- the
only way "back" is a fresh trigger from the monitoring source itself. Not
claiming a reversibility guarantee this connector hasn't verified.
"""

from __future__ import annotations

from ..connectors.pagerduty import PagerDutyError
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


class _PagerDutyIncidentActionBase(Action):
    _status = ""
    _verb = ""

    def plan(self, ctx: ActionContext) -> Plan:
        return Plan(
            action_id=self.spec.id,
            reversible=self.spec.reversible,
            risk_tier=self.spec.risk_tier,
            steps=[PlanStep(description=f"{self._verb} PagerDuty incident {ctx.target.resource}")],
        )

    def _call(self, pd, incident_id: str) -> dict:
        raise NotImplementedError

    def execute(self, ctx: ActionContext) -> ActionResult:
        pd = ctx.extra.get("connectors", {}).get("pagerduty")
        if not pd:
            return ActionResult(status=ActionResultStatus.FAILED, summary="PagerDuty connector is missing or not configured.")
        try:
            incident = self._call(pd, ctx.target.resource)
        except PagerDutyError as exc:
            return ActionResult(status=ActionResultStatus.FAILED, summary=f"{self._verb.lower()} failed: {exc}")
        except Exception as exc:  # noqa: BLE001 — report honestly, never fake a result
            return ActionResult(status=ActionResultStatus.FAILED, summary=f"{self._verb.lower()} failed: {exc}")
        return ActionResult(
            status=ActionResultStatus.SUCCEEDED,
            summary=f"incident {ctx.target.resource} {self._status}",
            detail={"incident_id": ctx.target.resource, "status": incident.get("status", self._status)},
        )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        actual_status = result.detail.get("status", "")
        return VerificationResult(ok=actual_status == self._status, detail=f"incident status now={actual_status or 'unknown'}")


class PagerdutyAcknowledgeAction(_PagerDutyIncidentActionBase):
    _status = "acknowledged"
    _verb = "Acknowledge"
    spec = ActionSpec(
        id="pagerduty-acknowledge",
        summary="Acknowledge a PagerDuty incident",
        risk_tier=RiskTier.SAFE,
        reversible=False,
        capabilities=("acknowledge_incident",),
    )

    def _call(self, pd, incident_id: str) -> dict:
        return pd.acknowledge_incident(incident_id)


class PagerdutyResolveAction(_PagerDutyIncidentActionBase):
    _status = "resolved"
    _verb = "Resolve"
    spec = ActionSpec(
        id="pagerduty-resolve",
        summary="Resolve a PagerDuty incident",
        risk_tier=RiskTier.APPROVAL,
        reversible=False,
        capabilities=("resolve_incident",),
        approval_hint="Always prompts, even in bypass mode — a false resolve can suppress a real ongoing outage.",
    )

    def _call(self, pd, incident_id: str) -> dict:
        return pd.resolve_incident(incident_id)
