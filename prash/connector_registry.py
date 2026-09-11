"""Prash Connector Registry.

Single source of truth for all 13 backend connectors, their configuration schemas,
widget templates, capabilities, and lifecycle management.
Zero hardcoding in frontend or server endpoints; all metadata and discovery
is resolved dynamically from this registry.
"""
from __future__ import annotations

import importlib
import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Type

import dotenv

from prash.connectors.base import Connector

logger = logging.getLogger(__name__)

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")


@dataclass
class AuthField:
    key: str  # env var name, e.g. "AWS_ACCESS_KEY_ID"
    label: str  # human-readable, e.g. "Access Key ID"
    type: str  # "text" | "password" | "textarea" | "file" | "select"
    required: bool = True
    default: str = ""
    placeholder: str = ""
    help_text: str = ""
    options: List[str] = field(default_factory=list)  # for "select" type


@dataclass
class WidgetTemplate:
    id: str  # e.g. "cpu_gauge"
    label: str  # e.g. "CPU Utilization"
    type: str  # "gauge" | "line_chart" | "status_grid" | "event_timeline" | "metric_card" | "bar_chart"
    metric_keys: List[str]  # e.g. ["CPUUtilization"] — maps to connector get_stats() event_types
    unit: str = ""  # e.g. "%", "MB/s", "ms"
    description: str = ""
    refresh_interval: int = 30  # seconds


@dataclass
class ConnectorRegistryEntry:
    id: str  # e.g. "aws"
    name: str  # e.g. "AWS EC2"
    category: str  # "infrastructure" | "cicd" | "monitoring" | "security" | "iac"
    icon: str  # lucide icon name, e.g. "cloud"
    color: str  # hex color, e.g. "#FF9900"
    connector_class_path: str  # e.g. "prash.connectors.aws.AWSConnector"
    auth_fields: List[AuthField]
    widget_templates: List[WidgetTemplate]
    description: str = ""
    docs_url: str = ""
    supports_watch: bool = False
    supports_stats: bool = False
    supports_execute: bool = False

    @property
    def connector_class(self) -> Type[Connector]:
        module_path, class_name = self.connector_class_path.rsplit(".", 1)
        mod = importlib.import_module(module_path)
        return getattr(mod, class_name)


CONNECTOR_REGISTRY: Dict[str, ConnectorRegistryEntry] = {
    "aws": ConnectorRegistryEntry(
        id="aws",
        name="AWS EC2",
        category="infrastructure",
        icon="cloud",
        color="#FF9900",
        connector_class_path="prash.connectors.aws.AWSConnector",
        description="Monitor AWS EC2 instances, CloudWatch metrics, and execute operational actions.",
        docs_url="https://aws.amazon.com/ec2/",
        supports_watch=True,
        supports_stats=True,
        supports_execute=True,
        auth_fields=[
            AuthField(
                key="AWS_ACCESS_KEY_ID",
                label="Access Key ID",
                type="text",
                required=True,
                placeholder="AKIA...",
                help_text="IAM user access key with EC2 and CloudWatch permissions.",
            ),
            AuthField(
                key="AWS_SECRET_ACCESS_KEY",
                label="Secret Access Key",
                type="password",
                required=True,
                help_text="IAM user secret access key.",
            ),
            AuthField(
                key="AWS_REGION",
                label="AWS Region",
                type="text",
                required=False,
                default="us-east-1",
                placeholder="us-east-1",
                help_text="Target AWS region.",
            ),
        ],
        widget_templates=[
            WidgetTemplate(
                id="cpu_gauge",
                label="CPU Utilization",
                type="gauge",
                metric_keys=["CPUUtilization", "cpu"],
                unit="%",
                description="Real-time EC2 instance CPU utilization percentage.",
            ),
            WidgetTemplate(
                id="network_io",
                label="Network I/O",
                type="line_chart",
                metric_keys=["NetworkIn", "NetworkOut", "network"],
                unit="bytes",
                description="Network ingress and egress volume.",
            ),
            WidgetTemplate(
                id="disk_ops",
                label="Disk Operations",
                type="line_chart",
                metric_keys=["DiskReadOps", "DiskWriteOps", "disk_ops"],
                unit="ops",
                description="Disk read/write IOPS.",
            ),
            WidgetTemplate(
                id="status_checks",
                label="Status Checks",
                type="status_grid",
                metric_keys=["StatusCheckFailed", "status"],
                unit="",
                description="System and instance status check health.",
            ),
            WidgetTemplate(
                id="alarms_timeline",
                label="CloudWatch Alarms",
                type="event_timeline",
                metric_keys=["alarm_state_change", "alarm"],
                unit="",
                description="Recent CloudWatch alarm state transitions.",
            ),
        ],
    ),
    "azure": ConnectorRegistryEntry(
        id="azure",
        name="Microsoft Azure",
        category="infrastructure",
        icon="server",
        color="#0078D4",
        connector_class_path="prash.connectors.azure.AzureConnector",
        description="Monitor Azure Virtual Machines and infrastructure metrics via Azure Monitor.",
        docs_url="https://azure.microsoft.com/",
        supports_watch=True,
        supports_stats=True,
        supports_execute=True,
        auth_fields=[
            AuthField(
                key="AZURE_SUBSCRIPTION_ID",
                label="Subscription ID",
                type="text",
                required=True,
                placeholder="00000000-0000-0000-0000-000000000000",
            ),
            AuthField(
                key="AZURE_TENANT_ID",
                label="Tenant ID",
                type="text",
                required=True,
                placeholder="00000000-0000-0000-0000-000000000000",
            ),
            AuthField(
                key="AZURE_CLIENT_ID",
                label="Client ID",
                type="text",
                required=True,
                placeholder="App registration application ID",
            ),
            AuthField(
                key="AZURE_CLIENT_SECRET",
                label="Client Secret",
                type="password",
                required=True,
            ),
            AuthField(
                key="AZURE_LOCATION",
                label="Location",
                type="text",
                required=False,
                default="eastus",
                placeholder="eastus",
            ),
        ],
        widget_templates=[
            WidgetTemplate(
                id="vm_status",
                label="VM Status",
                type="status_grid",
                metric_keys=["vm_status", "status"],
                unit="",
                description="Azure VM power and provisioning state.",
            ),
            WidgetTemplate(
                id="cpu_gauge",
                label="CPU Utilization",
                type="gauge",
                metric_keys=["Percentage CPU", "cpu"],
                unit="%",
                description="Azure VM processor utilization.",
            ),
            WidgetTemplate(
                id="memory_chart",
                label="Available Memory",
                type="line_chart",
                metric_keys=["Available Memory Bytes", "memory"],
                unit="bytes",
                description="Available virtual memory.",
            ),
            WidgetTemplate(
                id="disk_io",
                label="Disk I/O Operations",
                type="line_chart",
                metric_keys=["Disk Read Operations/Sec", "Disk Write Operations/Sec"],
                unit="ops/sec",
                description="Disk operations per second.",
            ),
        ],
    ),
    "gcp": ConnectorRegistryEntry(
        id="gcp",
        name="Google Cloud",
        category="infrastructure",
        icon="cloud-lightning",
        color="#4285F4",
        connector_class_path="prash.connectors.gcp.GCPConnector",
        description="Monitor Google Cloud Compute Engine and Cloud Run services via Cloud Monitoring.",
        docs_url="https://cloud.google.com/",
        supports_watch=True,
        supports_stats=True,
        supports_execute=True,
        auth_fields=[
            AuthField(
                key="GCP_PROJECT_ID",
                label="Project ID",
                type="text",
                required=True,
                placeholder="my-gcp-project",
            ),
            AuthField(
                key="GOOGLE_APPLICATION_CREDENTIALS",
                label="Service Account Key File",
                type="file",
                required=False,
                placeholder="/path/to/key.json",
                help_text="Path to service account JSON key file.",
            ),
            AuthField(
                key="GCP_REGION",
                label="GCP Region",
                type="text",
                required=False,
                default="us-central1",
                placeholder="us-central1",
            ),
        ],
        widget_templates=[
            WidgetTemplate(
                id="instance_status",
                label="Instance Status",
                type="status_grid",
                metric_keys=["instance_status", "status"],
                unit="",
                description="GCP instance lifecycle state.",
            ),
            WidgetTemplate(
                id="cpu_gauge",
                label="CPU Utilization",
                type="gauge",
                metric_keys=["compute.googleapis.com/instance/cpu/utilization", "cpu"],
                unit="%",
                description="GCP Compute Engine CPU utilization.",
            ),
            WidgetTemplate(
                id="network_chart",
                label="Network Traffic",
                type="line_chart",
                metric_keys=["compute.googleapis.com/instance/network/received_bytes_count", "network"],
                unit="bytes",
                description="Received network throughput.",
            ),
            WidgetTemplate(
                id="disk_metrics",
                label="Disk I/O",
                type="line_chart",
                metric_keys=["compute.googleapis.com/instance/disk/read_bytes_count", "disk"],
                unit="bytes",
                description="Disk read byte volume.",
            ),
        ],
    ),
    "kubernetes": ConnectorRegistryEntry(
        id="kubernetes",
        name="Kubernetes",
        category="infrastructure",
        icon="boxes",
        color="#326CE5",
        connector_class_path="prash.connectors.kubernetes.KubernetesConnector",
        description="Monitor Kubernetes pods, deployments, restart counts, and cluster event streams.",
        docs_url="https://kubernetes.io/",
        supports_watch=True,
        supports_stats=True,
        supports_execute=True,
        auth_fields=[
            AuthField(
                key="KUBECONFIG",
                label="Kubeconfig Path",
                type="file",
                required=False,
                placeholder="~/.kube/config",
                help_text="Path to kubeconfig. Defaults to ~/.kube/config or in-cluster config.",
            ),
            AuthField(
                key="KUBE_CONTEXT",
                label="Cluster Context",
                type="text",
                required=False,
                placeholder="my-cluster",
            ),
            AuthField(
                key="KUBE_NAMESPACE",
                label="Namespace",
                type="text",
                required=False,
                default="default",
                placeholder="default",
            ),
        ],
        widget_templates=[
            WidgetTemplate(
                id="pod_status_grid",
                label="Pod Status Grid",
                type="status_grid",
                metric_keys=["pod_status", "status"],
                unit="",
                description="Health matrix across pods and containers.",
            ),
            WidgetTemplate(
                id="restart_count",
                label="Pod Restart Count",
                type="bar_chart",
                metric_keys=["restart_count", "restarts"],
                unit="",
                description="Container restart frequency detecting crash loops.",
            ),
            WidgetTemplate(
                id="memory_per_pod",
                label="Pod Memory",
                type="line_chart",
                metric_keys=["memory_bytes", "memory"],
                unit="bytes",
                description="Working set memory per pod.",
            ),
            WidgetTemplate(
                id="k8s_events",
                label="Cluster Events",
                type="event_timeline",
                metric_keys=["k8s_event", "event"],
                unit="",
                description="Warning and error event timeline from the API server.",
            ),
        ],
    ),
    "vercel": ConnectorRegistryEntry(
        id="vercel",
        name="Vercel",
        category="infrastructure",
        icon="triangle",
        color="#000000",
        connector_class_path="prash.connectors.vercel.VercelConnector",
        description="Monitor Vercel deployments, build times, function invocations, and trigger redeployments.",
        docs_url="https://vercel.com/",
        supports_watch=True,
        supports_stats=True,
        supports_execute=True,
        auth_fields=[
            AuthField(
                key="VERCEL_TOKEN",
                label="API Token",
                type="password",
                required=True,
                placeholder="Bearer token",
                help_text="Personal or team access token.",
            ),
            AuthField(
                key="VERCEL_TEAM_ID",
                label="Team ID",
                type="text",
                required=False,
                placeholder="team_...",
                help_text="Optional team identifier for team-scoped projects.",
            ),
        ],
        widget_templates=[
            WidgetTemplate(
                id="deployment_status",
                label="Deployment Status",
                type="status_grid",
                metric_keys=["deploy_state", "status"],
                unit="",
                description="Latest deployment state (READY, BUILDING, ERROR).",
            ),
            WidgetTemplate(
                id="build_time_chart",
                label="Build Duration",
                type="line_chart",
                metric_keys=["build_duration", "build_time"],
                unit="s",
                description="Time taken to build and deploy project revisions.",
            ),
            WidgetTemplate(
                id="function_invocations",
                label="Function Invocations",
                type="bar_chart",
                metric_keys=["function_invocation", "invocations"],
                unit="",
                description="Serverless function invocation volume.",
            ),
        ],
    ),
    "github": ConnectorRegistryEntry(
        id="github",
        name="GitHub Actions",
        category="cicd",
        icon="git-branch",
        color="#24292E",
        connector_class_path="prash.connectors.github.GitHubConnector",
        description="Monitor GitHub Actions workflow runs, build times, and pull request statuses.",
        docs_url="https://docs.github.com/en/actions",
        supports_watch=True,
        supports_stats=True,
        supports_execute=False,
        auth_fields=[
            AuthField(
                key="GITHUB_TOKEN",
                label="Personal Access Token",
                type="password",
                required=True,
                placeholder="ghp_...",
                help_text="GitHub token with repo and workflow permissions.",
            ),
        ],
        widget_templates=[
            WidgetTemplate(
                id="workflow_status",
                label="Workflow Status",
                type="status_grid",
                metric_keys=["workflow_status", "status"],
                unit="",
                description="Status of active and recent CI workflows.",
            ),
            WidgetTemplate(
                id="recent_runs",
                label="Workflow Runs",
                type="event_timeline",
                metric_keys=["workflow_run", "run"],
                unit="",
                description="Timeline of completed and in-progress CI runs.",
            ),
            WidgetTemplate(
                id="build_time_trend",
                label="Run Duration",
                type="line_chart",
                metric_keys=["run_duration", "duration"],
                unit="s",
                description="Historical build duration across runs.",
            ),
        ],
    ),
    "gitlab": ConnectorRegistryEntry(
        id="gitlab",
        name="GitLab CI",
        category="cicd",
        icon="git-commit",
        color="#FC6D26",
        connector_class_path="prash.connectors.gitlab.GitLabConnector",
        description="Monitor GitLab CI/CD pipelines, test executions, and runner metrics.",
        docs_url="https://docs.gitlab.com/ee/ci/",
        supports_watch=True,
        supports_stats=True,
        supports_execute=False,
        auth_fields=[
            AuthField(
                key="GITLAB_TOKEN",
                label="Access Token",
                type="password",
                required=True,
                placeholder="glpat-...",
                help_text="GitLab personal or project access token.",
            ),
            AuthField(
                key="GITLAB_BASE_URL",
                label="Base URL",
                type="text",
                required=False,
                default="https://gitlab.com",
                placeholder="https://gitlab.com",
                help_text="GitLab instance URL for self-hosted installations.",
            ),
        ],
        widget_templates=[
            WidgetTemplate(
                id="pipeline_status",
                label="Pipeline Status",
                type="status_grid",
                metric_keys=["pipeline_status", "status"],
                unit="",
                description="Current pipeline execution state.",
            ),
            WidgetTemplate(
                id="recent_pipelines",
                label="Pipeline History",
                type="event_timeline",
                metric_keys=["pipeline_run", "pipeline"],
                unit="",
                description="Recent pipeline completions and failures.",
            ),
            WidgetTemplate(
                id="pipeline_duration",
                label="Duration Trend",
                type="line_chart",
                metric_keys=["pipeline_duration", "duration"],
                unit="s",
                description="Pipeline run duration trend.",
            ),
        ],
    ),
    "datadog": ConnectorRegistryEntry(
        id="datadog",
        name="Datadog",
        category="monitoring",
        icon="activity",
        color="#632CA6",
        connector_class_path="prash.connectors.datadog.DatadogConnector",
        description="Integrate Datadog monitor health, log streams, and synthetic checks.",
        docs_url="https://www.datadoghq.com/",
        supports_watch=True,
        supports_stats=True,
        supports_execute=True,
        auth_fields=[
            AuthField(
                key="DATADOG_API_KEY",
                label="API Key",
                type="password",
                required=True,
                help_text="Datadog organization API key.",
            ),
            AuthField(
                key="DATADOG_APP_KEY",
                label="Application Key",
                type="password",
                required=True,
                help_text="Datadog user application key.",
            ),
            AuthField(
                key="DATADOG_SITE",
                label="Site",
                type="text",
                required=False,
                default="datadoghq.com",
                placeholder="datadoghq.com",
                help_text="Site domain (e.g. datadoghq.com, datadoghq.eu).",
            ),
        ],
        widget_templates=[
            WidgetTemplate(
                id="monitor_status_grid",
                label="Monitor Status Grid",
                type="status_grid",
                metric_keys=["monitor_status", "status"],
                unit="",
                description="Health status of configured Datadog monitors.",
            ),
            WidgetTemplate(
                id="alert_timeline",
                label="Alert Timeline",
                type="event_timeline",
                metric_keys=["alert", "event"],
                unit="",
                description="Triggered alerts and monitor transitions.",
            ),
            WidgetTemplate(
                id="custom_metric",
                label="Metric Chart",
                type="line_chart",
                metric_keys=["metric_value", "metric"],
                unit="",
                description="Custom telemetry timeseries queries.",
            ),
        ],
    ),
    "grafana": ConnectorRegistryEntry(
        id="grafana",
        name="Grafana",
        category="monitoring",
        icon="bar-chart-2",
        color="#F46800",
        connector_class_path="prash.connectors.grafana.GrafanaConnector",
        description="Monitor Grafana alert rules, dashboard panels, and incident annotations.",
        docs_url="https://grafana.com/",
        supports_watch=True,
        supports_stats=True,
        supports_execute=True,
        auth_fields=[
            AuthField(
                key="GRAFANA_URL",
                label="Grafana URL",
                type="text",
                required=True,
                placeholder="https://myorg.grafana.net",
                help_text="URL of your Grafana Cloud or self-hosted instance.",
            ),
            AuthField(
                key="GRAFANA_API_KEY",
                label="API Key or Token",
                type="password",
                required=True,
                help_text="Service account token or legacy API key.",
            ),
        ],
        widget_templates=[
            WidgetTemplate(
                id="alert_rules",
                label="Alert Rules",
                type="status_grid",
                metric_keys=["alert_rule", "status"],
                unit="",
                description="Firing vs normal alert evaluation states.",
            ),
            WidgetTemplate(
                id="annotations_timeline",
                label="Annotations",
                type="event_timeline",
                metric_keys=["annotation", "event"],
                unit="",
                description="Timeline of deployments and operational annotations.",
            ),
        ],
    ),
    "pagerduty": ConnectorRegistryEntry(
        id="pagerduty",
        name="PagerDuty",
        category="monitoring",
        icon="bell",
        color="#06AC38",
        connector_class_path="prash.connectors.pagerduty.PagerDutyConnector",
        description="Track active PagerDuty incidents, on-call rotations, and trigger escalations.",
        docs_url="https://www.pagerduty.com/",
        supports_watch=True,
        supports_stats=True,
        supports_execute=True,
        auth_fields=[
            AuthField(
                key="PAGERDUTY_API_KEY",
                label="REST API Key",
                type="password",
                required=True,
                help_text="Account-level REST API key.",
            ),
            AuthField(
                key="PAGERDUTY_FROM_EMAIL",
                label="User Email",
                type="text",
                required=False,
                placeholder="user@company.com",
                help_text="Required for incident acknowledge/resolve actions.",
            ),
            AuthField(
                key="PAGERDUTY_ROUTING_KEY",
                label="Events Routing Key",
                type="password",
                required=False,
                help_text="Integration key for triggering PagerDuty Events v2.",
            ),
        ],
        widget_templates=[
            WidgetTemplate(
                id="incident_timeline",
                label="Incident Timeline",
                type="event_timeline",
                metric_keys=["incident", "event"],
                unit="",
                description="Active and resolved incident timeline.",
            ),
            WidgetTemplate(
                id="on_call_status",
                label="On-Call Status",
                type="status_grid",
                metric_keys=["on_call", "status"],
                unit="",
                description="Current primary and secondary engineers on call.",
            ),
        ],
    ),
    "snyk": ConnectorRegistryEntry(
        id="snyk",
        name="Snyk",
        category="security",
        icon="shield",
        color="#4C4A73",
        connector_class_path="prash.connectors.snyk.SnykConnector",
        description="Monitor vulnerabilities, license issues, and code security status.",
        docs_url="https://snyk.io/",
        supports_watch=True,
        supports_stats=True,
        supports_execute=True,
        auth_fields=[
            AuthField(
                key="SNYK_API_TOKEN",
                label="API Token",
                type="password",
                required=True,
                help_text="Snyk personal or service account token.",
            ),
            AuthField(
                key="SNYK_ORG_ID",
                label="Organization ID",
                type="text",
                required=True,
                placeholder="00000000-0000-0000-0000-000000000000",
                help_text="Target Snyk organization UUID.",
            ),
        ],
        widget_templates=[
            WidgetTemplate(
                id="vulnerability_count",
                label="Vulnerability Count",
                type="metric_card",
                metric_keys=["vulnerability_count", "count"],
                unit="",
                description="Total active vulnerabilities across projects.",
            ),
            WidgetTemplate(
                id="severity_breakdown",
                label="Severity Breakdown",
                type="bar_chart",
                metric_keys=["severity_high", "severity_medium", "severity_low"],
                unit="",
                description="Critical, high, medium, and low issues distribution.",
            ),
        ],
    ),
    "gitleaks": ConnectorRegistryEntry(
        id="gitleaks",
        name="Gitleaks",
        category="security",
        icon="lock",
        color="#FF6B6B",
        connector_class_path="prash.connectors.gitleaks.GitleaksConnector",
        description="Local repository secret detection and prevention scanning.",
        docs_url="https://github.com/gitleaks/gitleaks",
        supports_watch=True,
        supports_stats=True,
        supports_execute=False,
        auth_fields=[
            AuthField(
                key="GITLEAKS_BINARY",
                label="Gitleaks Binary Path",
                type="text",
                required=False,
                default="gitleaks",
                placeholder="gitleaks",
                help_text="Path to gitleaks executable. Defaults to 'gitleaks' on PATH.",
            ),
        ],
        widget_templates=[
            WidgetTemplate(
                id="secret_count",
                label="Secrets Found",
                type="metric_card",
                metric_keys=["secret_count", "count"],
                unit="",
                description="Total detected secret leaks in current repository.",
            ),
            WidgetTemplate(
                id="scan_results",
                label="Scan Findings",
                type="event_timeline",
                metric_keys=["secret_finding", "finding"],
                unit="",
                description="Specific file and line leak incidents.",
            ),
        ],
    ),
    "terraform": ConnectorRegistryEntry(
        id="terraform",
        name="Terraform",
        category="iac",
        icon="layers",
        color="#7B42BC",
        connector_class_path="prash.connectors.terraform.TerraformConnector",
        description="Detect infrastructure drift, resource changes, and state status.",
        docs_url="https://www.terraform.io/",
        supports_watch=True,
        supports_stats=True,
        supports_execute=True,
        auth_fields=[
            AuthField(
                key="TERRAFORM_STATE_PATH",
                label="State File / Directory",
                type="file",
                required=False,
                default=".",
                placeholder=".",
                help_text="Local directory containing terraform configuration or .tfstate file.",
            ),
            AuthField(
                key="TERRAFORM_USE_CLOUD",
                label="Use Terraform Cloud",
                type="select",
                required=False,
                default="false",
                options=["false", "true"],
                help_text="Set to 'true' if using Terraform Cloud / HCP.",
            ),
            AuthField(
                key="TERRAFORM_API_TOKEN",
                label="Terraform Cloud API Token",
                type="password",
                required=False,
                help_text="API token for Terraform Cloud (if cloud is enabled).",
            ),
        ],
        widget_templates=[
            WidgetTemplate(
                id="drift_status",
                label="Drift Status",
                type="status_grid",
                metric_keys=["drift", "status"],
                unit="",
                description="Detected configuration drift against actual infrastructure.",
            ),
            WidgetTemplate(
                id="resource_count",
                label="Managed Resources",
                type="metric_card",
                metric_keys=["resource_count", "count"],
                unit="",
                description="Total resources tracked in state.",
            ),
        ],
    ),
}

_active_connectors: Dict[str, Connector] = {}


def get_registry() -> Dict[str, ConnectorRegistryEntry]:
    """Return the complete registry of all connectors."""
    return CONNECTOR_REGISTRY


def get_missing_fields(connector_id: str, env_config: Mapping[str, Any]) -> List[str]:
    """Return a list of required auth field keys missing or empty in env_config."""
    entry = CONNECTOR_REGISTRY.get(connector_id)
    if not entry:
        return []
    missing = []
    for f in entry.auth_fields:
        if f.required:
            val = env_config.get(f.key)
            if not val or not str(val).strip():
                missing.append(f.key)
    return missing


def is_connector_configured(connector_id: str, env_config: Mapping[str, Any]) -> bool:
    """Check if a connector has all required credentials configured."""
    entry = CONNECTOR_REGISTRY.get(connector_id)
    if not entry:
        return False

    # Connectors with no auth fields at all (e.g. self-contained or test connectors)
    if not entry.auth_fields:
        return True

    required_fields = [f for f in entry.auth_fields if f.required]
    if not required_fields:
        # For connectors with only optional fields (e.g. gitleaks, local terraform),
        # consider configured if any of its config keys are present in env
        return any(bool(env_config.get(f.key)) for f in entry.auth_fields)

    return len(get_missing_fields(connector_id, env_config)) == 0


def discover_configured(env_config: Mapping[str, Any]) -> List[str]:
    """Return IDs of all connectors whose required credentials exist in env_config."""
    return [
        cid
        for cid, entry in CONNECTOR_REGISTRY.items()
        if is_connector_configured(cid, env_config)
    ]


def get_connector(connector_id: str, env_config: Optional[Mapping[str, Any]] = None) -> Connector:
    """Get or create an active connector instance dynamically from the registry."""
    if connector_id in _active_connectors:
        return _active_connectors[connector_id]

    entry = CONNECTOR_REGISTRY.get(connector_id)
    if not entry:
        raise KeyError(f"Unknown connector ID: {connector_id}")

    if env_config is None:
        env_config = dotenv.dotenv_values(ENV_PATH)

    cls = entry.connector_class
    instance = cls(env_config)
    _active_connectors[connector_id] = instance
    return instance


def clear_connector_cache(connector_id: Optional[str] = None) -> None:
    """Clear cached connector instances, allowing reload with new credentials."""
    global _active_connectors
    if connector_id:
        _active_connectors.pop(connector_id, None)
    else:
        _active_connectors.clear()


def mask_credential(value: Optional[str]) -> str:
    """Safely mask credential string, revealing only first 3 and last 3 characters."""
    if not value:
        return ""
    val_str = str(value).strip()
    if len(val_str) <= 6:
        return "***"
    return f"{val_str[:3]}...{val_str[-3:]}"


def registry_to_json(env_config: Optional[Mapping[str, Any]] = None) -> List[Dict[str, Any]]:
    """Serialize the full registry to a JSON-ready list for frontend consumption."""
    if env_config is None:
        env_config = dotenv.dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}

    result = []
    for cid, entry in CONNECTOR_REGISTRY.items():
        missing = get_missing_fields(cid, env_config)
        configured = is_connector_configured(cid, env_config)
        masked = {
            f.key: mask_credential(env_config.get(f.key))
            for f in entry.auth_fields
            if f.key in env_config and env_config.get(f.key)
        }

        entry_dict = {
            "id": entry.id,
            "name": entry.name,
            "category": entry.category,
            "icon": entry.icon,
            "color": entry.color,
            "description": entry.description,
            "docs_url": entry.docs_url,
            "status": "configured" if configured else "unconfigured",
            "missing_fields": missing,
            "masked_credentials": masked,
            "supports_watch": entry.supports_watch,
            "supports_stats": entry.supports_stats,
            "supports_execute": entry.supports_execute,
            "auth_fields": [asdict(f) for f in entry.auth_fields],
            "widget_templates": [asdict(w) for w in entry.widget_templates],
        }
        result.append(entry_dict)

    return result


def connector_detail_to_json(
    connector_id: str, env_config: Optional[Mapping[str, Any]] = None
) -> Dict[str, Any]:
    """Serialize metadata for a single connector."""
    entry = CONNECTOR_REGISTRY.get(connector_id)
    if not entry:
        raise KeyError(f"Unknown connector ID: {connector_id}")

    if env_config is None:
        env_config = dotenv.dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}

    missing = get_missing_fields(connector_id, env_config)
    configured = is_connector_configured(connector_id, env_config)
    masked = {
        f.key: mask_credential(env_config.get(f.key))
        for f in entry.auth_fields
        if f.key in env_config and env_config.get(f.key)
    }

    return {
        "id": entry.id,
        "name": entry.name,
        "category": entry.category,
        "icon": entry.icon,
        "color": entry.color,
        "description": entry.description,
        "docs_url": entry.docs_url,
        "status": "configured" if configured else "unconfigured",
        "missing_fields": missing,
        "masked_credentials": masked,
        "supports_watch": entry.supports_watch,
        "supports_stats": entry.supports_stats,
        "supports_execute": entry.supports_execute,
        "auth_fields": [asdict(f) for f in entry.auth_fields],
        "widget_templates": [asdict(w) for w in entry.widget_templates],
    }
