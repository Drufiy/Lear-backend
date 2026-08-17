"""Action: execute-aws (Track C).

Approval tier: running arbitrary commands on an EC2 instance modifies state.
"""

from __future__ import annotations

from rich.prompt import Prompt

from ..connectors.aws import SSMFailedNeedsSSH
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


class ExecuteAwsAction(Action):
    spec = ActionSpec(
        id="execute-aws",
        summary="Execute a shell command on an AWS EC2 instance",
        risk_tier=RiskTier.APPROVAL,
        reversible=False,
        capabilities=("execute",),
    )

    def plan(self, ctx: ActionContext) -> Plan:
        command = ctx.extra.get("command")
        noninteractive = getattr(ctx.extra, "noninteractive", False)
        if not command and not ctx.dry_run and not noninteractive:
            # Command is missing, we will prompt in execute, but for plan we can just indicate it
            command_desc = "<interactive input>"
        else:
            command_desc = command or "<missing command>"

        return Plan(
            action_id=self.spec.id,
            reversible=False,
            risk_tier=self.spec.risk_tier,
            steps=[
                PlanStep(description=f"Connect to EC2 instance {ctx.target.resource}", impact="read-only"),
                PlanStep(description=f"Execute command: {command_desc}"),
            ],
        )

    def execute(self, ctx: ActionContext) -> ActionResult:
        aws = ctx.extra.get("connectors", {}).get("aws")
        if not aws:
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary="AWS connector is missing or not configured.",
            )

        command = ctx.extra.get("command")
        noninteractive = getattr(ctx.extra, "noninteractive", False)
        
        if not command:
            if noninteractive:
                return ActionResult(
                    status=ActionResultStatus.FAILED,
                    summary="No command provided and running in non-interactive mode.",
                )
            try:
                command = Prompt.ask(f"Enter the command to execute on {ctx.target.resource}")
            except (EOFError, KeyboardInterrupt):
                return ActionResult(
                    status=ActionResultStatus.SKIPPED,
                    summary="Command input cancelled by user.",
                )
            if not command:
                return ActionResult(
                    status=ActionResultStatus.SKIPPED,
                    summary="No command entered.",
                )

        pem_path = ctx.extra.get("pem_path")

        try:
            res = aws.execute_command(ctx.target.resource, command, pem_path=pem_path)
        except SSMFailedNeedsSSH as exc:
            if noninteractive:
                return ActionResult(
                    status=ActionResultStatus.FAILED,
                    summary=f"SSM execution failed and running in non-interactive mode. Needs SSH fallback: {exc}",
                )
            try:
                from rich.console import Console
                console = Console()
                console.print(f"[yellow]{exc}[/yellow]")
                pem_path = Prompt.ask(f"Enter the path to the SSH .pem file for {ctx.target.resource}")
            except (EOFError, KeyboardInterrupt):
                return ActionResult(
                    status=ActionResultStatus.SKIPPED,
                    summary="PEM path input cancelled by user.",
                )
            if not pem_path:
                return ActionResult(
                    status=ActionResultStatus.SKIPPED,
                    summary="No PEM path entered.",
                )
            # Retry with SSH
            try:
                res = aws.execute_command(ctx.target.resource, command, pem_path=pem_path)
            except Exception as e:
                return ActionResult(
                    status=ActionResultStatus.FAILED,
                    summary=f"SSH execution failed: {e}",
                )
        except Exception as exc:  # noqa: BLE001
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary=f"execution failed: {exc}",
            )

        if "error" in res:
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary=f"Execution error: {res['error']}",
            )

        # Successful execution
        summary = f"Command executed via {res.get('source')}. Status: {res.get('status')}"
        return ActionResult(
            status=ActionResultStatus.SUCCEEDED,
            summary=summary,
            detail=res,
        )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        res = result.detail
        status_val = res.get("status", "").lower()
        if "success" in status_val or res.get("exit_code", 0) == 0:
            return VerificationResult(ok=True, detail="Command completed successfully")
        return VerificationResult(ok=False, detail=f"Command may have failed. Status: {status_val}, STDERR: {res.get('stderr', '').strip()}")
