# Feature 16 — AI Widget Generation 🟡 PARTIALLY DONE

**Priority:** P1 — AI creates custom widget configurations per service  
**Status:** 🟡 **PARTIAL** — button exists in frontend, backend endpoint may exist, full pipeline incomplete  
**Depends on:** `02_CONNECTOR_REGISTRY.md` ✅, `08_METRIC_WIDGETS.md` 🟡, `10_AI_CHATBOX.md` 🟡  
**Blocks:** Nothing

---

## What's Done

### Frontend
- [x] "AI Generate Widgets" button in `ServiceWidget.tsx` (lines 137-145)
- [x] Calls `POST /api/connectors/{id}/generate-widgets` with `resource_id` and prompt (lines 73-89)
- [x] Loading state — "Synthesizing..." with spinning sparkle icon
- [x] Stores generated layout in `customLayout` state
- [x] Shows confirmation badge: "AI synthesized custom widget configuration (N widgets active)"

### Backend (Per CHANGELOG)
- [x] `POST /api/connectors/{id}/generate-widgets` endpoint exists in `prash/server.py`
- [x] "Inspects live telemetry, metric names, and resource shapes to synthesize optimized custom SVG widget layouts"

## What's Remaining

### Phase A — Backend Widget Generator
- [ ] **A1. `prash/widget_generator.py`** — **FILE DOES NOT EXIST** — widget config dataclasses and generation logic not in a dedicated module
- [ ] **A4. Prompt builder** — verify the prompt uses real connector capabilities and metrics
- [ ] **A5. Response parser** — verify LLM JSON response parsing
- [ ] **A6. Validation** — verify invalid metric_keys/types are rejected
- [ ] **A7. Fallback chain** — AI → validate → template fallback if all invalid
- [ ] **A9. Cache generated configs** — save to `prash.yaml` per service

### Phase B — Frontend Widget Configurator (NOT STARTED)
- [ ] **B1. `WidgetConfigurator.tsx`** — UI for viewing and customizing widget layout
- [ ] **B4. Preview layout** — show generated widgets before confirming
- [ ] **B5. Manual override** — user can add/remove/reorder widgets
- [ ] **B6. Save layout** — persist widget config for this service

### Phase C — Integration (PARTIAL)
- [ ] **C1. Auto-generate on first watch** — not implemented
- [ ] **C2. ServiceWidget uses generated config** — currently the `customLayout` state is set but the rendering doesn't actually change based on it (lines 175-179 just show a badge, the widget grid stays hardcoded)
- [ ] **C3. Regenerate option** — button exists ✅

---

## Defects

> [!WARNING]
> **Generated layout not actually rendered**: When `customLayout` is set after the AI generates widgets, `ServiceWidget.tsx` only shows a text badge "AI synthesized custom widget configuration". The actual widget grid (lines 182-239) remains the **same hardcoded layout** (gauge → line chart → cards → timeline → grid). The generated config is stored but never used for rendering.

> [!NOTE]
> This feature depends heavily on Feature 08 being template-driven first. Once `ServiceWidget` renders from `widget_templates`, this feature can generate and inject custom templates.

---

## Files Required
- `prash/widget_generator.py` — **NEW** (generation logic may be inline in `server.py` currently)
- `desktop/src/components/WidgetConfigurator.tsx` — **NEW**
