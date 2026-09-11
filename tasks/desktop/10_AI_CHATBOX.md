# Feature 10 — Per-Service AI Chatbox 🟡 PARTIALLY DONE

**Priority:** P0 — AI-powered interaction, the "magic" moment  
**Status:** 🟡 **PARTIAL** — chat UI exists with service context, but greeting is hardcoded and execute is fake  
**Depends on:** `01_BACKEND_API_BRIDGE.md` ✅, `08_METRIC_WIDGETS.md` 🟡, existing `prash/brain/`  
**Blocks:** `16_AI_WIDGET_GENERATION.md`

---

## What's Done

### Phase B — Frontend Chat Components (PARTIAL)
- [x] **B1. `Chatbot.tsx`** — slide-in panel with AnimatePresence, accepts `serviceContext` prop
- [x] **B2. Service context chip** — shows `connectorId / resourceId` badge when context active (lines 142-149)
- [x] **B5. Action recommendation rendering** — shows command with execute button (lines 169-188)
- [x] **B8. Chat header** — shows "Lear Copilot" + "Telemetry Context Active" status
- [x] Message input with Enter-to-send (line 209)
- [x] Auto-scroll to latest message (lines 36-38)
- [x] Loading indicator — "Lear is analyzing live metrics..." (lines 192-196)

### Backend
- [x] `POST /api/chat` called with `message` + `service_context` (lines 50-62)
- [x] Response rendered with text, command, executable flag (lines 65-75)

## What's Remaining

### 🔴 Critical Fixes
- [ ] **FIX: Hardcoded greeting** — Line 29: `"Hello! I am Lear Copilot. I analyze your live infrastructure telemetry..."` is a static string. Per spec, the greeting must contain **REAL current metrics** from the connector (CPU, state, etc.)
- [ ] **FIX: `handleExecuteAction` is fake** — Lines 86-99: It locally marks the message as "executed" and appends a fake audit message `"Command executed: \`prash ...\`. Telemetry updated."` It never calls `POST /api/chat/execute` or any real action endpoint
- [ ] **FIX: Error message is generic** — Line 79: `"Error connecting to the Lear reasoning engine."` instead of the real error from the backend

### Phase A — Backend Chat Enhancement (PARTIAL)
- [x] **A1. `POST /api/chat`** accepts `service_context` — confirmed via frontend code
- [ ] **A6. SSE streaming endpoint** — `POST /api/chat/stream` — not implemented
- [ ] **A7. Action execution endpoint** — `POST /api/chat/execute` — not implemented

### Phase B — Frontend (remaining)
- [ ] **B2. `ChatMessage.tsx`** component — currently messages rendered inline
- [ ] **B3. Context-aware greeting** — must fetch real status from connector on open
- [ ] **B4. Markdown + code blocks** with syntax highlighting and copy button
- [ ] **B6. Execute button handler** — must call real backend endpoint
- [ ] **B7. Streaming support** — SSE rendering

### Phase C — Chat UX (PARTIAL)
- [x] **C1. Auto-scroll** ✅
- [x] **C2. Message input** — enter to send ✅
- [x] **C3. Loading indicator** ✅
- [ ] **C4. Error handling** — show real error, not generic text
- [ ] **C5. Empty state** — suggested questions based on service type
- [x] **C6. Chat panel positioning** — slide-in from right ✅
- [ ] **C7. Chat history** — messages reset on close (not persisted per service)

### Phase D — Global Chat (NOT STARTED)
- [ ] **D1-D3** — Service switching via `@aws`, multi-service context

---

## Defects

> [!CAUTION]
> **FAKE EXECUTE**: `handleExecuteAction` (line 86) is a no-op that fabricates an audit trail message without calling any backend endpoint. Users see "Action Dispatched" but nothing actually happens.

> [!CAUTION]
> **HARDCODED GREETING**: The initial message is a static string, not derived from real connector state. The spec requires showing live CPU %, state, network metrics in the first message.

> [!WARNING]
> **GENERIC ERROR**: When `fetch('/api/chat')` fails, the error says "Error connecting to the Lear reasoning engine" — a canned message, not the real error.

---

## Files Required
- `desktop/src/components/ChatMessage.tsx` — **NEW**
