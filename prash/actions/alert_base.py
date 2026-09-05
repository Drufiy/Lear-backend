"""Base Action for sending alerts.

This establishes the base contract for alerting capabilities across providers.
By default, sending an outbound alert modifies state and is not cleanly reversible,
so it defaults to RiskTier.APPROVAL.
"""

from __future__ import annotations

from .contract import Action, ActionSpec, RiskTier


class AlertAction(Action):
    spec = ActionSpec(
        id="alert-base",
        summary="Base action for sending outbound alerts",
        risk_tier=RiskTier.APPROVAL,
        reversible=False,
        capabilities=("alert",),
    )
