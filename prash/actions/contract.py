"""The Lear action contract.

This is the Days 1-2 shared foundation. Every action in the system must
implement this contract, and every permission engine decision is made against
it. Nothing about the contract is web-stack-specific; it ports to any agent
body.

The contract answers five questions for every action:

1. What does it do?           -> Action.summary / Action.plan
2. What is its risk tier?     -> Action.spec.risk_tier
3. Is it reversible?          -> Action.spec.reversible
4. How do you dry-run it?     -> Action.dry_run (never touches infrastructure)
5. How do you verify it?      -> Action.verify (checks reality afterward)
"""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class RiskTier(enum.Enum):
    """Risk classification used by the permission engine.

    SAFE:      can run without asking in permissive modes (re-run a job,
               restart a crash-looping pod, open a fix PR, request a secret).
    APPROVAL:  always requires an explicit per-action grant, even in bypass
               mode (rollback, scale, config change).
    NEVER:     never executed in v1, unconditionally refused (migrations,
               data destruction, production without an explicit per-action
               grant).
    """

    SAFE = "safe"
    APPROVAL = "approval"
    NEVER = "never"


class Decision(enum.Enum):
    """The permission engine's verdict for a requested action."""

    ALLOW = "allow"
    PROMPT = "prompt"
    REFUSE = "refuse"


class ActionResultStatus(enum.Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NEEDS_APPROVAL = "needs_approval"
    NEEDS_INPUT = "needs_input"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ActionSpec:
    """Static description of an action. Decided once, in code, never at runtime."""

    id: str
    summary: str
    risk_tier: RiskTier
    reversible: bool
    capabilities: tuple[str, ...] = ()
    approval_hint: str = ""

    @property
    def always_asks(self) -> bool:
        return self.risk_tier in (RiskTier.APPROVAL, RiskTier.NEVER)


@dataclass
class Target:
    """What the action is acting on, and where.

    ``environment`` drives environment-scoped permission mode (staging is
    auto, production always prompts).
    """

    resource: str
    environment: str = "staging"
    labels: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionContext:
    """Everything an action needs to plan, act, and verify."""

    target: Target
    credentials: Dict[str, Any]
    secrets: Dict[str, str] = field(default_factory=dict)
    dry_run: bool = False
    grant: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlanStep:
    description: str
    impact: str = ""
    dry_run_only: bool = False


@dataclass
class Plan:
    """What the action intends to do. Shown to the user before any approval."""

    action_id: str
    steps: list[PlanStep]
    reversible: bool
    risk_tier: RiskTier

    def describe(self) -> str:
        return "\n".join(f"- {s.description}" + (f" [{s.impact}]" if s.impact else "") for s in self.steps)


@dataclass
class VerificationResult:
    ok: bool
    detail: str = ""


@dataclass
class ActionResult:
    status: ActionResultStatus
    summary: str
    verification: Optional[VerificationResult] = None
    detail: Dict[str, Any] = field(default_factory=dict)


class Action(abc.ABC):
    """Base class every Prash action implements."""

    spec: ActionSpec

    @abc.abstractmethod
    def plan(self, ctx: ActionContext) -> Plan:
        """Return the intended steps. Must not touch infrastructure."""

    @abc.abstractmethod
    def execute(self, ctx: ActionContext) -> ActionResult:
        """Perform the action against the target using ctx.credentials."""

    @abc.abstractmethod
    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        """Check whether the action actually worked. Reports honestly if not."""

    def dry_run(self, ctx: ActionContext) -> Plan:
        """The dry-run contract: plan without executing a single write."""
        ctx = ActionContext(**{**vars(ctx), "dry_run": True})
        return self.plan(ctx)

    def ask_for_secret(self, name: str, hint: str = "") -> str:
        """Raise a structured request for a missing secret value.

        Track C #1 depends on this: Prash can *ask* for the value rather than
        dead-ending on ``needs_secret``.
        """
        raise MissingSecretError(name=name, hint=hint)


class MissingSecretError(Exception):
    """Raised when an action needs a secret the user has not supplied."""

    def __init__(self, name: str, hint: str = ""):
        self.name = name
        self.hint = hint
        super().__init__(f"missing secret: {name}")
