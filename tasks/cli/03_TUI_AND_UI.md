# TUI & UI — `tui.py`, `ui.py`, `fix.py` (rendering)

**Owner:** Aryan  
**Status:** Built  
**Priority:** Tier 2  

---

## Tasks

### T1. Diagnosis rendering (`fix.py`)
- [ ] `render_diagnosis()` — formatted diagnosis with confidence, category, explanation
- [ ] `render_options()` — ranked menu with per-option rationale, default marked
- [ ] Color-coded severity: critical (red), warning (yellow), info (blue)
- [ ] `--noninteractive` renders without prompts

### T2. TUI panels (`tui.py`)
- [ ] Action list with risk tier badges
- [ ] Audit log viewer with filtering
- [ ] Circuit breaker status display
- [ ] Configuration overview
- [ ] Watcher status panel

### T3. Rich formatting (`ui.py`)
- [ ] `rich` library for formatted CLI output
- [ ] Tables, panels, progress bars, spinners
- [ ] Cross-platform ANSI color support
- [ ] cp1252 console safety (Windows legacy consoles)

### T4. Desktop API bridge compatibility
- [ ] TUI output doesn't break when called from desktop API
- [ ] stdout/stderr capture works for `POST /api/chat/execute`
- [ ] No interactive prompts in API-called paths

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_render_diagnosis` | `tests/test_fix.py` | Diagnosis formatting correct |
| `test_render_options` | `tests/test_fix.py` | Options menu formatted |
| `test_tui_action_list` | `tests/test_tui.py` | Actions displayed with tiers |
| `test_console_encoding` | `tests/test_tui.py` | cp1252 safety |
| `test_api_capture` | `tests/test_desktop_api.py` | stdout capture for API |

---

## Acceptance Criteria

- [ ] All TUI panels render correctly on both platforms
- [ ] cp1252 console safety for Windows
- [ ] Desktop API can capture TUI output
