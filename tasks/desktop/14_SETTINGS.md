# Feature 14 — Settings & Configuration 🟡 PARTIALLY DONE

**Priority:** P2 — preferences and management  
**Status:** 🟡 **PARTIAL** — UI exists but save is fake, config not from API  
**Depends on:** `01_BACKEND_API_BRIDGE.md` ✅  
**Blocks:** Nothing

---

## What's Done

- [x] **A1. `Settings.tsx` exists** — model selector + permission mode sections
- [x] **A2. AI provider section** — 3 model options with card selection
- [x] **A7. Re-run Wizard** — "Launch Wizard" button calls `onReconfigure()` (lines 31-38)
- [x] Permission mode section — Ask First / Auto-Safe / Bypass radio options
- [x] Design system styling — glass-card, accent colors consistent

## What's Remaining

### 🔴 Critical Fixes
- [ ] **FIX: Save button is fake** — Lines 9-11: `handleSave` just sets `saved=true` for 2 seconds. No API call, no persistence. Must call `POST /api/settings` or `POST /api/config`.
- [ ] **FIX: Model options are hardcoded** — Lines 52-56: `deepseek-v4-flash`, `kimi-k2.6`, `gemini-1.5-pro` are static strings. Should be fetched from API or config.

### Missing Sections
- [ ] **A3. Watcher settings** — poll interval selector, retention period, notification toggles
- [ ] **A4. Credential overview** — display all `.env` values masked from `GET /api/config`
- [ ] **A5. About section** — version from `package.json`, connector count from API (not hardcoded "13")
- [ ] **A6. Save settings** — persist to `.env` or `prash.yaml` via real API call

---

## Defects

> [!CAUTION]
> **FAKE SAVE**: The save button does absolutely nothing. It flashes "Preferences Saved!" after a 2s timeout then resets. No data is persisted anywhere. Users think their settings are saved but nothing changes.

> [!WARNING]
> **HARDCODED MODEL LIST**: The model options are defined inline in the component (lines 52-56). If new models are added to the backend, the Settings page won't show them without code changes.

> [!NOTE]
> The permission mode selection is also not persisted. It resets to "ask" on page reload.
