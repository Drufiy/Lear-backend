"""Action: datadog-alert (CONNECTOR_REWRITE_SPEC §4b, milestone M4).

APPROVAL tier: posting an event is outbound and team-visible -- the whole
point is that the team sees it in Datadog's event stream -- and Datadog's
API has no event deletion, so it can't be cleanly reversed. That's the
spec's default for outbound alerts (the same reasoning pagerduty-page
carries); a "visible to the whole team" side effect is exactly what the
approval prompt exists to surface, even though nothing in Datadog itself
is mutated beyond appending one event.
"""

from __future__ import annotations

import time

from typing import List, Optional

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


class DatadogAlertAction(Action):
    spec = ActionSpec(
        id="datadog-alert",
        summary="Post a visible alert event to the Datadog event stream",
        risk_tier=RiskTier.APPROVAL,
        reversible=False,
        capabilities=("alert",),
        approval_hint="This will create a visible alert in Datadog",
    )

    @staticmethod
    def _tags(extra_tags: object) -> Optional[List[str]]:
        # Accept a list or the comma-separated string the CLI would pass.
        if isinstance(extra_tags, str):
            tags = [tag.strip() for tag in extra_tags.split(",") if tag.strip()]
        elif isinstance(extra_tags, (list, tuple)):
            tags = [str(tag).strip() for tag in extra_tags if str(tag).strip()]
        else:
            tags = []
        return tags or None

    def plan(self, ctx: ActionContext) -> Plan:
        title = ctx.extra.get("title") or f"Prash alert: {ctx.target.resource}"
        priority = ctx.extra.get("priority") or "normal"
        tags = self._tags(ctx.extra.get("tags"))
        return Plan(
            action_id=self.spec.id,
            reversible=False,
            risk_tier=self.spec.risk_tier,
            steps=[
                PlanStep(
                    description=f"Post Datadog event '{title}' (priority {priority})"
                    + (f" tagged {', '.join(tags)}" if tags else ""),
                    impact=f"Visible to the whole team in the Datadog event stream; events cannot be deleted via the API",
                )
            ],
        )

    def execute(self, ctx: ActionContext) -> ActionResult:
        dd = ctx.extra.get("connectors", {}).get("datadog")
        if not dd:
            return ActionResult(status=ActionResultStatus.FAILED, summary="Datadog connector is missing or not configured.")
        title = ctx.extra.get("title") or f"Prash alert: {ctx.target.resource}"
        text = ctx.extra.get("text") or ctx.extra.get("message") or ctx.target.resource
        priority = ctx.extra.get("priority") or "normal"
        tags = self._tags(ctx.extra.get("tags"))
        try:
            resp = dd.post_event(title, text, tags=tags, priority=priority)
        except Exception as exc:  # noqa: BLE001
            return ActionResult(status=ActionResultStatus.FAILED, summary=f"alert failed: {exc}")
        event_id = ""
        if isinstance(resp, dict):
            event_id = str((resp.get("data") or {}).get("id") or "")
        return ActionResult(
            status=ActionResultStatus.SUCCEEDED,
            summary=f"Datadog event '{title}' posted" + (f" (event id {event_id})" if event_id else ""),
            detail={"event_id": event_id, "title": title, "priority": priority, "tags": tags or []},
        )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        dd = ctx.extra.get("connectors", {}).get("datadog")
        if not dd:
            return VerificationResult(ok=False, detail="could not verify: Datadog connector missing")
        event_id = result.detail.get("event_id")
        if not event_id:
            # execute() can only succeed with an event id when the API
            # returned one; without it there is nothing to confirm.
            return VerificationResult(ok=False, detail="could not verify: no event id was returned")

        def _matches(resp: object) -> bool:
            """The GET-by-id returning a payload proves existence; Datadog 404s
            when an event is absent. Identity is checked when the id is visible:
            v1 intake echoes the numeric id as data.id, while v2 GET of the same
            event returns its own encoded data.id with the original id nested at
            attributes.attributes.evt.id (found live 2026-09-07)."""
            if not isinstance(resp, dict) or not resp.get("data"):
                return False
            data = resp["data"]
            if str(data.get("id") or "") == str(event_id):
                return True
            nested = data.get("attributes") or {}
            evt = nested.get("attributes", {}).get("evt", {}) if isinstance(nested, dict) else {}
            return str(evt.get("id") or "") == str(event_id)

        # Found live (2026-09-07): a just-posted event is not queryable for a
        # few seconds (intake -> searchability propagation), so the first GET
        # can 404 while the event exists. Bounded retry: confirm as soon as
        # reality catches up; if it never does, report exactly that instead
        # of claiming a verified success.
        last = ""
        for attempt in range(3):
            try:
                resp = dd.get_event(event_id)
            except Exception as exc:  # noqa: BLE001
                last = f"event {event_id} not found: {exc}"
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
                continue
            if _matches(resp):
                return VerificationResult(ok=True, detail=f"event {event_id} exists in the Datadog event stream")
            last = f"event {event_id} not found in Datadog (may still be propagating)"
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
        return VerificationResult(ok=False, detail=last)
