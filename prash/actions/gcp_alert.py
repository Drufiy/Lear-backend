"""Action: gcp-alert (Track C).

Publishes an alert to a GCP Pub/Sub topic. Requires GCP_PUBSUB_TOPIC in the credentials.
"""

from __future__ import annotations

import base64

try:
    from googleapiclient import discovery
except ImportError:
    pass

from .alert_base import AlertAction
from .contract import ActionContext, ActionResult, ActionResultStatus, ActionSpec, Plan, PlanStep, RiskTier, VerificationResult

class GCPAlertAction(AlertAction):
    spec = ActionSpec(
        id="gcp-alert",
        summary="Publish an alert via GCP Pub/Sub",
        risk_tier=RiskTier.APPROVAL,
        reversible=False,
        capabilities=("alert",),
        approval_hint="This will publish a message to a Pub/Sub topic"
    )

    def plan(self, ctx: ActionContext) -> Plan:
        topic = ctx.extra.get("connectors", {}).get("gcp", {}).credentials.get("GCP_PUBSUB_TOPIC", "<missing topic>") if ctx.extra.get("connectors", {}).get("gcp") else "<missing topic>"
        message = ctx.extra.get("message", "<no message provided>")
        
        return Plan(
            action_id=self.spec.id,
            reversible=False,
            risk_tier=self.spec.risk_tier,
            steps=[
                PlanStep(description=f"Publish alert to Pub/Sub topic {topic}: {message}"),
            ],
        )

    def execute(self, ctx: ActionContext) -> ActionResult:
        gcp = ctx.extra.get("connectors", {}).get("gcp")
        if not gcp:
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary="GCP connector is missing or not configured.",
            )

        topic = gcp.credentials.get("GCP_PUBSUB_TOPIC")
        if not topic:
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary="GCP_PUBSUB_TOPIC credential is required for gcp-alert.",
            )

        message = ctx.extra.get("message")
        if not message:
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary="Message payload is missing for alert.",
            )

        if not gcp.authenticate():
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary="GCP connector failed to authenticate.",
            )

        try:
            pubsub = discovery.build('pubsub', 'v1', credentials=gcp._creds, cache_discovery=False)
            data = base64.b64encode(message.encode("utf-8")).decode("utf-8")
            
            project_id = gcp.project_id
            full_topic = topic if "projects/" in topic else f"projects/{project_id}/topics/{topic}"
            
            body = {
                "messages": [
                    {"data": data}
                ]
            }
            resp = pubsub.projects().topics().publish(topic=full_topic, body=body).execute()
            return ActionResult(
                status=ActionResultStatus.SUCCEEDED,
                summary=f"Alert published successfully.",
                detail=resp,
            )
        except Exception as exc:  # noqa: BLE001
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary=f"Failed to publish Pub/Sub alert: {exc}",
            )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        if result.status == ActionResultStatus.SUCCEEDED and "messageIds" in result.detail:
            return VerificationResult(ok=True, detail=f"Message ID: {result.detail['messageIds'][0]}")
        return VerificationResult(ok=False, detail="Publish failed or missing messageIds")
