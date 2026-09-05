"""Action: aws-alert (Track C).

Publishes an alert to an SNS topic. Requires AWS_SNS_TOPIC_ARN in the credentials.
"""

from __future__ import annotations

from .alert_base import AlertAction
from .contract import ActionContext, ActionResult, ActionResultStatus, ActionSpec, Plan, PlanStep, RiskTier, VerificationResult

class AWSAlertAction(AlertAction):
    spec = ActionSpec(
        id="aws-alert",
        summary="Publish an alert via AWS SNS",
        risk_tier=RiskTier.APPROVAL,
        reversible=False,
        capabilities=("alert",),
        approval_hint="This will publish a message to an SNS topic"
    )

    def plan(self, ctx: ActionContext) -> Plan:
        # Access credentials safely. Depending on structure, it might be in ctx.extra or require connector
        topic_arn = ctx.extra.get("connectors", {}).get("aws", {}).credentials.get("AWS_SNS_TOPIC_ARN", "<missing topic ARN>") if ctx.extra.get("connectors", {}).get("aws") else "<missing topic ARN>"
        message = ctx.extra.get("message", "<no message provided>")
        
        return Plan(
            action_id=self.spec.id,
            reversible=False,
            risk_tier=self.spec.risk_tier,
            steps=[
                PlanStep(description=f"Publish alert to SNS topic {topic_arn}: {message}"),
            ],
        )

    def execute(self, ctx: ActionContext) -> ActionResult:
        aws = ctx.extra.get("connectors", {}).get("aws")
        if not aws:
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary="AWS connector is missing or not configured.",
            )

        topic_arn = aws.credentials.get("AWS_SNS_TOPIC_ARN")
        if not topic_arn:
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary="AWS_SNS_TOPIC_ARN credential is required for aws-alert.",
            )

        message = ctx.extra.get("message")
        if not message:
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary="Message payload is missing for alert.",
            )

        try:
            session = aws._get_boto_session()
            sns = session.client("sns")
            resp = sns.publish(
                TopicArn=topic_arn,
                Message=message,
                Subject="Prash Autonomous Alert"
            )
            return ActionResult(
                status=ActionResultStatus.SUCCEEDED,
                summary=f"Alert published successfully.",
                detail=resp,
            )
        except Exception as exc:  # noqa: BLE001
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary=f"Failed to publish SNS alert: {exc}",
            )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        if result.status == ActionResultStatus.SUCCEEDED and "MessageId" in result.detail:
            return VerificationResult(ok=True, detail=f"Message ID: {result.detail['MessageId']}")
        return VerificationResult(ok=False, detail="Publish failed or missing MessageId")
