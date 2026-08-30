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

class TerraformInitAction(Action):
    spec = ActionSpec(
        id="terraform-init",
        summary="Run terraform init to download modules and providers.",
        risk_tier=RiskTier.SAFE,
        reversible=True,
        capabilities=("init",),
    )

    def plan(self, ctx: ActionContext) -> Plan:
        return Plan(
            action_id=self.spec.id,
            steps=[PlanStep(description=f"Run `terraform init` in {ctx.target.resource}")],
            reversible=self.spec.reversible,
            risk_tier=self.spec.risk_tier,
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
                summary="Cloud execution of terraform init is not yet supported in this version.",
            )

        try:
            result = subprocess.run(
                ["terraform", "init", "-no-color"],
                cwd=target_dir,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return ActionResult(
                    status=ActionResultStatus.FAILED,
                    summary="terraform init failed",
                    detail={"error": result.stderr or result.stdout},
                )
            return ActionResult(
                status=ActionResultStatus.SUCCEEDED,
                summary="Successfully initialized terraform workspace.",
            )
        except Exception as e:
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary="Failed to execute terraform init.",
                detail={"error": str(e)},
            )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        if result.status != ActionResultStatus.SUCCEEDED:
            return VerificationResult(ok=False, detail="Action did not succeed.")
        
        target_dir = Path(ctx.target.resource).resolve()
        if (target_dir / ".terraform").exists():
            return VerificationResult(ok=True, detail=".terraform directory found.")
        return VerificationResult(ok=False, detail=".terraform directory missing.")
