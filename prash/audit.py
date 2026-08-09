"""Append-only audit log of every action Prash takes.

The log is append-only by construction: it is opened in append mode and never
rewritten in place. Every entry carries a monotonic sequence, UTC timestamp,
the action id, risk tier, permission mode, environment, decision, outcome, and
verification. This is the user's record of "what did Prash do, when, and did it
work".
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .actions.contract import ActionResult, Decision, RiskTier
from .permissions import PermissionMode


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class AuditLog:
    def __init__(self, path: Optional[Path] = None):
        self.path = path or Path(os.environ.get("PRASH_AUDIT", "~/.prash/audit.jsonl")).expanduser()

    def _open_append(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return self.path.open("a", encoding="utf-8")

    def append(
        self,
        action_id: str,
        risk_tier: RiskTier,
        mode: PermissionMode,
        decision: Decision,
        result: ActionResult,
        environment: str = "staging",
        actor: str = "local",
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        entry_id = uuid.uuid4().hex[:12]
        entry: Dict[str, Any] = {
            "id": entry_id,
            "ts": _utc_now(),
            "seq": self._next_seq(),
            "action": action_id,
            "risk_tier": risk_tier.value,
            "mode": mode.value,
            "decision": decision.value,
            "environment": environment,
            "actor": actor,
            "status": result.status.value,
            "summary": result.summary,
            "verification_ok": bool(result.verification) and result.verification.ok,
            "extra": extra or {},
        }
        with self._open_append() as fh:
            fh.write(json.dumps(entry) + "\n")
        return entry_id

    def _next_seq(self) -> int:
        if not self.path.exists():
            return 1
        last = None
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    last = line
        if last is None:
            return 1
        try:
            return int(json.loads(last)["seq"]) + 1
        except (ValueError, KeyError):
            return 1

    def read(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        entries: List[Dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    entries.append(json.loads(line))
        return entries[-limit:] if limit else entries
