"""Circuit breaker: hard cap on actions per resource per time window.

Day-7 safety rail (PRASH_V2.md §6): without it, a crash-loop in `auto-safe`
mode becomes restart -> crash -> restart, unattended — a self-inflicted
outage. When a resource exceeds ``max_actions`` executions within
``window_seconds``, the breaker opens and Prash stops acting on that resource
and escalates to a human.

State is persisted locally so the cap survives across process restarts (it is
not an in-memory-only guard). The human closes it explicitly with
``prash circuit reset``.

Config (via local credentials / env, schema owned by Track A):
    PRASH_CIRCUIT_MAX_ACTIONS      default 5
    PRASH_CIRCUIT_WINDOW_SECONDS   default 60
    PRASH_CIRCUIT_STATE_PATH       default .prash/circuit.json
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_MAX_ACTIONS = 5
DEFAULT_WINDOW_SECONDS = 60
DEFAULT_STATE_PATH = ".prash/circuit.json"


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class CircuitBreaker:
    max_actions: int
    window_seconds: int
    path: Path
    _state: Dict[str, List[float]] = field(default_factory=dict, init=False)

    @classmethod
    def default(cls) -> "CircuitBreaker":
        return cls(
            max_actions=_int_env("PRASH_CIRCUIT_MAX_ACTIONS", DEFAULT_MAX_ACTIONS),
            window_seconds=_int_env("PRASH_CIRCUIT_WINDOW_SECONDS", DEFAULT_WINDOW_SECONDS),
            path=Path(os.environ.get("PRASH_CIRCUIT_STATE_PATH", DEFAULT_STATE_PATH)).expanduser(),
        )

    def _now(self) -> float:
        return time.time()

    def _load(self) -> None:
        if not self.path.exists():
            self._state = {}
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._state = {str(k): [float(t) for t in v] for k, v in data.get("resources", {}).items()}
        except (ValueError, OSError):
            self._state = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"resources": self._state}
        self.path.write_text(json.dumps(payload), encoding="utf-8")

    def _recent(self, resource: str) -> List[float]:
        cutoff = self._now() - self.window_seconds
        recent = [t for t in self._state.get(resource, []) if t >= cutoff]
        self._state[resource] = recent
        return recent

    def is_open(self, resource: str) -> bool:
        self._load()
        return len(self._recent(resource)) >= self.max_actions

    def record(self, resource: str) -> None:
        self._load()
        recent = self._recent(resource)
        recent.append(self._now())
        self._state[resource] = recent
        self._save()

    def reset(self, resource: Optional[str] = None) -> None:
        self._load()
        if resource is None:
            self._state = {}
        else:
            self._state.pop(resource, None)
        self._save()

    def open_resources(self) -> List[str]:
        self._load()
        return [r for r in self._state if self.is_open(r)]
