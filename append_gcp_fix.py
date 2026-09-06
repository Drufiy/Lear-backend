import codecs

# 1. Update imports in fix.py
with codecs.open('prash/fix.py', 'r', encoding='utf-8') as f:
    content = f.read()

if 'format_gcp_context' not in content:
    content = content.replace(
        'format_aws_context,',
        'format_aws_context,\n    format_gcp_context,'
    )
    # Also add GCPConnector to imports
    if 'GCPConnector' not in content:
        content = content.replace(
            'from .connectors.aws import AWSConnector',
            'from .connectors.aws import AWSConnector\nfrom .connectors.gcp import GCPConnector'
        )

# 2. Add diagnose_gcp_instance to fix.py
gcp_func = """

async def diagnose_gcp_instance(
    target: str,
    creds: dict,
) -> Diagnosis:
    \"\"\"Gather GCP connector metrics, state, and logs for an instance, feed them to
    Track D's brain, and return the Diagnosis.
    \"\"\"
    import datetime
    
    gcp = GCPConnector(creds)
    info = gcp.locate(target)
    if not info:
        raise FixTargetError(f"GCP instance {target} not found")
        
    state = gcp.poll_state(target)
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)
    stats = gcp.get_stats(target, since=since)
    
    context = format_gcp_context(target, state, stats)
    
    return await diagnose_failure(
        logs=context,
        repo_full_name=target,
        commit_message="(no commit — GCP instance diagnosis)",
        workflow_name="gcp",
        investigation_context=None,
        multi_file=False,
        category_hint="gcp infrastructure, resource limits, instance state",
        include_manifest_tools=False,
    )
"""

if 'def diagnose_gcp_instance' not in content:
    content += gcp_func

with codecs.open('prash/fix.py', 'w', encoding='utf-8') as f:
    f.write(content)
