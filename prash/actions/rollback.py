"""Action: rollback (Track C #3).

Approval tier: always requires an explicit per-action grant, even in bypass
mode. Blocked on release-tracking existing (Prash must know what "last known
good" means before "undo" means anything). Until a ReleaseTracker is supplied
via ctx, execute reports honestly that tracking is not wired.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any, Dict, Optional

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


@dataclass
class Release:
    revision: str
    tag: str
    timestamp: str
    healthy: bool


class ReleaseTracker(abc.ABC):
    """What Prash needs before rollback can mean anything."""

    @abc.abstractmethod
    def last_known_good(self, resource: str) -> Optional[Release]:
        """The last release of ``resource`` verified healthy."""


class RollbackAction(Action):
    spec = ActionSpec(
        id="rollback",
        summary="Roll back a deployment to the last known good revision",
        risk_tier=RiskTier.APPROVAL,
        reversible=True,
        capabilities=("deploy_state", "rollback"),
        approval_hint="Production rollbacks always prompt, even in bypass mode.",
    )

    def plan(self, ctx: ActionContext) -> Plan:
        tracker: Optional[ReleaseTracker] = ctx.extra.get("release_tracker")
        if tracker is None:
            return Plan(
                action_id=self.spec.id,
                reversible=True,
                risk_tier=self.spec.risk_tier,
                steps=[
                    PlanStep(
                        description=f"Roll back {ctx.target.resource} to last known good",
                        impact="requires release-tracking (not wired yet)",
                    )
                ],
            )
        target = tracker.last_known_good(ctx.target.resource)
        target_s = target.revision if target else "unknown (none recorded)"
        return Plan(
            action_id=self.spec.id,
            reversible=True,
            risk_tier=self.spec.risk_tier,
            steps=[
                PlanStep(description=f"Identify last known good revision for {ctx.target.resource}", impact="read-only"),
                PlanStep(description=f"Set {ctx.target.resource} to revision {target_s}"),
                PlanStep(description="Confirm rollout completes and health checks pass"),
            ],
        )

    def execute(self, ctx: ActionContext) -> ActionResult:
        tracker: Optional[ReleaseTracker] = ctx.extra.get("release_tracker")
        driver: Any = ctx.extra.get("deploy_driver")
        if tracker is None or driver is None:
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary="release-tracking not wired yet (Track C #3 dependency): nothing rolled back",
            )
        target = tracker.last_known_good(ctx.target.resource)
        if target is None:
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary="no last-known-good revision recorded for this resource",
            )
        driver.rollback(ctx.target.resource, target.revision)
        return ActionResult(
            status=ActionResultStatus.SUCCEEDED,
            summary=f"rolled back {ctx.target.resource} to {target.revision}",
            detail={"revision": target.revision},
        )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        driver: Any = ctx.extra.get("deploy_driver")
        if driver is None:
            return VerificationResult(ok=False, detail="no deploy driver to verify against")
        healthy = driver.rollout_healthy(ctx.target.resource)
        return VerificationResult(ok=healthy, detail=f"rollout healthy={healthy}")
