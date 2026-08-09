"""Permission engine: the decision rule for whether an action may proceed.

Mirrors Claude Code's model:

    read-only            -> investigate only; every write is refused
    ask                  -> prompt before every action (default)
    auto-safe            -> safe tier proceeds, approval tier prompts
    environment-scoped   -> safe tier auto on staging, always prompts on
                            production
    bypass               -> safe tier auto (CI/automation); approval tier
                            STILL prompts; never tier refused unconditionally

Invariants enforced here:
    - NEVER tier is always REFUSE, regardless of mode or grant.
    - APPROVAL tier always requires an explicit per-action grant. In bypass
      mode it still prompts (never silently proceeds).
"""

from __future__ import annotations

import enum

from .actions.contract import Decision, RiskTier


class PermissionMode(enum.Enum):
    READ_ONLY = "read-only"
    ASK = "ask"
    AUTO_SAFE = "auto-safe"
    ENVIRONMENT_SCOPED = "environment-scoped"
    BYPASS = "bypass"


PRODUCTION = "production"


def decide(
    mode: PermissionMode,
    risk_tier: RiskTier,
    environment: str = "staging",
    grant: bool = False,
) -> Decision:
    """Return ALLOW / PROMPT / REFUSE for a requested action.

    ``grant`` is the explicit per-action grant. It is only meaningful for the
    APPROVAL tier (a user saying "yes, do this one thing"). It can never
    override the NEVER tier.
    """
    if risk_tier is RiskTier.NEVER:
        return Decision.REFUSE

    if mode is PermissionMode.READ_ONLY:
        return Decision.REFUSE

    if risk_tier is RiskTier.SAFE:
        if mode in (PermissionMode.AUTO_SAFE, PermissionMode.BYPASS):
            return Decision.ALLOW
        if mode is PermissionMode.ENVIRONMENT_SCOPED:
            return Decision.ALLOW if environment != PRODUCTION else Decision.PROMPT
        return Decision.PROMPT

    # APPROVAL tier: always prompt unless an explicit per-action grant exists.
    # Mode can never auto-approve this tier.
    return Decision.ALLOW if grant else Decision.PROMPT
