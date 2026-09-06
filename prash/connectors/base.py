"""Connector pattern, ported from v1's vercel_client.py:

    authenticate -> locate resource -> fetch logs -> poll state

Every read/write connector implements this shape so Track B connectors (k8s,
Cloud Run, AWS) and Track C write actions all share one contract. Connectors
hold no credentials of their own: they receive them per-call from the local
CredentialStore.
"""
import abc
import datetime
import enum
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, TypedDict


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


class ConnectorEvent(TypedDict):
    """Normalized timeline entry — the thing cross-connector correlation joins on."""

    timestamp: datetime.datetime  # UTC, required
    connector: str  # e.g. "datadog", "kubernetes", "github"
    event_type: str  # e.g. "monitor_alert", "metric_spike", "deploy_event"
    summary: str  # one human-readable line — what the diagnosis brain reads first
    raw: dict  # untouched provider-specific payload, for drill-down


class WatchHandle(abc.ABC):
    """Handle returned by a connector's watch() method; the shared watcher
    loop polls it each cycle.

    poll() returns only the events produced since the previous poll (state
    transitions, new timeline entries) — an unchanged cycle returns []. Not
    every provider models watching as a pollable handle (some expose
    lifecycle state instead), so a subclass implements the methods it
    actually supports; the unimplemented ones raise NotImplementedError.
    """

    connector: str  # connector name, e.g. "datadog"
    target: str  # resolved target this handle watches
    interval: int  # suggested seconds between polls

    def poll(self) -> list["ConnectorEvent"]:
        """Run one watch cycle and return any new events since the last poll."""
        raise NotImplementedError

    @property
    def is_active(self) -> bool:
        """True while the watch is running (lifecycle-style handles)."""
        raise NotImplementedError

    def stop(self) -> None:
        """Stop the watch (lifecycle-style handles)."""
        raise NotImplementedError


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

    def watch(self, target: str) -> WatchHandle:
        """Begin monitoring `target`; the handle feeds the shared watcher loop."""
        raise NotImplementedError

    def get_stats(self, target: str, since: datetime.datetime | None = None) -> list[ConnectorEvent]:
        """Return a time series of normalized events for `target`, optionally since a time.

        The time-series complement of poll_state(): it may call poll_state() or
        fetch_logs() internally but does not replace them.
        """
        raise NotImplementedError
