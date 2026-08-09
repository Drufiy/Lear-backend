"""Connector pattern, ported from v1's vercel_client.py:

    authenticate -> locate resource -> fetch logs -> poll state

Every read/write connector implements this shape so Track B connectors (k8s,
Cloud Run, AWS) and Track C write actions all share one contract. Connectors
hold no credentials of their own: they receive them per-call from the local
CredentialStore.
"""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional


class ConnectorState(enum.Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    CRASH_LOOPING = "crash-looping"
    DEPLOYING = "deploying"
    STABLE = "stable"
    NOT_FOUND = "not-found"


@dataclass
class ResourceState:
    resource: str
    state: ConnectorState
    detail: Dict[str, Any]
    ts: Optional[str] = None


class Connector(abc.ABC):
    """Base class for all Prash connectors."""

    name: str = "base"
    read_capabilities: tuple[str, ...] = ()
    write_capabilities: tuple[str, ...] = ()

    def __init__(self, credentials: Mapping[str, Any]):
        self.credentials = credentials

    @abc.abstractmethod
    def authenticate(self) -> bool:
        """Validate credentials. Never raises; returns False on failure."""

    @abc.abstractmethod
    def locate(self, resource: str) -> Dict[str, Any]:
        """Resolve a human-readable resource id to a concrete handle."""

    def fetch_logs(self, resource: str, **kwargs: Any) -> list[str]:
        """Return raw log lines for a resource."""
        raise NotImplementedError

    def poll_state(self, resource: str, **kwargs: Any) -> ResourceState:
        """Return the current state of a resource."""
        raise NotImplementedError
