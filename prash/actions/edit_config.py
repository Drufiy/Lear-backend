"""Actions: edit-configmap, edit-secret (Track C, sprint-2 Kubernetes Depth,
PRASH_V2.md §7b).

Approval tier: RiskTier's own docstring already names "config change" as an
APPROVAL-tier example alongside rollback and scale -- same reasoning, a bad
config edit can take a running service down as surely as either.

Wired to Track B's Kubernetes connector (prash/connectors/kubernetes.py,
owned by Aradhya) -- same split as restart-pod/rollback/scale: the
connector does the single clear write (a merge patch, only the given keys
change), this action owns planning, permission gating, and verification.

Secret handling is deliberately more conservative than ConfigMap's: Prash's
whole security posture is "your credentials never leave your machine" (§4),
so EditSecretAction never reads, holds, or prints a Secret's decoded value
-- not in the plan, not in the summary, not in verify(). It only ever
confirms which KEYS exist after the write, matching what
get_secret_keys() returns. The value being written is still visible in
argv/ctx.extra for this process's own lifetime (unavoidable -- the user has
to supply it somehow), but nothing here echoes it back out.
"""

from __future__ import annotations

from ..connectors.kubernetes import (
    get_configmap,
    get_secret_keys,
    update_configmap,
    update_secret,
)
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


class _EditConfigResourceBase(Action):
    """Shared shape for edit-configmap and edit-secret. Subclasses differ in
    which connector functions they call and how they describe themselves --
    the actual write/verify pattern is identical."""

    _kind = "resource"

    def _split(self, ctx: ActionContext) -> tuple[str, str]:
        namespace, _, name = ctx.target.resource.partition("/")
        return (namespace or "default", name)

    def _data(self, ctx: ActionContext) -> dict[str, str]:
        return ctx.extra.get("config_data") or {}

    def plan(self, ctx: ActionContext) -> Plan:
        namespace, name = self._split(ctx)
        data = self._data(ctx)
        keys = ", ".join(sorted(data)) if data else "(no keys given)"
        return Plan(
            action_id=self.spec.id,
            reversible=True,
            risk_tier=self.spec.risk_tier,
            steps=[
                PlanStep(description=f"Read current {self._kind} {name} in {namespace}", impact="read-only"),
                PlanStep(description=f"Merge-patch keys [{keys}] into {name} — every other key is untouched"),
                PlanStep(description=f"Confirm the write took effect on {name}"),
            ],
        )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        raise NotImplementedError


class EditConfigMapAction(_EditConfigResourceBase):
    _kind = "ConfigMap"
    spec = ActionSpec(
        id="edit-configmap",
        summary="Merge-patch keys into an existing ConfigMap",
        risk_tier=RiskTier.APPROVAL,
        reversible=True,
        capabilities=("get_configmap", "update_configmap"),
        approval_hint="Always prompts, even in bypass mode -- a bad config value can take a running service down as surely as a bad rollback.",
    )

    def execute(self, ctx: ActionContext) -> ActionResult:
        namespace, name = self._split(ctx)
        data = self._data(ctx)
        if not data:
            return ActionResult(status=ActionResultStatus.FAILED, summary="no --set KEY=VALUE pairs given")
        try:
            ok = update_configmap(namespace, name, data)
        except Exception as exc:  # noqa: BLE001
            return ActionResult(status=ActionResultStatus.FAILED, summary=f"edit-configmap failed: {exc}")
        if not ok:
            return ActionResult(status=ActionResultStatus.FAILED, summary=f"configmap {namespace}/{name} not found")
        return ActionResult(
            status=ActionResultStatus.SUCCEEDED,
            summary=f"{namespace}/{name} updated: {', '.join(sorted(data))}",
            detail={"namespace": namespace, "name": name, "keys": ",".join(sorted(data))},
        )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        namespace, name = self._split(ctx)
        expected = self._data(ctx)
        try:
            current = get_configmap(namespace, name)
        except Exception as exc:  # noqa: BLE001
            return VerificationResult(ok=False, detail=f"could not verify: {exc}")
        if current is None:
            return VerificationResult(ok=False, detail=f"configmap {namespace}/{name} not found after edit")
        ok = all(current.get(k) == v for k, v in expected.items())
        return VerificationResult(ok=ok, detail=f"keys now={sorted(current)}")


class EditSecretAction(_EditConfigResourceBase):
    _kind = "Secret"
    spec = ActionSpec(
        id="edit-secret",
        summary="Merge-patch keys into an existing Secret (values never logged or printed)",
        risk_tier=RiskTier.APPROVAL,
        reversible=True,
        capabilities=("get_secret_keys", "update_secret"),
        approval_hint="Always prompts, even in bypass mode. Values are never echoed to the console or audit log — only key names are.",
    )

    def execute(self, ctx: ActionContext) -> ActionResult:
        namespace, name = self._split(ctx)
        data = self._data(ctx)
        if not data:
            return ActionResult(status=ActionResultStatus.FAILED, summary="no --set KEY=VALUE pairs given")
        try:
            ok = update_secret(namespace, name, data)
        except Exception as exc:  # noqa: BLE001
            return ActionResult(status=ActionResultStatus.FAILED, summary=f"edit-secret failed: {exc}")
        if not ok:
            return ActionResult(status=ActionResultStatus.FAILED, summary=f"secret {namespace}/{name} not found")
        # Deliberately never include the values here -- only which keys changed.
        return ActionResult(
            status=ActionResultStatus.SUCCEEDED,
            summary=f"{namespace}/{name} updated: {', '.join(sorted(data))} (values not shown)",
            detail={"namespace": namespace, "name": name, "keys": ",".join(sorted(data))},
        )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        namespace, name = self._split(ctx)
        expected_keys = set(self._data(ctx))
        try:
            current_keys = get_secret_keys(namespace, name)
        except Exception as exc:  # noqa: BLE001
            return VerificationResult(ok=False, detail=f"could not verify: {exc}")
        if current_keys is None:
            return VerificationResult(ok=False, detail=f"secret {namespace}/{name} not found after edit")
        ok = expected_keys.issubset(set(current_keys))
        return VerificationResult(ok=ok, detail=f"keys now={current_keys}")
