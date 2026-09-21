"""Test script to verify AWS EKS connectivity via Prash's native KubernetesConnector."""

import os
import sys

# Load .env variables
env_vars = {}
if os.path.exists(".env"):
    with open(".env", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip().strip("'\"")

for k, v in env_vars.items():
    if k not in os.environ:
        os.environ[k] = v

print("=" * 60)
print("PRASH KUBERNETES CONNECTOR VERIFICATION")
print("=" * 60)
print(f"KUBE_CONTEXT  : {os.environ.get('KUBE_CONTEXT', 'Not set (using current-context)')}")
print(f"KUBE_NAMESPACE: {os.environ.get('KUBE_NAMESPACE', 'default')}")
print(f"AWS_REGION    : {os.environ.get('AWS_REGION', 'ap-south-1')}")
print("-" * 60)

try:
    from prash.connectors.kubernetes import KubernetesConnector

    conn = KubernetesConnector(credentials=env_vars)
    success = conn.authenticate()

    if not success:
        print(f"FAILED to authenticate with Kubernetes cluster!")
        print(f"Error: {conn.auth_error}")
        sys.exit(1)

    print("SUCCESS: Authenticated with cluster!")
    print(f"Cluster Info  : {conn.auth_identity}")

    # Query nodes
    nodes = conn.core_v1.list_node().items
    print(f"\nDiscovered {len(nodes)} cluster nodes:")
    for node in nodes:
        ready_cond = next((c for c in node.status.conditions if c.type == "Ready"), None)
        status = ready_cond.status if ready_cond else "Unknown"
        node_name = node.metadata.name
        instance_type = node.metadata.labels.get("node.kubernetes.io/instance-type", "unknown")
        zone = node.metadata.labels.get("topology.kubernetes.io/zone", "unknown")
        print(f"  - Node: {node_name} | Ready: {status} | Type: {instance_type} | Zone: {zone}")

    # Query namespaces
    target_ns = os.environ.get("KUBE_NAMESPACE", "lear-demo")
    namespaces = [ns.metadata.name for ns in conn.core_v1.list_namespace().items]
    print(f"\nNamespaces found: {len(namespaces)}")
    if target_ns in namespaces:
        print(f"Target namespace '{target_ns}' exists: YES")
    else:
        print(f"Target namespace '{target_ns}' exists: NO (will be created)")

    # Query pods in target namespace
    pods = conn.core_v1.list_namespaced_pod(namespace=target_ns).items
    print(f"Pods in namespace '{target_ns}': {len(pods)}")
    for pod in pods:
        print(f"  - Pod: {pod.metadata.name} | Phase: {pod.status.phase}")

    print("\n" + "=" * 60)
    print("ALL CHECKS PASSED - Prash is fully connected to EKS!")
    print("=" * 60)

except Exception as e:
    print(f"ERROR: {type(e).__name__} - {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
