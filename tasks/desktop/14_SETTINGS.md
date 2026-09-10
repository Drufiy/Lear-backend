# Feature 14 — Settings & Configuration

**Priority:** P2 — preferences and management  
**Owner:** TBD  
**Depends on:** `01_BACKEND_API_BRIDGE.md`  
**Target file:** [`desktop/src/components/Settings.tsx`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/desktop/src/components/Settings.tsx) (rewrite)  
**Test file:** `desktop/src/__tests__/Settings.test.tsx` (new)

---

## Product Spec

Settings page for managing Lear's configuration — credentials, AI provider, polling intervals, notification preferences, and about/version info.

### Sections

#### 1. AI Provider Configuration
```
┌── AI Provider ──────────────────────────┐
│  Provider: [DeepSeek ▾]                 │
│  API Key: [●●●●●●●●●●●●●●●●  👁]       │
│  Model: [deepseek-chat ▾]              │
│  Status: ● Connected                    │
│  [Test Connection]  [Save]              │
└─────────────────────────────────────────┘
```

#### 2. Watcher Settings
```
┌── Watcher Configuration ───────────────┐
│  Default poll interval: [30s ▾]         │
│  Event retention: [7 days ▾]            │
│  Notification sound: [✓ Enabled]       │
│  Auto-start watches on launch: [✓]      │
└─────────────────────────────────────────┘
```

#### 3. Credential Overview
```
┌── Configured Credentials ──────────────┐
│  AWS_ACCESS_KEY_ID:     AKI...789       │
│  AWS_SECRET_ACCESS_KEY: ●●●●●●●...key  │
│  GITHUB_TOKEN:          ghp...abc       │
│  DEEPSEEK_API_KEY:      sk-...xyz       │
│                                         │
│  [Open .env file]  [Re-run Wizard]      │
└─────────────────────────────────────────┘
```

#### 4. About
```
┌── About Lear ──────────────────────────┐
│  Version: 0.2.0                         │
│  Backend: FastAPI (Python 3.12)         │
│  Connectors: 13 available, 4 configured │
│  Data storage: Local only (.env)        │
│  Credentials: Never leave this machine  │
│                                         │
│  Built by Drufiy · drufiy.com           │
└─────────────────────────────────────────┘
```

---

## Detailed Task List

- [ ] **A1. Rewrite Settings.tsx** — remove hardcoded config
- [ ] **A2. AI provider section** — dropdown for provider, API key input (masked), test connection button
- [ ] **A3. Watcher settings** — poll interval selector, retention period, notification toggles
- [ ] **A4. Credential overview** — display all `.env` values masked, "Open .env" button
- [ ] **A5. About section** — version from `package.json`, connector count from API
- [ ] **A6. Save settings** — persist to `.env` or `prash.yaml` as appropriate
- [ ] **A7. Re-run Wizard** — button to return to the setup wizard

---

## Testing Methodology

### Anti-Hardcoding Test Suite

```
test_NO_HARDCODED_CREDENTIALS — Credential list comes from the API's 
    masked config, not from hardcoded env var names.

test_NO_HARDCODED_VERSION — Version comes from package.json or API, 
    not from a string in the component.

test_NO_HARDCODED_CONNECTOR_COUNT — "13 available, 4 configured" 
    counts from the API, not hardcoded numbers.

test_CREDENTIALS_ALWAYS_MASKED — No credential value displayed 
    unmasked in the settings UI.
```

---

## Definition of Done

- [ ] All settings reflect REAL configuration state
- [ ] Credential display always masked
- [ ] AI provider connection testable from UI
- [ ] Version and connector count from API
