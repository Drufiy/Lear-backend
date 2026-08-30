import subprocess
from pathlib import Path

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

class TerraformApplyAction(Action):
    # Dynamic risk tier: read TERRAFORM_APPLY_RISK_TIER from config or default to APPROVAL
    spec = ActionSpec(
        id="terraform-apply",
        summary="Run terraform apply -auto-approve to resolve drift or apply new config.",
        risk_tier=RiskTier.APPROVAL,
        reversible=False,
        capabilities=("apply",),
        approval_hint="This will mutate infrastructure state.",
    )

    def plan(self, ctx: ActionContext) -> Plan:
        # Check dynamic strictness from credentials/config
        strictness = str(ctx.credentials.get("TERRAFORM_APPLY_RISK_TIER", "")).lower()
        dynamic_tier = self.spec.risk_tier
        if strictness == "safe":
            dynamic_tier = RiskTier.SAFE
        elif strictness == "never":
            dynamic_tier = RiskTier.NEVER
            
        return Plan(
            action_id=self.spec.id,
            steps=[PlanStep(description=f"Run `terraform apply -auto-approve` in {ctx.target.resource}")],
            reversible=self.spec.reversible,
            risk_tier=dynamic_tier,
        )

    def execute(self, ctx: ActionContext) -> ActionResult:
        target_dir = Path(ctx.target.resource).resolve()
        if not target_dir.exists() or not target_dir.is_dir():
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary=f"Target directory {target_dir} does not exist.",
            )
        
        if str(ctx.credentials.get("TERRAFORM_USE_CLOUD", "false")).lower() == "true":
             return ActionResult(
                status=ActionResultStatus.FAILED,
                summary="Cloud execution of terraform apply is not yet supported in this version.",
            )

        try:
            result = subprocess.run(
                ["terraform", "apply", "-auto-approve", "-no-color"],
                cwd=target_dir,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return ActionResult(
                    status=ActionResultStatus.FAILED,
                    summary="terraform apply failed",
                    detail={"error": result.stderr or result.stdout},
                )
            return ActionResult(
                status=ActionResultStatus.SUCCEEDED,
                summary="Successfully applied terraform configuration.",
            )
        except Exception as e:
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary="Failed to execute terraform apply.",
                detail={"error": str(e)},
            )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        if result.status != ActionResultStatus.SUCCEEDED:
            return VerificationResult(ok=False, detail="Action did not succeed.")
        
        target_dir = Path(ctx.target.resource).resolve()
        
        # Verify drift is gone
        try:
            plan_res = subprocess.run(
                ["terraform", "plan", "-detailed-exitcode", "-no-color"],
                cwd=target_dir,
                capture_output=True,
                text=True,
            )
            if plan_res.returncode == 0:
                return VerificationResult(ok=True, detail="No drift detected after apply.")
            else:
                return VerificationResult(ok=False, detail="Drift or error still present after apply.")
        except Exception as e:
            return VerificationResult(ok=False, detail=f"Could not verify state: {e}")
