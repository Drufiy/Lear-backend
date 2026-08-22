"""Action: gitleaks-escalate (Sprint 2 Tier 3, PRASH_V2.md §7b).

Deliberately not "gitleaks-fix" -- there is nothing gitleaks itself can
mutate to fix a leaked secret (see gitleaks.py's own docstring: it has no
cloud account, and the actual fix is rotating the credential in whatever
system it belongs to, which a local scanner has no way to know). Discussed
explicitly before building (see PRASH_V2.md §9/§10, 2026-08-19): the honest
write action here is escalation, not remediation -- when a scan finds
leaks, open a real PagerDuty incident so a human rotates the credential
fast, rather than either doing nothing or pretending to fix something this
connector structurally cannot fix.

The first genuinely cross-connector action in this codebase: needs BOTH
the gitleaks connector (to run the scan) and the pagerduty connector (to
escalate what it finds) present in ctx.extra["connectors"]. Every other
action here acts through exactly one connector; this one doesn't, and
that's a deliberate, documented exception, not an accidental coupling.

SAFE tier: escalating a real problem to a human is the opposite of
suppressing one (contrast with pagerduty-resolve, APPROVAL, which
suppresses paging) -- low blast radius, and worst case it's a noisy but
harmless incident. Never includes the actual secret value in the incident
payload -- only rule id, file, line, and gitleaks' own fingerprint, same
safety property gitleaks.py's poll_state()/fetch_logs() already enforce.
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


class GitleaksEscalateAction(Action):
    spec = ActionSpec(
        id="gitleaks-escalate",
        summary="Scan for leaked secrets and open a PagerDuty incident if any are found",
        risk_tier=RiskTier.SAFE,
        reversible=False,
        capabilities=("secret_scan", "trigger_event"),
    )

    def plan(self, ctx: ActionContext) -> Plan:
        return Plan(
            action_id=self.spec.id,
            reversible=False,
            risk_tier=self.spec.risk_tier,
            steps=[
                PlanStep(description=f"Scan {ctx.target.resource} for leaked secrets", impact="read-only"),
                PlanStep(description="If any are found, open a PagerDuty incident naming the rule/file/line only -- never the secret value"),
            ],
        )

    def execute(self, ctx: ActionContext) -> ActionResult:
        gitleaks = ctx.extra.get("connectors", {}).get("gitleaks")
        pagerduty = ctx.extra.get("connectors", {}).get("pagerduty")
        if not gitleaks:
            return ActionResult(status=ActionResultStatus.FAILED, summary="Gitleaks connector is missing or not configured.")
        if not pagerduty:
            return ActionResult(status=ActionResultStatus.FAILED, summary="PagerDuty connector is missing or not configured -- needed to escalate a leak.")

        state = gitleaks.poll_state(ctx.target.resource)
        findings = state.detail.get("findings", [])
        if not findings:
            return ActionResult(status=ActionResultStatus.SKIPPED, summary=f"no leaks found in {ctx.target.resource} -- nothing to escalate")

        summary = f"gitleaks found {len(findings)} leaked secret(s) in {ctx.target.resource}"
        rule_ids = sorted({f.get("rule_id", "?") for f in findings})
        try:
            incident = pagerduty.trigger_event(
                summary=summary,
                source=ctx.target.resource,
                severity="critical",
                custom_details={"leak_count": len(findings), "rule_ids": rule_ids, "findings": findings},
            )
        except PagerDutyError as exc:
            return ActionResult(status=ActionResultStatus.FAILED, summary=f"scan found {len(findings)} leak(s) but escalation failed: {exc}")
        return ActionResult(
            status=ActionResultStatus.SUCCEEDED,
            summary=f"{summary} -- PagerDuty incident opened",
            detail={"leak_count": len(findings), "dedup_key": incident.get("dedup_key", "")},
        )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        if result.status is ActionResultStatus.SKIPPED:
            return VerificationResult(ok=True, detail="no leaks found; nothing needed escalating")
        dedup_key = result.detail.get("dedup_key", "")
        return VerificationResult(ok=bool(dedup_key), detail=f"incident dedup_key={dedup_key or 'missing'}")
