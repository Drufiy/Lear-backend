"""Kubernetes connector interface.

Track B owns the real implementation (authenticate -> locate -> fetch logs ->
poll state -> restart). Track C's restart-pod action is written against THIS
interface so it is wiring-ready the moment Track B lands. Until then the stub
returns NOT_FOUND / refuses writes with a clear message instead of pretending
to succeed.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

from .base import Connector, ConnectorState, ResourceState


class K8sConnector(Connector):
    name = "kubernetes"
    read_capabilities = ("pod_status", "pod_logs", "pod_events")
    write_capabilities = ("restart_pod",)

    def __init__(self, credentials: Mapping[str, Any]):
        super().__init__(credentials)
        self._driver = credentials.get("K8S_DRIVER")

    def authenticate(self) -> bool:
        # Real impl: load kubeconfig / in-cluster config. Stub until Track B.
        return False

    def locate(self, resource: str) -> Dict[str, Any]:
        namespace, _, name = resource.partition("/")
        return {"namespace": namespace or "default", "name": name}

    def poll_state(self, resource: str, **kwargs: Any) -> ResourceState:
        handle = self.locate(resource)
        if not self._driver:
            return ResourceState(resource, ConnectorState.NOT_FOUND, {"error": "no kubernetes driver configured"})
        return ResourceState(resource, ConnectorState.UNKNOWN, handle)

    def restart(self, namespace: str, name: str) -> Dict[str, Any]:
        if not self._driver:
            raise NotImplementedError(
                "kubernetes connector not built yet (Track B). restart-pod is "
                "contract-complete and will act through this method once the "
                "driver lands."
            )
        return {"action": "delete_pod", "namespace": namespace, "name": name}
