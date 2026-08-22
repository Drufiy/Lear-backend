"""Action: grafana-silence-alert (Sprint 2 Tier 3, PRASH_V2.md §7b).

Same reasoning and shape as datadog-mute-monitor: SAFE tier (silences
paging noise, doesn't touch the underlying problem, time-bounded).
reversible=True -- Grafana's Alertmanager API supports deleting a silence
before its endsAt (DELETE /api/alertmanager/grafana/api/v2/silence/{id}),
a real mechanism even though this action doesn't call it yet.
"""

from __future__ import annotations

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


class GrafanaSilenceAlertAction(Action):
    spec = ActionSpec(
        id="grafana-silence-alert",
        summary="Silence a Grafana alert rule for a time-bounded window",
        risk_tier=RiskTier.SAFE,
        reversible=True,
        capabilities=("silence_alert",),
    )

    def plan(self, ctx: ActionContext) -> Plan:
        minutes = ctx.extra.get("minutes", 60)
        return Plan(
            action_id=self.spec.id,
            reversible=True,
            risk_tier=self.spec.risk_tier,
            steps=[PlanStep(description=f"Silence Grafana alert rule {ctx.target.resource} for {minutes} minutes")],
        )

    def execute(self, ctx: ActionContext) -> ActionResult:
        gf = ctx.extra.get("connectors", {}).get("grafana")
        if not gf:
            return ActionResult(status=ActionResultStatus.FAILED, summary="Grafana connector is missing or not configured.")
        minutes = ctx.extra.get("minutes", 60)
        try:
            silence = gf.silence_alert(ctx.target.resource, minutes=minutes)
        except Exception as exc:  # noqa: BLE001
            return ActionResult(status=ActionResultStatus.FAILED, summary=f"silence failed: {exc}")
        return ActionResult(
            status=ActionResultStatus.SUCCEEDED,
            summary=f"alert rule {ctx.target.resource} silenced for {minutes} minutes",
            detail={"minutes": minutes, "silence_id": silence.get("silenceID", "")},
        )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        silence_id = result.detail.get("silence_id", "")
        return VerificationResult(ok=bool(silence_id), detail=f"silence id={silence_id or 'missing'}")
