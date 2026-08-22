"""Action: execute-gcp (Track C).

Approval tier: running arbitrary commands on a GCP Compute Engine instance modifies state.
"""

from __future__ import annotations

from rich.prompt import Prompt

from ..connectors.gcp import GCPRunCommandFailedNeedsSSH
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


class ExecuteGCPAction(Action):
    spec = ActionSpec(
        id="execute-gcp",
        summary="Execute a shell command on a GCP Compute Engine instance",
        risk_tier=RiskTier.APPROVAL,
        reversible=False,
        capabilities=("execute",),
    )

    def plan(self, ctx: ActionContext) -> Plan:
        command = ctx.extra.get("command")
        noninteractive = ctx.extra.get("noninteractive", False)
        if not command and not ctx.dry_run and not noninteractive:
            command_desc = "<interactive input>"
        else:
            command_desc = command or "<missing command>"

        return Plan(
            action_id=self.spec.id,
            reversible=False,
            risk_tier=self.spec.risk_tier,
            steps=[
                PlanStep(description=f"Connect to GCP instance {ctx.target.resource}", impact="read-only"),
                PlanStep(description=f"Execute command: {command_desc}"),
            ],
        )

    def execute(self, ctx: ActionContext) -> ActionResult:
        gcp = ctx.extra.get("connectors", {}).get("gcp")
        if not gcp:
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary="GCP connector is missing or not configured.",
            )

        command = ctx.extra.get("command")
        noninteractive = ctx.extra.get("noninteractive", False)
        
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
            res = gcp.execute_command(ctx.target.resource, command, pem_path=pem_path)
        except GCPRunCommandFailedNeedsSSH as exc:
            if noninteractive:
                return ActionResult(
                    status=ActionResultStatus.FAILED,
                    summary=f"GCP execution failed and running in non-interactive mode. Needs SSH fallback: {exc}",
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
            try:
                res = gcp.execute_command(ctx.target.resource, command, pem_path=pem_path)
            except Exception as exc:
                return ActionResult(
                    status=ActionResultStatus.FAILED,
                    summary=f"SSH execution failed: {exc}",
                )
        except Exception as exc:
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary=f"execution failed: {exc}",
            )

        if "error" in res:
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary=f"Execution error: {res['error']}",
            )

        summary = f"Command executed via {res.get('source')}. Status: {res.get('status')}"
        return ActionResult(
            status=ActionResultStatus.SUCCEEDED,
            summary=summary,
            detail=res,
        )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        res = result.detail
        status_val = str(res.get("status", "")).lower()
        if "success" in status_val:
            return VerificationResult(ok=True, detail="Command completed successfully")
        exit_code = res.get("exit_code")
        if exit_code is not None:
            return VerificationResult(
                ok=exit_code == 0,
                detail=f"Command exited {exit_code}. STDERR: {res.get('stderr', '').strip()}",
            )
        return VerificationResult(ok=False, detail=f"Command may have failed. Status: {status_val}, STDERR: {res.get('stderr', '').strip()}")
