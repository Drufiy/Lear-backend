"""Unit tests for prash.widget_generator (pure logic, no I/O)."""
from prash.connector_registry import CONNECTOR_REGISTRY
from prash.widget_generator import (
    apply_layout,
    generate_specs,
    known_metric_keys,
    specs_from_json,
    specs_to_json,
    template_specs,
    validate_specs,
    WidgetSpec,
)

AWS = CONNECTOR_REGISTRY["aws"]


def test_known_metric_keys_are_lowercased():
    keys = known_metric_keys(AWS)
    assert "cpuutilization" in keys
    assert "CPUUtilization" not in keys


def test_template_specs_are_always_valid_and_positioned():
    specs = template_specs(AWS)
    assert len(specs) == len(AWS.widget_templates)
    assert all(spec.ai_generated is False for spec in specs)
    assert all(set(spec.position) == {"row", "col", "span"} for spec in specs)


def test_validate_accepts_valid_candidate_and_marks_ai():
    valid, rejected = validate_specs(
        [{"id": "cpu", "type": "gauge", "label": "CPU", "metric_keys": ["cpu"], "unit": "%"}],
        AWS,
        mark_ai=True,
    )
    assert rejected == []
    assert len(valid) == 1
    assert valid[0].ai_generated is True
    assert valid[0].rationale  # filled in for AI candidates


def test_validate_rejects_bad_type_metric_label_and_duplicates():
    candidates = [
        {"id": "a", "type": "pie_chart", "label": "Pie"},
        {"id": "b", "type": "metric_card", "label": "Ghost", "metric_keys": ["NotARealMetric"]},
        {"id": "c", "type": "gauge", "label": "", "metric_keys": ["cpu"]},
        {"id": "d", "type": "gauge", "label": "No keys"},
        {"id": "e", "type": "gauge", "label": "Dup", "metric_keys": ["cpu"]},
        {"id": "e", "type": "gauge", "label": "Dup again", "metric_keys": ["cpu"]},
    ]
    valid, rejected = validate_specs(candidates, AWS)

    assert [spec.id for spec in valid] == ["e"]
    joined = " | ".join(rejected)
    assert "unsupported widget type" in joined
    assert "unknown metric keys" in joined
    assert "missing label" in joined
    assert "no metric keys" in joined
    assert "duplicate widget id" in joined


def test_validate_allows_event_timeline_without_metric_keys():
    valid, rejected = validate_specs(
        [{"id": "events", "type": "event_timeline", "label": "Events"}],
        AWS,
    )
    assert rejected == []
    assert valid[0].type == "event_timeline"


def test_generate_without_candidates_uses_templates():
    result = generate_specs(AWS)
    assert result.source == "template"
    assert result.rejected == []
    assert all(spec.ai_generated is False for spec in result.specs)


def test_generate_prefers_valid_candidates():
    result = generate_specs(
        AWS,
        [
            {"id": "cpu", "type": "gauge", "label": "CPU", "metric_keys": ["CPUUtilization"], "unit": "%"},
            {"id": "bad", "type": "pie_chart", "label": "Pie"},
        ],
    )
    assert result.source == "ai"
    assert [spec.id for spec in result.specs] == ["cpu"]
    assert result.specs[0].ai_generated is True
    assert len(result.rejected) == 1


def test_generate_falls_back_when_every_candidate_is_invalid():
    result = generate_specs(AWS, [{"id": "bad", "type": "pie_chart", "label": "Pie"}])
    assert result.source == "template"
    assert len(result.specs) == len(AWS.widget_templates)
    assert result.rejected


def test_apply_layout_wraps_wide_widgets_across_three_columns():
    specs = [
        WidgetSpec(id="a", type="gauge", label="A"),
        WidgetSpec(id="b", type="line_chart", label="B"),
        WidgetSpec(id="c", type="status_grid", label="C"),
    ]
    apply_layout(specs)
    assert specs[0].position == {"row": 0, "col": 0, "span": 1}
    # gauge (1) + line_chart (2) fill the first row
    assert specs[1].position == {"row": 0, "col": 1, "span": 2}
    # full-width widget starts a new row
    assert specs[2].position == {"row": 1, "col": 0, "span": 3}


def test_specs_json_round_trip():
    specs = template_specs(AWS)
    restored = specs_from_json(specs_to_json(specs))
    assert [spec.id for spec in restored] == [spec.id for spec in specs]
    assert restored[0].metric_keys == specs[0].metric_keys
    assert restored[0].position == specs[0].position
