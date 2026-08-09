"""Action dispatch: plan -> permission decision -> execute -> verify -> audit.

This is Track A's orchestrator. It owns the pipeline the CLI drives:

1. Resolve the action from the registry.
2. Build its Plan (dry-run safe, touches nothing).
3. Check the circuit breaker — open circuit on this resource means stop and
   escalate to a human (day 7 safety rail), never execute.
4. Ask the permission engine for a Decision (mode + tier + environment).
5. REFUSE -> record in audit, return a refused result. Never executes.
6. PROMPT -> hand the plan to the interface (CLI) to ask the user.
7. Execute, then Verify honestly. Every actual execution is recorded in the
   circuit breaker so loops trip it.
8. Append an audit entry for everything that happened.
"""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass
from typing import Dict, Optional

from .actions.contract import (
    Action,
    ActionContext,
    ActionResult,
    ActionResultStatus,
    Decision,
    Plan,
)
from .audit import AuditLog
from .circuit_breaker import CircuitBreaker
from .permissions import PermissionMode, decide


class ExecutionOutcome(enum.Enum):
    EXECUTED = "executed"
    REFUSED = "refused"
    SKIPPED = "skipped"
    NEEDS_INPUT = "needs_input"
    ERRORED = "errored"
    CIRCUIT_OPEN = "circuit_open"


@dataclass
class RunResult:
    outcome: ExecutionOutcome
    decision: Decision
    result: ActionResult
    plan: Optional[Plan] = None
    grant: bool = False
    audit_id: Optional[str] = None

    @property
    def ok(self) -> bool:
        return (
            self.outcome is ExecutionOutcome.EXECUTED
            and self.result.status is ActionResultStatus.SUCCEEDED
        )


class AskFn(abc.ABC):
    """How the dispatcher asks the user before an APPROVAL/PROMPT action."""

    @abc.abstractmethod
    def ask(self, action: Action, plan: Plan, ctx: ActionContext) -> bool:
        """Return True to proceed with an explicit per-action grant."""


class Dispatcher:
    def __init__(
        self,
        mode: PermissionMode = PermissionMode.ASK,
        audit: Optional[AuditLog] = None,
        breaker: Optional[CircuitBreaker] = None,
    ):
        self.mode = mode
        self.audit = audit or AuditLog()
        self.breaker = breaker
        self._actions: Dict[str, Action] = {}

    def register(self, action: Action) -> None:
        self._actions[action.spec.id] = action

    def register_all(self, actions) -> None:
        for a in actions:
            self.register(a)

    @property
    def available(self) -> Dict[str, Action]:
        return dict(self._actions)

    def run(
        self,
        action_id: str,
        ctx: ActionContext,
        ask: Optional[AskFn] = None,
    ) -> RunResult:
        action = self._actions.get(action_id)
        if action is None:
            raise KeyError(f"unknown action: {action_id}")

        if ctx.dry_run:
            return self._dry_run(action, ctx)

        plan = action.plan(ctx)

        if self.breaker is not None and self.breaker.is_open(ctx.target.resource):
            result = ActionResult(
                status=ActionResultStatus.SKIPPED,
                summary=(
                    f"circuit open for {ctx.target.resource}: {self.breaker.max_actions} actions in "
                    f"{self.breaker.window_seconds}s exceeded — stop and escalate to a human "
                    f"(`prash circuit reset {ctx.target.resource}` to override)"
                ),
            )
            audit_id = self._log(action, ctx, Decision.REFUSE, result, extra={"reason": "circuit_open"})
            return RunResult(ExecutionOutcome.CIRCUIT_OPEN, Decision.REFUSE, result, plan, audit_id=audit_id)

        decision = decide(
            mode=self.mode,
            risk_tier=action.spec.risk_tier,
            environment=ctx.target.environment,
            grant=ctx.grant,
        )

        if decision is Decision.REFUSE:
            result = ActionResult(
                status=ActionResultStatus.SKIPPED,
                summary=f"refused by permission engine ({action.spec.risk_tier.value} tier, mode {self.mode.value})",
            )
            audit_id = self._log(action, ctx, decision, result)
            return RunResult(ExecutionOutcome.REFUSED, decision, result, plan, audit_id=audit_id)

        grant = ctx.grant
        if decision is Decision.PROMPT:
            if ask is None:
                result = ActionResult(
                    status=ActionResultStatus.NEEDS_APPROVAL,
                    summary=f"approval required for {action_id}",
                )
                audit_id = self._log(action, ctx, decision, result)
                return RunResult(ExecutionOutcome.SKIPPED, decision, result, plan, audit_id=audit_id)
            proceed = ask.ask(action, plan, ctx)
            if not proceed:
                result = ActionResult(
                    status=ActionResultStatus.SKIPPED,
                    summary=f"declined by user: {action_id}",
                )
                audit_id = self._log(action, ctx, decision, result)
                return RunResult(ExecutionOutcome.SKIPPED, decision, result, plan, grant=False, audit_id=audit_id)
            grant = True

        try:
            result = action.execute(ctx)
        except Exception as exc:  # noqa: BLE001 - report honestly, never claim success
            result = ActionResult(
                status=ActionResultStatus.FAILED,
                summary=f"errored during execute: {exc}",
            )
            self._record_execution(ctx)
            audit_id = self._log(action, ctx, decision, result, grant=grant)
            return RunResult(ExecutionOutcome.ERRORED, decision, result, plan, grant=grant, audit_id=audit_id)

        if result.status is ActionResultStatus.NEEDS_INPUT:
            audit_id = self._log(action, ctx, decision, result, grant=grant)
            return RunResult(ExecutionOutcome.NEEDS_INPUT, decision, result, plan, grant=grant, audit_id=audit_id)

        if result.status is ActionResultStatus.SUCCEEDED:
            verification = action.verify(ctx, result)
            result.verification = verification
        self._record_execution(ctx)
        audit_id = self._log(action, ctx, decision, result, grant=grant)
        return RunResult(ExecutionOutcome.EXECUTED, decision, result, plan, grant=grant, audit_id=audit_id)

    def _dry_run(self, action: Action, ctx: ActionContext) -> RunResult:
        plan = action.dry_run(ctx)
        decision = decide(
            mode=self.mode,
            risk_tier=action.spec.risk_tier,
            environment=ctx.target.environment,
            grant=ctx.grant,
        )
        result = ActionResult(
            status=ActionResultStatus.SUCCEEDED,
            summary=f"dry-run plan prepared ({len(plan.steps)} steps)",
        )
        audit_id = self._log(action, ctx, decision, result, dry_run=True)
        return RunResult(ExecutionOutcome.EXECUTED, decision, result, plan, audit_id=audit_id)

    def _record_execution(self, ctx: ActionContext) -> None:
        if self.breaker is not None:
            self.breaker.record(ctx.target.resource)

    def _log(self, action: Action, ctx: ActionContext, decision: Decision, result: ActionResult, grant: bool = False, dry_run: bool = False, extra: Optional[Dict] = None) -> str:
        base = {"grant": grant, "dry_run": dry_run}
        if extra:
            base.update(extra)
        return self.audit.append(
            action_id=action.spec.id,
            risk_tier=action.spec.risk_tier,
            mode=self.mode,
            decision=decision,
            result=result,
            environment=ctx.target.environment,
            extra=base,
        )
