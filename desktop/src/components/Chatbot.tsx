import { useState, useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Send, Sparkles, Trash2, ArrowRight, ShieldAlert, RefreshCw } from 'lucide-react';
import ChatMessage, { ChatMessageData } from './ChatMessage';
import { ChatContextType } from '../context/LearContext';

interface ChatbotProps {
  isOpen: boolean;
  onClose: () => void;
  serviceContext?: ChatContextType | null;
}

export default function Chatbot({ isOpen, onClose, serviceContext }: ChatbotProps) {
  const [messages, setMessages] = useState<ChatMessageData[]>([]);
  const [suggestedPrompts, setSuggestedPrompts] = useState<string[]>([]);
  const [activeContext, setActiveContext] = useState<ChatContextType | null>(
    serviceContext || null
  );
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [executingActionId, setExecutingActionId] = useState<number | null>(null);
  const [channelMode, setChannelMode] = useState<'dashboard' | 'slack' | 'email'>('dashboard');
  const [pollingEmail, setPollingEmail] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Sync activeContext with serviceContext prop updates
  useEffect(() => {
    setActiveContext(serviceContext || null);
  }, [serviceContext]);

  // Auto-scroll to bottom on messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  // Load context-aware dynamic greeting whenever opened without incident
  const loadGreeting = useCallback(async (ctx: ChatContextType | null) => {
    try {
      let url = '/api/chat/greeting';
      const params = new URLSearchParams();
      if (ctx?.connectorId) params.append('connector_id', ctx.connectorId);
      if (ctx?.resourceId) params.append('resource_id', ctx.resourceId);
      if (Array.from(params.keys()).length > 0) {
        url += `?${params.toString()}`;
      }

      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        const greetingMsg: ChatMessageData = {
          id: Date.now(),
          sender: 'agent',
          text: data.greeting || 'Hello! I am Lear. How can I assist your operational workflow?',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        };
        setMessages([greetingMsg]);
        if (data.suggested_prompts && Array.isArray(data.suggested_prompts)) {
          setSuggestedPrompts(data.suggested_prompts);
        }
      } else {
        const errText = await res.text();
        setMessages([
          {
            id: Date.now(),
            sender: 'agent',
            text: `Lear active. (Bridge notice: ${errText || 'default telemetry loaded'})`,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
        ]);
      }
    } catch (e: any) {
      setMessages([
        {
          id: Date.now(),
          sender: 'agent',
          text: `Lear active. Could not reach backend greeting: ${e?.message || String(e)}`,
          isError: true,
        },
      ]);
    }
  }, []);

  // Load dedicated incident thread and conversation history
  const loadIncidentSession = useCallback(async (ctx: ChatContextType) => {
    setLoading(true);
    try {
      let inc: any = null;
      if (ctx.incidentId) {
        const res = await fetch(`/api/incident/${ctx.incidentId}`);
        if (res.ok) {
          const d = await res.json();
          inc = d.incident;
        }
      }

      if (inc && inc.conversation && inc.conversation.length > 0) {
        const formatted: ChatMessageData[] = inc.conversation.map((c: any, i: number) => {
          let prefix = '';
          const sLower = (c.sender || '').toLowerCase();
          if (sLower.includes('slack')) {
            prefix = '💬 [Slack] ';
          } else if (sLower.includes('email')) {
            prefix = '✉️ [Email] ';
          }
          return {
            id: i + 1,
            sender: c.sender === 'Lear SRE Copilot' ? 'agent' : 'user',
            text: prefix + c.message,
            timestamp: c.timestamp || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          };
        });
        setMessages(formatted);
        const lastMsg = inc.conversation[inc.conversation.length - 1];
        if (lastMsg && lastMsg.quick_replies) {
          setSuggestedPrompts(lastMsg.quick_replies);
        } else {
          setSuggestedPrompts(['Approve & Deploy Fix', 'Deny / Halt Changes', 'Show Live Pod Crash Logs']);
        }
      } else {
        // Synthesize comprehensive incident context
        let richText = `🚨 **${ctx.title || 'Critical Incident Detected'}**\n\n`;
        if (ctx.diagnosis) richText += `**Diagnosis:**\n${ctx.diagnosis}\n\n`;
        if (ctx.errorSummary) richText += `**Error Details:**\n\`\`\`\n${ctx.errorSummary}\n\`\`\`\n\n`;
        if (ctx.agentThinking && ctx.agentThinking.length > 0) {
          richText += `**Agent Reasoning & Investigation:**\n`;
          ctx.agentThinking.forEach((step, idx) => {
            richText += `• **Phase ${idx + 1}:** ${step}\n`;
          });
          richText += '\n';
        }
        richText += `🧠 **Episodic Memory Match:**\nCorrelated pattern with prior cluster recovery episodes.\n\n`;
        richText += `Standing by for your authorization. Type **Approve** to execute remediation.`;

        setMessages([
          {
            id: Date.now(),
            sender: 'agent',
            text: richText,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
        ]);
        setSuggestedPrompts(['Approve & Deploy Fix', 'Deny / Halt Changes', 'Show Live Pod Crash Logs']);
      }
    } catch (e: any) {
      setMessages([
        {
          id: Date.now(),
          sender: 'agent',
          text: `Loaded incident context for ${ctx.title || ctx.incidentId}. Standing by for instructions.`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Check Gmail IMAP inbox immediately on demand
  const handlePollEmailNow = async () => {
    setPollingEmail(true);
    try {
      const res = await fetch('/api/email/poll-now', { method: 'POST' });
      if (res.ok) {
        if (activeContext?.incidentId) {
          await loadIncidentSession(activeContext);
        }
      }
    } catch (e) {
      console.error(e);
    } finally {
      setPollingEmail(false);
    }
  };

  // Fetch greeting or load incident when drawer opens
  useEffect(() => {
    if (isOpen) {
      if (activeContext?.incidentId) {
        loadIncidentSession(activeContext);
      } else {
        loadGreeting(activeContext);
      }
    }
  }, [isOpen, activeContext, loadGreeting, loadIncidentSession]);

  // Send message handler with SSE streaming support and fallback
  const handleSend = async (overridePrompt?: string) => {
    const rawText = overridePrompt || input;
    if (!rawText.trim() || loading) return;

    let targetText = rawText.trim();
    let currentCtx = activeContext;

    // Check for @connector mention prefix (e.g. "@aws Why is it slow?")
    const mentionMatch = targetText.match(/^@([a-zA-Z0-9_-]+)\s*(.*)$/);
    if (mentionMatch) {
      const mentionedConnector = mentionMatch[1].toLowerCase();
      targetText = mentionMatch[2] || 'Check status and metrics';
      currentCtx = { connectorId: mentionedConnector, resourceId: '' };
      setActiveContext(currentCtx);
    }

    const userMsg: ChatMessageData = {
      id: Date.now(),
      sender: 'user',
      text: (channelMode !== 'dashboard' ? `[Sent via ${channelMode.toUpperCase()}] ` : '') + (overridePrompt || input.trim()),
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages(prev => [...prev, userMsg]);
    if (!overridePrompt) setInput('');
    setLoading(true);

    const streamMsgId = Date.now() + 1;

    // 1. If sending via Slack Channel
    if (channelMode === 'slack') {
      try {
        const chatRes = await fetch('/api/slack/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: targetText,
            incident_id: currentCtx?.incidentId,
            user_name: 'Engineer'
          }),
        });
        if (chatRes.ok) {
          const chatData = await chatRes.json();
          const copilotReply = chatData.copilot_reply || 'Dispatched to Slack webhook.';
          setMessages(prev => [
            ...prev,
            {
              id: streamMsgId,
              sender: 'agent',
              text: `💬 **[Slack Response via Webhook]**\n\n${copilotReply}`,
              timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            },
          ]);
          setLoading(false);
          return;
        }
      } catch (err: any) {
        setMessages(prev => [
          ...prev,
          {
            id: streamMsgId,
            sender: 'agent',
            text: `Slack Dispatch Error: ${err?.message || err}`,
            isError: true,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
        ]);
        setLoading(false);
        return;
      }
    }

    // 2. If sending via Email (Gmail)
    if (channelMode === 'email') {
      try {
        const chatRes = await fetch('/api/email/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: targetText,
            incident_id: currentCtx?.incidentId,
            from_email: 'anantacharya5568@gmail.com'
          }),
        });
        if (chatRes.ok) {
          const chatData = await chatRes.json();
          const copilotReply = chatData.copilot_reply || 'Dispatched via Gmail SMTP.';
          setMessages(prev => [
            ...prev,
            {
              id: streamMsgId,
              sender: 'agent',
              text: `✉️ **[Email SMTP Response to anantacharya5568@gmail.com]**\n\n${copilotReply}`,
              timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            },
          ]);
          setLoading(false);
          return;
        }
      } catch (err: any) {
        setMessages(prev => [
          ...prev,
          {
            id: streamMsgId,
            sender: 'agent',
            text: `Email Dispatch Error: ${err?.message || err}`,
            isError: true,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
        ]);
        setLoading(false);
        return;
      }
    }

    // 3. If in an incident session on Dashboard, route message directly to the incident war room brain
    if (currentCtx?.incidentId) {
      try {
        const chatRes = await fetch(`/api/incident/${currentCtx.incidentId}/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: targetText }),
        });
        if (chatRes.ok) {
          const chatData = await chatRes.json();
          const copilotReply = chatData.copilot_reply || 'Remediation updated.';
          const lastMsg = chatData.incident?.conversation?.slice(-1)[0];
          setMessages(prev => [
            ...prev,
            {
              id: streamMsgId,
              sender: 'agent',
              text: copilotReply,
              timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            },
          ]);
          if (lastMsg?.quick_replies) {
            setSuggestedPrompts(lastMsg.quick_replies);
          }
          setLoading(false);
          return;
        }
      } catch (err: any) {
        setMessages(prev => [
          ...prev,
          {
            id: streamMsgId,
            sender: 'agent',
            text: `Incident War Room Error: ${err?.message || err}`,
            isError: true,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
        ]);
        setLoading(false);
      }
    }

    try {
      // 2. Try SSE streaming endpoint for normal copilot queries
      const streamRes = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: targetText,
          service_context: currentCtx ? {
            connector_id: currentCtx.connectorId,
            resource_id: currentCtx.resourceId,
          } : undefined,
        }),
      });

      if (streamRes.ok && streamRes.body) {
        // Prepare empty placeholder agent message with streaming cursor
        setMessages(prev => [
          ...prev,
          {
            id: streamMsgId,
            sender: 'agent',
            text: '',
            streaming: true,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
        ]);

        const reader = streamRes.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let accumulatedText = '';
        let streamDone = false;

        while (!streamDone) {
          const { value, done } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed.startsWith('data: ')) {
              const dataStr = trimmed.substring(6);
              try {
                const parsed = JSON.parse(dataStr);
                if (parsed.token) {
                  accumulatedText += parsed.token;
                  setMessages(prev =>
                    prev.map(m =>
                      m.id === streamMsgId
                        ? { ...m, text: accumulatedText }
                        : m
                    )
                  );
                }

                if (parsed.done) {
                  streamDone = true;
                  setMessages(prev =>
                    prev.map(m =>
                      m.id === streamMsgId
                        ? {
                            ...m,
                            text: parsed.text || accumulatedText,
                            streaming: false,
                            command: parsed.command,
                            actionRequired: parsed.actionRequired,
                            executable: parsed.executable,
                            isError: Boolean(parsed.error),
                          }
                        : m
                    )
                  );
                }
              } catch {
                // Ignore parse error on partial JSON
              }
            }
          }
        }
      } else {
        // Fallback to static chat endpoint
        const staticRes = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: targetText,
            service_context: currentCtx ? {
              connector_id: currentCtx.connectorId,
              resource_id: currentCtx.resourceId,
            } : undefined,
          }),
        });

        if (staticRes.ok) {
          const data = await staticRes.json();
          setMessages(prev => [
            ...prev,
            {
              id: streamMsgId,
              sender: 'agent',
              text: data.reply || data.message || 'Analysis complete.',
              command: data.command,
              actionRequired: data.action_required,
              executable: data.executable,
              timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            },
          ]);
        } else {
          const errData = await staticRes.text();
          setMessages(prev => [
            ...prev,
            {
              id: streamMsgId,
              sender: 'agent',
              text: `Bridge Error: ${errData || 'Could not communicate with backend engine.'}`,
              isError: true,
              timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            },
          ]);
        }
      }
    } catch (e: any) {
      setMessages(prev => [
        ...prev,
        {
          id: streamMsgId,
          sender: 'agent',
          text: `Bridge Exception: ${e?.message || 'Error connecting to the Lear reasoning engine.'}`,
          isError: true,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  // Real action execution handler
  const handleExecuteAction = async (msgId: number, command?: string[]) => {
    if (!command || command.length === 0) return;
    setExecutingActionId(msgId);

    try {
      const res = await fetch('/api/chat/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          command,
          action_id: command[0] || 'action',
          service_context: activeContext ? {
            connector_id: activeContext.connectorId,
            resource_id: activeContext.resourceId,
          } : undefined,
        }),
      });

      let data: any = {};
      try {
        data = await res.json();
      } catch {
        data = { success: false, output: await res.text() };
      }

      if (!res.ok) {
        throw new Error(data.detail || data.message || `HTTP ${res.status}`);
      }

      setMessages(prev =>
        prev.map(m => (m.id === msgId ? { ...m, executed: true } : m))
      );

      const resultText = data.success
        ? `Execution succeeded for \`prash ${command.join(' ')}\`:\n\n\`\`\`text\n${data.output || 'Action completed successfully.'}\n\`\`\``
        : `Execution failed for \`prash ${command.join(' ')}\` (exit code ${data.exit_code}):\n\n\`\`\`text\n${data.output || 'Action execution returned an error.'}\n\`\`\``;

      setMessages(prev => [
        ...prev,
        {
          id: Date.now(),
          sender: 'agent',
          text: resultText,
          isError: !data.success,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } catch (e: any) {
      setMessages(prev => [
        ...prev,
        {
          id: Date.now(),
          sender: 'agent',
          text: `Action Pipeline Error: ${e?.message || String(e)}`,
          isError: true,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      setExecutingActionId(null);
    }
  };

  // Clear chat history
  const handleClearChat = () => {
    if (activeContext?.incidentId) {
      loadIncidentSession(activeContext);
    } else {
      loadGreeting(activeContext);
    }
  };

  // Switch to global context
  const handleClearContext = () => {
    setActiveContext(null);
    loadGreeting(null);
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/60 z-40 backdrop-blur-sm"
          />

          {/* Drawer */}
          <motion.div
            initial={{ x: '100%', opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: '100%', opacity: 0 }}
            transition={{ type: 'spring', bounce: 0, duration: 0.35 }}
            className="fixed right-0 top-0 bottom-0 w-full max-w-lg bg-[#080B11] border-l border-border-subtle z-50 flex flex-col shadow-2xl"
          >
            {/* Header */}
            <div className="p-4 border-b border-border-subtle bg-surface/40 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className={`p-2.5 rounded-xl border shadow-sm ${
                  activeContext?.incidentId 
                    ? 'bg-rose-500/15 text-rose-400 border-rose-500/30' 
                    : 'bg-accent/15 text-accent border-accent/25'
                }`}>
                  {activeContext?.incidentId ? <ShieldAlert size={18} /> : <Sparkles size={18} />}
                </div>
                <div>
                  <h3 className="font-bold text-base text-white">Lear</h3>
                  <p className={`text-[11px] flex items-center gap-1.5 font-mono ${
                    activeContext?.incidentId ? 'text-rose-400 font-bold' : 'text-accent'
                  }`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${
                      activeContext?.incidentId ? 'bg-rose-400' : 'bg-accent'
                    }`} />
                    {activeContext?.incidentId 
                      ? 'Incident War Room Active' 
                      : activeContext?.connectorId 
                      ? 'Telemetry Context Active' 
                      : 'Global Infrastructure SRE'}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={handleClearChat}
                  title="Reload context / reset"
                  className="p-1.5 text-gray-400 hover:text-white rounded-lg hover:bg-surface transition-colors cursor-pointer"
                >
                  <Trash2 size={16} />
                </button>
                <button
                  onClick={onClose}
                  className="p-1.5 text-gray-400 hover:text-white rounded-lg hover:bg-surface transition-colors cursor-pointer"
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            {/* Live Omni-Channel Status Bar */}
            <div className="px-4 py-1.5 bg-[#070A10] border-b border-border-subtle/40 flex items-center justify-between text-[10px]">
              <div className="flex items-center gap-2">
                <span className="text-gray-500 font-mono">LIVE CHANNELS:</span>
                <span className="flex items-center gap-1 text-emerald-400 font-medium">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  Slack
                </span>
                <span className="text-gray-700">•</span>
                <span className="flex items-center gap-1 text-emerald-400 font-medium">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  Email (IMAP/SMTP)
                </span>
              </div>
              <span className="text-[10px] text-accent/80 font-mono">2-way sync</span>
            </div>

            {/* Context Header */}
            {activeContext?.incidentId ? (
              <div className="px-4 py-2.5 bg-rose-500/15 border-b border-rose-500/30 flex items-center justify-between text-xs">
                <div className="flex items-center gap-2 overflow-hidden">
                  <span className="px-2 py-0.5 rounded bg-rose-500/25 text-rose-300 font-mono font-bold text-[10px] border border-rose-500/40 shrink-0 uppercase">
                    {activeContext.severity || 'CRITICAL'}
                  </span>
                  <span className="text-gray-200 font-semibold truncate text-[11px]">
                    {activeContext.title || activeContext.incidentId}
                  </span>
                </div>
                <button
                  onClick={handleClearContext}
                  className="text-[10px] text-gray-400 hover:text-white shrink-0 ml-2 underline cursor-pointer"
                >
                  Exit Incident
                </button>
              </div>
            ) : activeContext?.connectorId ? (
              <div className="px-5 py-2 bg-surface/70 border-b border-border-subtle flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <span className="text-gray-400">Context:</span>
                  <span className="px-2 py-0.5 rounded bg-accent/15 text-accent font-mono font-bold text-[11px] border border-accent/20">
                    {activeContext.connectorId.toUpperCase()}
                    {activeContext.resourceId ? ` / ${activeContext.resourceId}` : ''}
                  </span>
                </div>
                <button
                  onClick={handleClearContext}
                  className="text-[11px] text-gray-400 hover:text-white flex items-center gap-1 transition-colors cursor-pointer font-medium"
                >
                  Switch to Global
                </button>
              </div>
            ) : (
              <div className="px-5 py-2 bg-surface/70 border-b border-border-subtle flex items-center justify-between text-xs text-gray-400">
                <span>Scope: <strong className="text-gray-200">Global</strong> (Use <code className="text-accent text-[10px]">@connector</code> to scope)</span>
              </div>
            )}

            {/* Message Feed */}
            <div className="flex-1 overflow-y-auto p-5 space-y-4">
              {messages.map(msg => (
                <ChatMessage
                  key={msg.id}
                  message={msg}
                  isExecuting={executingActionId === msg.id}
                  onExecute={handleExecuteAction}
                />
              ))}

              {loading && (
                <div className="flex items-center gap-2 text-xs text-gray-400 font-mono animate-pulse">
                  <span className="w-1.5 h-1.5 rounded-full bg-accent animate-ping" />
                  Lear is analyzing live metrics & reasoning...
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Suggested Prompt & Action Chips */}
            {suggestedPrompts.length > 0 && (
              <div className="px-4 py-2 bg-[#090D15] border-t border-border-subtle/50 flex flex-col gap-1.5">
                <span className="text-[10px] uppercase font-bold tracking-wider text-gray-400">
                  {activeContext?.incidentId ? '⚡ Quick Actions & Decisions' : 'Suggested Questions'}
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {suggestedPrompts.map((prompt, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleSend(prompt)}
                      disabled={loading}
                      className={`flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded-lg border transition-all text-left cursor-pointer disabled:opacity-50 ${
                        prompt.toLowerCase().includes('approve') || prompt.toLowerCase().includes('fix')
                          ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/25 font-bold'
                          : prompt.toLowerCase().includes('deny') || prompt.toLowerCase().includes('halt')
                          ? 'bg-rose-500/15 border-rose-500/40 text-rose-300 hover:bg-rose-500/25 font-medium'
                          : 'bg-surface hover:bg-surface/80 border-border-subtle hover:border-accent/40 text-gray-300 hover:text-white'
                      }`}
                    >
                      <span>{prompt}</span>
                      <ArrowRight size={10} className="shrink-0 opacity-70" />
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Channel Dispatch Selector & Inbox Poller */}
            <div className="flex items-center justify-between px-4 py-1.5 bg-[#090D15] border-t border-border-subtle/50 text-[11px]">
              <div className="flex items-center gap-1.5">
                <span className="text-gray-500 font-mono text-[10px]">ROUTE:</span>
                <button
                  type="button"
                  onClick={() => setChannelMode('dashboard')}
                  className={`px-2 py-0.5 rounded text-[10px] font-medium transition-all cursor-pointer ${
                    channelMode === 'dashboard'
                      ? 'bg-accent/20 text-accent border border-accent/40 font-bold'
                      : 'text-gray-400 hover:text-white border border-transparent'
                  }`}
                >
                  Dashboard
                </button>
                <button
                  type="button"
                  onClick={() => setChannelMode('slack')}
                  className={`px-2 py-0.5 rounded text-[10px] font-medium transition-all cursor-pointer ${
                    channelMode === 'slack'
                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-bold'
                      : 'text-gray-400 hover:text-white border border-transparent'
                  }`}
                >
                  💬 Slack
                </button>
                <button
                  type="button"
                  onClick={() => setChannelMode('email')}
                  className={`px-2 py-0.5 rounded text-[10px] font-medium transition-all cursor-pointer ${
                    channelMode === 'email'
                      ? 'bg-blue-500/20 text-blue-300 border border-blue-500/40 font-bold'
                      : 'text-gray-400 hover:text-white border border-transparent'
                  }`}
                >
                  ✉️ Email
                </button>
              </div>
              <button
                type="button"
                onClick={handlePollEmailNow}
                disabled={pollingEmail}
                title="Trigger immediate IMAP check for new incoming user emails"
                className="text-[10px] text-gray-400 hover:text-white flex items-center gap-1 bg-surface px-2 py-0.5 rounded border border-border-subtle hover:border-gray-600 disabled:opacity-50 cursor-pointer"
              >
                <RefreshCw size={10} className={pollingEmail ? 'animate-spin text-accent' : ''} />
                {pollingEmail ? 'Checking...' : 'Poll Inbox'}
              </button>
            </div>

            {/* Input Bar */}
            <div className="p-3 border-t border-border-subtle bg-surface/30">
              <div className="flex items-center gap-2 bg-surface border border-border-subtle rounded-xl px-3 py-1.5 focus-within:border-accent transition-all">
                <input
                  type="text"
                  placeholder={
                    activeContext?.incidentId
                      ? "Reply to Lear (or type 'Approve' to deploy fix)..."
                      : activeContext?.connectorId
                      ? `Ask Lear about ${activeContext.connectorId.toUpperCase()} telemetry or actions...`
                      : "Ask Lear or use @connector (e.g. @aws, @k8s)..."
                  }
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSend()}
                  className="flex-1 bg-transparent text-xs text-white placeholder-gray-500 focus:outline-none py-1.5"
                />
                <button
                  onClick={() => handleSend()}
                  disabled={!input.trim() || loading}
                  className="p-2 rounded-lg bg-accent text-gray-950 hover:bg-accent-light transition-all disabled:opacity-40 cursor-pointer"
                >
                  <Send size={14} />
                </button>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
