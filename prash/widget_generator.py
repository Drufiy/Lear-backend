"""Widget layout generation for the desktop app.

Layouts are derived from each connector's registry ``widget_templates``. An
optional list of AI-proposed candidates can be supplied; every candidate is
validated against the connector's real capabilities before it is used, and the
generator always falls back to the registry templates so a service is never
left without a layout.

This module is deliberately pure (no file or network I/O) so it is easy to test;
persistence lives in ``prash.server``.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from prash.connector_registry import ConnectorRegistryEntry, WidgetTemplate

logger = logging.getLogger(__name__)

VALID_WIDGET_TYPES = {
    "gauge",
    "line_chart",
    "bar_chart",
    "metric_card",
    "event_timeline",
    "status_grid",
}

# Widget types that are driven by numeric metrics and therefore require at
# least one known metric key.
METRIC_DRIVEN_TYPES = {"gauge", "line_chart", "bar_chart", "metric_card"}

_GRID_COLUMNS = 3
_WIDE_TYPES = {"line_chart", "bar_chart", "event_timeline"}
_FULL_WIDTH_TYPES = {"status_grid"}


@dataclass
class WidgetSpec:
    """A single widget in a service layout."""

    id: str
    type: str
    label: str
    metric_keys: List[str] = field(default_factory=list)
    unit: str = ""
    description: str = ""
    refresh_interval: int = 30
    position: Dict[str, int] = field(default_factory=dict)
    ai_generated: bool = False
    rationale: str = ""


@dataclass
class GenerationResult:
    """Outcome of a generation pass, including why candidates were rejected."""

    specs: List[WidgetSpec]
    source: str  # "ai" | "template"
    rejected: List[str] = field(default_factory=list)


def _span_for(widget_type: str) -> int:
    if widget_type in _FULL_WIDTH_TYPES:
        return _GRID_COLUMNS
    if widget_type in _WIDE_TYPES:
        return 2
    return 1


def apply_layout(specs: List[WidgetSpec]) -> List[WidgetSpec]:
    """Assign grid positions for a 3-column layout, wrapping wide widgets."""
    row = 0
    col = 0
    for spec in specs:
        span = _span_for(spec.type)
        if col + span > _GRID_COLUMNS:
            row += 1
            col = 0
        spec.position = {"row": row, "col": col, "span": span}
        col += span
        if col >= _GRID_COLUMNS:
            col = 0
            row += 1
    return specs


def known_metric_keys(entry: ConnectorRegistryEntry) -> set:
    """Every metric key the connector advertises through its templates."""
    return {key.lower() for template in entry.widget_templates for key in template.metric_keys}


def template_specs(entry: ConnectorRegistryEntry) -> List[WidgetSpec]:
    """Build specs from the connector's registry templates (always valid)."""
    specs = [
        WidgetSpec(
            id=template.id,
            type=template.type,
            label=template.label,
            metric_keys=list(template.metric_keys),
            unit=template.unit,
            description=template.description,
            refresh_interval=template.refresh_interval,
            ai_generated=False,
            rationale=f"Registry template for {entry.name}.",
        )
        for template in entry.widget_templates
    ]
    return apply_layout(specs)


def _coerce_spec(raw: Mapping[str, Any]) -> WidgetSpec:
    metric_keys = raw.get("metric_keys") or []
    if not isinstance(metric_keys, (list, tuple)):
        metric_keys = []
    try:
        refresh_interval = int(raw.get("refresh_interval") or 30)
    except (TypeError, ValueError):
        refresh_interval = 30
    position = raw.get("position")
    return WidgetSpec(
        id=str(raw.get("id") or ""),
        type=str(raw.get("type") or ""),
        label=str(raw.get("label") or ""),
        metric_keys=[str(key) for key in metric_keys],
        unit=str(raw.get("unit") or ""),
        description=str(raw.get("description") or ""),
        refresh_interval=refresh_interval,
        position=position if isinstance(position, dict) else {},
        ai_generated=bool(raw.get("ai_generated", False)),
        rationale=str(raw.get("rationale") or ""),
    )


def validate_specs(
    raw_specs: Iterable[Mapping[str, Any]],
    entry: ConnectorRegistryEntry,
    mark_ai: bool = False,
) -> Tuple[List[WidgetSpec], List[str]]:
    """Validate candidate specs against a connector's registry capabilities.

    A candidate is rejected when its type is unknown, it has no label, its id is
    duplicated, a metric-driven widget has no usable metric key, or it
    references a metric the connector does not advertise. ``mark_ai`` stamps
    accepted specs as AI-generated; leave it False for user-authored layouts.
    """
    known = known_metric_keys(entry)
    valid: List[WidgetSpec] = []
    rejected: List[str] = []
    seen_ids: set = set()

    for raw in raw_specs or []:
        if not isinstance(raw, Mapping):
            rejected.append("candidate is not an object")
            continue
        spec = _coerce_spec(raw)
        identity = spec.id or spec.label or spec.type or "unnamed"

        if spec.type not in VALID_WIDGET_TYPES:
            rejected.append(f"{identity}: unsupported widget type '{spec.type}'")
            continue
        if not spec.label.strip():
            rejected.append(f"{identity}: missing label")
            continue
        if not spec.id:
            rejected.append(f"{identity}: missing id")
            continue
        if spec.id in seen_ids:
            rejected.append(f"{identity}: duplicate widget id")
            continue

        unknown = [key for key in spec.metric_keys if key.lower() not in known]
        if unknown:
            rejected.append(f"{identity}: unknown metric keys {', '.join(unknown)}")
            continue
        if spec.type in METRIC_DRIVEN_TYPES and not spec.metric_keys:
            rejected.append(f"{identity}: metric-driven widget has no metric keys")
            continue

        seen_ids.add(spec.id)
        if mark_ai:
            spec.ai_generated = True
            if not spec.rationale:
                spec.rationale = f"AI-synthesized widget for {entry.name}."
        valid.append(spec)

    return valid, rejected


def generate_specs(
    entry: ConnectorRegistryEntry, candidates: Optional[Iterable[Mapping[str, Any]]] = None
) -> GenerationResult:
    """Validate AI candidates, falling back to registry templates.

    Returns AI-validated specs when at least one candidate is valid; otherwise
    returns the connector's registry templates. Rejected candidate reasons are
    always reported so callers can surface them honestly.
    """
    if candidates:
        valid, rejected = validate_specs(candidates, entry, mark_ai=True)
        if valid:
            return GenerationResult(specs=apply_layout(valid), source="ai", rejected=rejected)
        fallback = template_specs(entry)
        return GenerationResult(specs=fallback, source="template", rejected=rejected)

    return GenerationResult(specs=template_specs(entry), source="template", rejected=[])


def specs_to_json(specs: Iterable[WidgetSpec]) -> List[Dict[str, Any]]:
    return [asdict(spec) for spec in specs]


def specs_from_json(raw_specs: Optional[Iterable[Mapping[str, Any]]]) -> List[WidgetSpec]:
    return [_coerce_spec(raw) for raw in (raw_specs or []) if isinstance(raw, Mapping)]
