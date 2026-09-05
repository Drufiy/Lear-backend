import codecs

content = """

def format_gcp_context(target: str, state, events: list[dict]) -> str:
    parts = [
        "=== GCP INSTANCE STATUS ===",
        f"target: {target}",
        f"state: {state.state.value if hasattr(state, 'state') else state}",
        "",
        "=== GCP EVENTS (METRICS & LOGS) ===",
    ]
    if events:
        for e in events:
            parts.append(f"- {e.get('timestamp')}: [{e.get('event_type')}] {e.get('summary')}")
    else:
        parts.append("(no events)")
    return "\\n".join(parts)
"""

with codecs.open('prash/brain/diagnosis_agent.py', 'a', encoding='utf-8') as f:
    f.write(content)
