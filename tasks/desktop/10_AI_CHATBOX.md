# Feature 10 — Per-Service AI Chatbox

**Priority:** P0 — AI-powered interaction, the "magic" moment  
**Owner:** TBD  
**Depends on:** `01_BACKEND_API_BRIDGE.md`, `08_METRIC_WIDGETS.md`, existing `prash/brain/` module  
**Target files:**  
- [`desktop/src/components/Chatbot.tsx`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/desktop/src/components/Chatbot.tsx) (rewrite)  
- `desktop/src/components/ChatMessage.tsx` (new)  
- `prash/server.py` — enhanced chat endpoint  
**Test file:** `desktop/src/__tests__/Chatbot.test.tsx` (new), `tests/test_chat_api.py` (new)

---

## Product Spec

Every service in a project has an AI chatbox. When you open chat from an AWS EC2 widget, the AI already knows:
- Which instance you're looking at
- Current CPU, memory, network metrics
- Recent events and alarms
- The instance's state and health

The user types natural language, and the AI responds with insights, diagnoses, and actionable recommendations — backed by real connector data.

### The Context Injection Flow

```
User clicks "Chat" on AWS EC2 widget (instance i-0abc123)
    │
    ▼
Frontend opens Chatbot with service_context:
  {connector_id: "aws", resource_id: "i-0abc123", display_name: "API Server"}
    │
    ▼
Frontend sends POST /api/chat {
    message: "Why is CPU so high?",
    service_context: {
        connector_id: "aws",
        resource_id: "i-0abc123"
    }
}
    │
    ▼
Backend:
  1. Fetches current metrics via AWSConnector.get_stats("i-0abc123")
  2. Fetches current state via AWSConnector.poll_state("i-0abc123")
  3. Fetches recent events (CloudWatch alarms, CloudTrail)
  4. Builds context string:
     "Instance i-0abc123 in us-east-1:
      State: running | CPU: 94.2% | Network In: 1.2 GB/s
      Recent: CPU spike 5 min ago, status check passed 2 min ago"
  5. Prepends context to user message
  6. Sends to DiagnosisAgent (brain module)
  7. Returns AI response with optional action recommendations
    │
    ▼
Frontend displays response with:
  - Text explanation
  - Optional "Execute Action" buttons
  - Optional code blocks for commands
```

### Chat UI Layout

```
┌────────────────────────────────────────────┐
│  💬 Lear AI — API Server (AWS EC2)         │
│  ● Online · Watching i-0abc123      [✕]    │
├────────────────────────────────────────────┤
│                                            │
│  ┌─ Lear ──────────────────────────────┐   │
│  │ I'm watching your EC2 instance      │   │
│  │ i-0abc123 in us-east-1.             │   │
│  │                                     │   │
│  │ Current status:                     │   │
│  │ • State: Running                    │   │
│  │ • CPU: 94.2% ⚠️                     │   │
│  │ • Network In: 1.2 GB/s             │   │
│  │ • Status Checks: Passing           │   │
│  │ • Active Alarms: 1 (HighCPU)       │   │
│  │                                     │   │
│  │ What would you like to investigate? │   │
│  └─────────────────────────────────────┘   │
│                                            │
│                    ┌─ You ──────────────┐   │
│                    │ Why is CPU so high?│   │
│                    └───────────────────┘   │
│                                            │
│  ┌─ Lear ──────────────────────────────┐   │
│  │ Based on the CloudWatch metrics and │   │
│  │ CloudTrail logs for i-0abc123:      │   │
│  │                                     │   │
│  │ The CPU spike started at 21:01 and  │   │
│  │ correlates with a 3x increase in    │   │
│  │ NetworkIn traffic. CloudTrail shows │   │
│  │ no scaling events or config changes.│   │
│  │                                     │   │
│  │ Likely cause: traffic spike.        │   │
│  │                                     │   │
│  │ Recommended actions:                │   │
│  │ ┌──────────────────────────────┐    │   │
│  │ │ 🔄 Restart the instance      │    │   │
│  │ │    Risk: SAFE · Auto-allowed  │    │   │
│  │ │    [Execute]                  │    │   │
│  │ └──────────────────────────────┘    │   │
│  │ ┌──────────────────────────────┐    │   │
│  │ │ 📈 Scale up (resize instance) │    │   │
│  │ │    Risk: APPROVAL · Needs OK  │    │   │
│  │ │    [Request Approval]         │    │   │
│  │ └──────────────────────────────┘    │   │
│  └─────────────────────────────────────┘   │
│                                            │
├────────────────────────────────────────────┤
│  [Ask Lear about this service...        →] │
└────────────────────────────────────────────┘
```

### Chat Features

1. **Context-aware greeting**: First message shows REAL current status from the connector
2. **Natural language input**: User types freely, backend uses intent parsing (existing `prash/intent.py`)
3. **Action recommendations**: AI suggests specific actions with risk tier badges
4. **Execute inline**: "Execute" button calls the action API directly, shows result
5. **Code blocks**: For commands, logs, and technical output — monospace with copy button
6. **Streaming responses**: SSE for long responses (not wait-for-full-response)
7. **Chat history**: Persisted per service within the session (not across restarts)
8. **Global chat**: Also accessible without service context (general Lear assistant)

### Message Types

```typescript
interface ChatMessage {
    id: string;
    sender: "user" | "agent";
    text: string;
    timestamp: string;
    // Optional enrichments:
    actions?: ActionRecommendation[];
    codeBlocks?: CodeBlock[];
    metrics?: MetricSnapshot[];
    isStreaming?: boolean;
}

interface ActionRecommendation {
    action_id: string;
    label: string;
    description: string;
    risk_tier: "SAFE" | "APPROVAL" | "NEVER";
    executable: boolean;
}

interface CodeBlock {
    language: string;
    code: string;
    copyable: boolean;
}
```

### Backend Chat Enhancement

The existing `POST /api/chat` endpoint is enhanced to:
1. Accept optional `service_context` with `connector_id` + `resource_id`
2. When context is provided, fetch REAL metrics/status/events from the connector
3. Build a context preamble string with actual data
4. Feed the full context + user message to the brain module
5. Parse the brain's response for action recommendations
6. Return structured response with text + actions + code blocks

---

## Detailed Task List

### Phase A — Backend Chat Enhancement

- [ ] **A1. Enhance `POST /api/chat`** — accept `service_context` parameter
- [ ] **A2. Context fetching** — when `service_context` is provided:
  - Call `connector.poll_state(resource_id)` for current state
  - Call `connector.get_stats(resource_id)` for recent metrics/events
  - Call `connector.fetch_logs(resource_id)` for recent log lines
- [ ] **A3. Context formatting** — build a structured context string:
  ```
  Service: AWS EC2 instance i-0abc123 (us-east-1)
  State: running
  Metrics: CPU=94.2%, NetworkIn=1.2GB/s, DiskReadOps=450/s
  Recent Events: CPU spike (5m ago), Status check passed (2m ago)
  Logs: [last 20 lines of relevant logs]
  ```
- [ ] **A4. Brain integration** — prepend context to the user message before sending to `DiagnosisAgent`
- [ ] **A5. Action parsing** — if the brain recommends an action, include it in the response with `action_id` and `risk_tier`
- [ ] **A6. SSE streaming endpoint** — `POST /api/chat/stream` that returns Server-Sent Events for streaming responses
- [ ] **A7. Action execution endpoint** — `POST /api/chat/execute` that executes a recommended action and returns the result

### Phase B — Frontend Chat Components

- [ ] **B1. Rewrite `Chatbot.tsx`** — accept `serviceContext` prop for scoped chat
- [ ] **B2. Create `ChatMessage.tsx`** — renders a single message with all enrichments
- [ ] **B3. Context-aware greeting** — on open, if service context provided, show a greeting with REAL current status
- [ ] **B4. Message rendering** — markdown support, code blocks with syntax highlighting and copy button
- [ ] **B5. Action recommendation cards** — render action suggestions with risk tier badge and execute button
- [ ] **B6. Execute button handler** — calls `POST /api/chat/execute`, shows result inline
- [ ] **B7. Streaming support** — render SSE tokens as they arrive, showing typing indicator
- [ ] **B8. Chat header** — shows service name, connector icon, watching status

### Phase C — Chat UX

- [ ] **C1. Auto-scroll** to latest message
- [ ] **C2. Message input** — auto-focus, enter to send, shift+enter for newline
- [ ] **C3. Loading indicator** — typing dots while AI is responding
- [ ] **C4. Error handling** — "Failed to get response" with retry button
- [ ] **C5. Empty state** — when no messages, show suggested questions based on the service type
- [ ] **C6. Chat panel positioning** — slide-in from right side, overlay on mobile-sized windows, panel on larger windows
- [ ] **C7. Chat history** — messages persist within the session per service

### Phase D — Global Chat

- [ ] **D1. Global chat mode** — accessible from the sidebar, no service context
- [ ] **D2. Service switching** — user can type "@aws" or "@kubernetes" to add service context mid-conversation
- [ ] **D3. Multi-service context** — chat can reference data from multiple services when asked

---

## Testing Methodology

### Unit Tests

```
# Backend
test_chat_without_context_uses_general_brain
test_chat_with_context_fetches_connector_data
test_chat_context_includes_real_poll_state
test_chat_context_includes_real_get_stats
test_chat_context_includes_real_fetch_logs
test_chat_formats_context_string_correctly
test_chat_returns_action_recommendations
test_chat_action_execute_calls_dispatcher
test_chat_handles_connector_not_configured
test_chat_handles_brain_error_gracefully

# Frontend
test_chatbot_opens_with_service_context
test_chatbot_greeting_shows_real_status
test_chatbot_sends_message_to_api
test_chatbot_renders_text_response
test_chatbot_renders_code_blocks
test_chatbot_renders_action_cards
test_chatbot_execute_button_calls_api
test_chatbot_shows_loading_indicator
test_chatbot_shows_error_on_api_failure
test_chatbot_auto_scrolls_to_bottom
test_chatbot_persists_history_per_service
test_chatbot_empty_state_shows_suggestions
```

### Anti-Hardcoding Test Suite

```
test_NO_HARDCODED_GREETING — The initial greeting message contains 
    REAL metrics from the connector, not static text. Connect to a 
    service with known CPU=34.5%, verify the greeting shows "34.5%", 
    not a hardcoded value.

test_NO_HARDCODED_CONTEXT — The context string sent to the brain 
    contains actual connector data, not placeholder values. Mock the 
    connector to return specific metrics and verify those exact values 
    appear in the context.

test_NO_HARDCODED_SUGGESTIONS — Suggested questions in the empty state 
    are service-type-specific (from the registry), not a fixed list for 
    all services.

test_NO_HARDCODED_RESPONSES — The AI response comes from the actual 
    brain module / LLM call, not from a switch/case that returns 
    canned responses based on keywords.

test_NO_DEMO_RESPONSES — There is no "demo mode" that returns 
    pre-written responses instead of calling the brain.

test_ACTIONS_FROM_BRAIN — Action recommendations come from the brain's 
    diagnosis output, not from hardcoded suggestions based on 
    connector type.

test_CONTEXT_REFRESHES — If the user chats again after 5 minutes, the 
    context is re-fetched from the connector (not cached from the first 
    message). Metrics may have changed.

test_ERROR_IS_REAL — If the brain API call fails, the error message 
    shown to the user is the real error, not "I'm having trouble 
    thinking right now" or similar cute placeholder.
```

### Integration Tests

```
test_CHAT_WITH_AWS_CONTEXT — Connect AWS → open chat on EC2 instance → 
    verify greeting contains real instance state → ask about CPU → 
    verify response references real metrics

test_CHAT_ACTION_FLOW — Get AI recommendation → click Execute → verify 
    action runs → verify result shown in chat

test_CHAT_WITHOUT_CONTEXT — Open global chat → ask general question → 
    verify response (no connector context needed)

test_CHAT_SERVICE_SWITCH — Open chat on AWS → switch to K8s service → 
    verify context updates to K8s data
```

---

## Definition of Done

- [ ] Chat opens with REAL service status as greeting (from connector data)
- [ ] User messages include real connector context when service is scoped
- [ ] AI responses come from the actual brain module, not canned responses
- [ ] Action recommendations rendered with risk tier badges and execute buttons
- [ ] Execute button runs real actions and shows real results
- [ ] Code blocks render with syntax highlighting and copy button
- [ ] Loading/error/empty states handled gracefully
- [ ] Chat works without service context (global mode)
- [ ] Zero hardcoded responses, greetings, or suggestions
- [ ] Anti-hardcoding tests all pass
