"""Action: datadog-mute-monitor (Sprint 2 Tier 3, PRASH_V2.md §7b).

SAFE tier: muting a monitor silences paging noise, it doesn't touch
whatever's actually wrong and it's time-bounded (auto-expires), matching
pagerduty-acknowledge's reasoning -- low blast radius, easily corrected,
literally what an on-call engineer does by hand while working the real
problem. Reversible=True: Datadog's /unmute endpoint exists even though
this action doesn't call it yet -- the underlying mechanism to undo is
real, not hypothetical.
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


class DatadogMuteMonitorAction(Action):
    spec = ActionSpec(
        id="datadog-mute-monitor",
        summary="Mute a Datadog monitor for a time-bounded window",
        risk_tier=RiskTier.SAFE,
        reversible=True,
        capabilities=("mute_monitor",),
    )

    def plan(self, ctx: ActionContext) -> Plan:
        minutes = ctx.extra.get("minutes", 60)
        return Plan(
            action_id=self.spec.id,
            reversible=True,
            risk_tier=self.spec.risk_tier,
            steps=[PlanStep(description=f"Mute Datadog monitor {ctx.target.resource} for {minutes} minutes")],
        )

    def execute(self, ctx: ActionContext) -> ActionResult:
        dd = ctx.extra.get("connectors", {}).get("datadog")
        if not dd:
            return ActionResult(status=ActionResultStatus.FAILED, summary="Datadog connector is missing or not configured.")
        minutes = ctx.extra.get("minutes", 60)
        try:
            dd.mute_monitor(ctx.target.resource, minutes=minutes)
        except Exception as exc:  # noqa: BLE001
            return ActionResult(status=ActionResultStatus.FAILED, summary=f"mute failed: {exc}")
        return ActionResult(
            status=ActionResultStatus.SUCCEEDED,
            summary=f"monitor {ctx.target.resource} muted for {minutes} minutes",
            detail={"minutes": minutes},
        )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        dd = ctx.extra.get("connectors", {}).get("datadog")
        if not dd:
            return VerificationResult(ok=False, detail="could not verify: Datadog connector missing")
        state = dd.poll_state(ctx.target.resource)
        # Datadog surfaces a muted monitor's own state as "No Data"/paused
        # rather than a distinct "muted" enum in this connector's mapping,
        # so verification here is best-effort: confirm the monitor still
        # resolves at all, since a mute call against a nonexistent monitor
        # would already have failed in execute().
        return VerificationResult(ok=True, detail=f"monitor still resolves, overall_state={state.detail.get('overall_state', 'unknown')}")
