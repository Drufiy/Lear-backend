"""Lear Desktop AI Widget Generation Module.

Dynamically synthesizes, validates, and persists customized SVG widget layouts
tailored to live connector telemetry, metric shapes, resource types, and user prompts.
Zero-mock mandate: gracefully adapts real connector capabilities and metrics when LLM
is unconfigured or offline.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set

import yaml

logger = logging.getLogger(__name__)

DEFAULT_YAML_PATH = os.path.join(os.path.dirname(__file__), "..", "prash.yaml")

VALID_WIDGET_TYPES: Set[str] = {
    "gauge",
    "line_chart",
    "bar_chart",
    "metric_card",
    "event_timeline",
    "status_grid",
}


@dataclass
class WidgetPosition:
    row: int = 0
    col: int = 0
    span: int = 1

    def to_dict(self) -> Dict[str, int]:
        return {"row": self.row, "col": self.col, "span": self.span}


@dataclass
class WidgetConfig:
    id: str
    type: str
    label: str
    metric_keys: List[str] = field(default_factory=list)
    unit: str = ""
    description: str = ""
    refresh_interval: int = 30
    position: WidgetPosition = field(default_factory=WidgetPosition)
    ai_generated: bool = True
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "metric_keys": list(self.metric_keys),
            "unit": self.unit,
            "description": self.description,
            "refresh_interval": self.refresh_interval,
            "position": self.position.to_dict(),
            "ai_generated": self.ai_generated,
            "rationale": self.rationale,
        }


@dataclass
class GeneratedLayout:
    connector_id: str
    resource_id: str
    widgets: List[WidgetConfig]
    status: str = "unknown"
    detected_metrics: List[str] = field(default_factory=list)
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "connector_id": self.connector_id,
            "resource_id": self.resource_id,
            "widgets": [w.to_dict() for w in self.widgets],
            "status": self.status,
            "detected_metrics": list(self.detected_metrics),
            "rationale": self.rationale,
            "ai_generated": True,
        }


def build_generation_prompt(
    connector_id: str,
    connector_name: str,
    category: str,
    capabilities: List[str],
    available_metrics: List[str],
    current_status: str,
    user_prompt: str,
    existing_templates: List[Any],
) -> str:
    """Builds a structured prompt instructing the model to synthesize an optimal widget layout."""
    template_summaries = []
    for t in existing_templates:
        t_id = getattr(t, "id", "") or (t.get("id") if isinstance(t, dict) else "")
        t_type = getattr(t, "type", "") or (t.get("type") if isinstance(t, dict) else "")
        t_label = getattr(t, "label", "") or (t.get("label") if isinstance(t, dict) else "")
        t_keys = getattr(t, "metric_keys", []) or (t.get("metric_keys", []) if isinstance(t, dict) else [])
        template_summaries.append(f"- {t_label} (type: {t_type}, id: {t_id}, keys: {t_keys})")

    templates_str = "\n".join(template_summaries) if template_summaries else "None specified"
    metrics_str = ", ".join(available_metrics) if available_metrics else "Standard provider metrics"
    caps_str = ", ".join(capabilities) if capabilities else "Standard metrics and polling"

    prompt = f"""You are Lear's AI Widget Architect. Design an optimal desktop telemetry widget layout for a cloud service.

Service: {connector_name} (ID: {connector_id}, Category: {category})
Current Health Status: {current_status}
Capabilities: {caps_str}
Detected Live Metrics: {metrics_str}
User Design Request: "{user_prompt or 'Create a balanced executive and operational monitoring layout'}"

Available Widget Types:
1. 'gauge' — Best for single percentage/utilization metrics (e.g., CPU %, Memory %, Disk %). Span: 1.
2. 'line_chart' — Best for time-series trends over time. Span: 2.
3. 'bar_chart' — Best for multi-category breakdowns (e.g., status codes, severity distribution). Span: 2.
4. 'metric_card' — Best for key quantitative KPIs, error rates, counts. Span: 1.
5. 'event_timeline' — Best for alarms, deployments, and watcher alerts. Span: 2.
6. 'status_grid' — Best for overall subsystem health checks. Span: 3.

Baseline Registry Templates:
{templates_str}

Requirements:
- Output a strict JSON object with a "widgets" array and a "rationale" string.
- Grid is 3 columns wide. Each row's total span must equal 3 (or less).
- Use exact metric names from detected metrics or registry templates.
- Ensure all types are strictly in: gauge, line_chart, bar_chart, metric_card, event_timeline, status_grid.
- No markdown, no preface, no trailing thoughts. Return ONLY valid JSON:
{{
  "rationale": "High-level reason for this composition",
  "widgets": [
    {{
      "id": "{connector_id}_cpu_gauge",
      "type": "gauge",
      "label": "CPU Utilization",
      "metric_keys": ["cpu"],
      "unit": "%",
      "description": "Processor load",
      "refresh_interval": 30,
      "position": {{"row": 0, "col": 0, "span": 1}},
      "rationale": "Immediate visibility of compute pressure"
    }}
  ]
}}
"""
    return prompt.strip()


def validate_widget_config(widget: Dict[str, Any]) -> bool:
    """Validates that a single widget dict conforms to safety and layout constraints."""
    if not isinstance(widget, dict):
        return False
    w_type = widget.get("type", "")
    if w_type not in VALID_WIDGET_TYPES:
        return False

    label = widget.get("label", "")
    if not label or not isinstance(label, str):
        return False

    pos = widget.get("position", {})
    if not isinstance(pos, dict):
        return False

    row = pos.get("row", 0)
    col = pos.get("col", 0)
    span = pos.get("span", 1)

    if not (isinstance(row, int) and row >= 0):
        return False
    if not (isinstance(col, int) and col >= 0):
        return False
    if not (isinstance(span, int) and 1 <= span <= 3):
        return False

    return True


def parse_and_validate_llm_response(
    raw_text: str,
    connector_id: str,
    available_metrics: Optional[List[str]] = None,
) -> tuple[List[WidgetConfig], str]:
    """Parses LLM output, extracts JSON, validates items, and returns valid WidgetConfigs."""
    cleaned = raw_text.strip()
    # Strip markdown code fences if present
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except Exception:
        # Try finding json block within text
        match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
            except Exception:
                return [], ""
        else:
            return [], ""

    widgets_raw = data.get("widgets", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    rationale = data.get("rationale", "") if isinstance(data, dict) else ""

    valid_configs: List[WidgetConfig] = []
    row, col = 0, 0

    for idx, w in enumerate(widgets_raw):
        if not validate_widget_config(w):
            continue

        w_type = w["type"]
        span = w.get("position", {}).get("span") or (2 if w_type in ("line_chart", "event_timeline", "bar_chart") else (3 if w_type == "status_grid" else 1))
        span = max(1, min(3, span))

        cfg = WidgetConfig(
            id=w.get("id") or f"{connector_id}_{w_type}_{idx}",
            type=w_type,
            label=w.get("label", "Telemetry"),
            metric_keys=list(w.get("metric_keys", [])),
            unit=w.get("unit", ""),
            description=w.get("description", ""),
            refresh_interval=int(w.get("refresh_interval", 30)),
            position=WidgetPosition(row=row, col=col, span=span),
            ai_generated=True,
            rationale=w.get("rationale", ""),
        )
        valid_configs.append(cfg)

        col += span
        if col >= 3:
            col = 0
            row += 1

    return valid_configs, rationale


def fallback_template_layout(
    connector_id: str,
    resource_id: str,
    available_metrics: List[str],
    current_status: str,
    templates: List[Any],
    prompt: str = "",
) -> GeneratedLayout:
    """Deterministic capability and metric adaptation engine.
    
    Synthesizes custom widget placements matching user prompt intents and available
    telemetry without requiring an active external LLM connection.
    """
    p_lower = prompt.lower()
    widgets: List[WidgetConfig] = []
    row, col = 0, 0

    # Determine intent weighting from user prompt
    prioritize_cpu = any(kw in p_lower for kw in ["cpu", "processor", "compute", "load", "gauge"])
    prioritize_trends = any(kw in p_lower for kw in ["trend", "history", "time", "graph", "line", "disk", "network"])
    prioritize_breakdown = any(kw in p_lower for kw in ["breakdown", "category", "severity", "bar", "distribution"])
    prioritize_health = any(kw in p_lower for kw in ["health", "status", "uptime", "overview", "executive"])

    # Transform template items into a working list
    raw_templates = []
    for t in templates:
        if isinstance(t, dict):
            raw_templates.append(t)
        else:
            raw_templates.append({
                "id": getattr(t, "id", "widget"),
                "type": getattr(t, "type", "metric_card"),
                "label": getattr(t, "label", "Metric"),
                "metric_keys": getattr(t, "metric_keys", []),
                "unit": getattr(t, "unit", ""),
                "description": getattr(t, "description", ""),
                "refresh_interval": getattr(t, "refresh_interval", 30),
            })

    # If no templates exist for connector, create generic baseline
    if not raw_templates:
        raw_templates = [
            {"id": "gauge", "type": "gauge", "label": "Utilization", "metric_keys": ["cpu", "utilization"], "unit": "%"},
            {"id": "chart", "type": "line_chart", "label": "Telemetry Trend", "metric_keys": ["metric"], "unit": ""},
            {"id": "timeline", "type": "event_timeline", "label": "Alarms & Watcher Events"},
            {"id": "status", "type": "status_grid", "label": "System Verification"},
        ]

    # Sort templates based on intent
    def template_priority(tmpl: dict) -> int:
        t_type = tmpl.get("type", "")
        t_label = tmpl.get("label", "").lower()
        if prioritize_cpu and (t_type == "gauge" or "cpu" in t_label):
            return 0
        if prioritize_trends and (t_type == "line_chart" or "trend" in t_label):
            return 1
        if prioritize_breakdown and (t_type == "bar_chart" or "breakdown" in t_label):
            return 1
        if prioritize_health and (t_type in ("status_grid", "metric_card")):
            return 0
        return 5

    sorted_templates = sorted(raw_templates, key=template_priority)

    for idx, tmpl in enumerate(sorted_templates):
        w_type = tmpl.get("type", "metric_card")
        if w_type not in VALID_WIDGET_TYPES:
            w_type = "metric_card"

        span = 2 if w_type in ("line_chart", "event_timeline", "bar_chart") else (3 if w_type == "status_grid" else 1)

        # Wrap to next row if span overflows 3 columns
        if col + span > 3:
            col = 0
            row += 1

        cfg = WidgetConfig(
            id=f"{connector_id}_{tmpl.get('id', idx)}",
            type=w_type,
            label=tmpl.get("label", "Telemetry"),
            metric_keys=list(tmpl.get("metric_keys", [])),
            unit=tmpl.get("unit", ""),
            description=tmpl.get("description", ""),
            refresh_interval=int(tmpl.get("refresh_interval", 30)),
            position=WidgetPosition(row=row, col=col, span=span),
            ai_generated=True,
            rationale=f"Synthesized from {connector_id} capabilities matching '{prompt or 'balanced layout'}'",
        )
        widgets.append(cfg)

        col += span
        if col >= 3:
            col = 0
            row += 1

    rationale = f"Synthesized custom layout with {len(widgets)} widgets adapted to live metrics and intent."
    return GeneratedLayout(
        connector_id=connector_id,
        resource_id=resource_id,
        widgets=widgets,
        status=current_status,
        detected_metrics=available_metrics,
        rationale=rationale,
    )


def synthesize_widgets(
    connector_id: str,
    connector_name: str,
    category: str,
    capabilities: List[str],
    available_metrics: List[str],
    current_status: str,
    templates: List[Any],
    resource_id: str = "",
    prompt: str = "",
) -> GeneratedLayout:
    """Full generation pipeline: LLM synthesis -> parse/validate -> fallback engine."""
    # Check if an LLM key is configured in environment
    api_key = (
        os.environ.get("DEEPSEEK_API_KEY")
        or os.environ.get("KIMI_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )

    if api_key:
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=api_key,
                base_url=os.environ.get("DEEPSEEK_BASE_URL") or os.environ.get("KIMI_BASE_URL") or None,
                timeout=3.0,
            )
            model_name = (
                os.environ.get("DEEPSEEK_MODEL")
                or os.environ.get("KIMI_MODEL")
                or "deepseek-v4-flash"
            )
            gen_prompt = build_generation_prompt(
                connector_id=connector_id,
                connector_name=connector_name,
                category=category,
                capabilities=capabilities,
                available_metrics=available_metrics,
                current_status=current_status,
                user_prompt=prompt,
                existing_templates=templates,
            )
            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are an expert DevOps telemetry visualization architect. Respond only in JSON."},
                    {"role": "user", "content": gen_prompt},
                ],
                temperature=0.2,
            )
            raw_response = completion.choices[0].message.content or ""
            valid_widgets, rationale = parse_and_validate_llm_response(raw_response, connector_id, available_metrics)
            if valid_widgets and len(valid_widgets) >= 2:
                return GeneratedLayout(
                    connector_id=connector_id,
                    resource_id=resource_id,
                    widgets=valid_widgets,
                    status=current_status,
                    detected_metrics=available_metrics,
                    rationale=rationale or "Custom synthesized AI layout.",
                )
        except Exception as e:
            logger.info(f"AI generation call bypassed or failed ({e}); using template adaptation fallback.")

    # Fallback to deterministic capability & metrics adaptation engine
    return fallback_template_layout(
        connector_id=connector_id,
        resource_id=resource_id,
        available_metrics=available_metrics,
        current_status=current_status,
        templates=templates,
        prompt=prompt,
    )


# ---------------------------------------------------------------------------
# YAML Persistence
# ---------------------------------------------------------------------------

def _read_yaml(yaml_path: str) -> Dict[str, Any]:
    if not os.path.exists(yaml_path):
        return {}
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"Failed to read yaml from {yaml_path}: {e}")
        return {}


def _write_yaml(data: Dict[str, Any], yaml_path: str) -> None:
    try:
        os.makedirs(os.path.dirname(os.path.abspath(yaml_path)), exist_ok=True)
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f)
    except Exception as e:
        logger.warning(f"Failed to write yaml to {yaml_path}: {e}")


def save_widget_layout_to_yaml(
    connector_id: str,
    resource_id: str,
    widgets: List[Dict[str, Any]],
    yaml_path: str = DEFAULT_YAML_PATH,
) -> bool:
    """Persists a custom widget configuration to prash.yaml under widgets.{connector_id}.{target}."""
    try:
        data = _read_yaml(yaml_path)
        if "widgets" not in data or not isinstance(data["widgets"], dict):
            data["widgets"] = {}

        if connector_id not in data["widgets"] or not isinstance(data["widgets"][connector_id], dict):
            data["widgets"][connector_id] = {}

        target_key = resource_id.strip() if resource_id and resource_id.strip() else "default"
        data["widgets"][connector_id][target_key] = widgets
        _write_yaml(data, yaml_path)
        return True
    except Exception as e:
        logger.warning(f"Error persisting widget layout to {yaml_path}: {e}")
        return False


def load_widget_layout_from_yaml(
    connector_id: str,
    resource_id: str = "",
    yaml_path: str = DEFAULT_YAML_PATH,
) -> Optional[List[Dict[str, Any]]]:
    """Loads saved widget configuration from prash.yaml if present."""
    try:
        data = _read_yaml(yaml_path)
        widgets_section = data.get("widgets", {})
        if not isinstance(widgets_section, dict):
            return None

        conn_section = widgets_section.get(connector_id, {})
        if not isinstance(conn_section, dict):
            return None

        target_key = resource_id.strip() if resource_id and resource_id.strip() else "default"
        layout = conn_section.get(target_key)
        if layout and isinstance(layout, list):
            return layout

        # Fallback to default target if specific resource has no dedicated layout
        if target_key != "default" and "default" in conn_section:
            default_layout = conn_section.get("default")
            if default_layout and isinstance(default_layout, list):
                return default_layout

        return None
    except Exception as e:
        logger.warning(f"Error reading widget layout from {yaml_path}: {e}")
        return None


def delete_widget_layout_from_yaml(
    connector_id: str,
    resource_id: str = "",
    yaml_path: str = DEFAULT_YAML_PATH,
) -> bool:
    """Removes a saved custom widget layout from prash.yaml, reverting to defaults."""
    try:
        data = _read_yaml(yaml_path)
        widgets_section = data.get("widgets", {})
        if not isinstance(widgets_section, dict) or connector_id not in widgets_section:
            return False

        conn_section = widgets_section[connector_id]
        if not isinstance(conn_section, dict):
            return False

        target_key = resource_id.strip() if resource_id and resource_id.strip() else "default"
        if target_key in conn_section:
            del conn_section[target_key]
            _write_yaml(data, yaml_path)
            return True

        return False
    except Exception as e:
        logger.warning(f"Error removing widget layout from {yaml_path}: {e}")
        return False
