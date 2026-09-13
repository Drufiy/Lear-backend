import { useState, useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Send, Sparkles, Trash2, ArrowRight } from 'lucide-react';
import ChatMessage, { ChatMessageData } from './ChatMessage';

interface ChatbotProps {
  isOpen: boolean;
  onClose: () => void;
  serviceContext?: {
    connectorId?: string;
    resourceId?: string;
  } | null;
}

export default function Chatbot({ isOpen, onClose, serviceContext }: ChatbotProps) {
  const [messages, setMessages] = useState<ChatMessageData[]>([]);
  const [suggestedPrompts, setSuggestedPrompts] = useState<string[]>([]);
  const [activeContext, setActiveContext] = useState<{ connectorId?: string; resourceId?: string } | null>(
    serviceContext || null
  );
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [executingActionId, setExecutingActionId] = useState<number | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Sync activeContext with serviceContext prop updates
  useEffect(() => {
    setActiveContext(serviceContext || null);
  }, [serviceContext]);

  // Auto-scroll to bottom on messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  // Load context-aware dynamic greeting whenever opened or context switches
  const loadGreeting = useCallback(async (ctx: { connectorId?: string; resourceId?: string } | null) => {
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
          text: data.greeting || 'Hello! I am Lear Copilot. How can I assist your operational workflow?',
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
            text: `Lear Copilot active. (Bridge notice: ${errText || 'default telemetry loaded'})`,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
        ]);
      }
    } catch (e: any) {
      setMessages([
        {
          id: Date.now(),
          sender: 'agent',
          text: `Lear Copilot active. Could not reach backend greeting: ${e?.message || String(e)}`,
          isError: true,
        },
      ]);
    }
  }, []);

  // Fetch greeting when drawer opens
  useEffect(() => {
    if (isOpen) {
      loadGreeting(activeContext);
    }
  }, [isOpen, activeContext, loadGreeting]);

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
      text: overridePrompt || input.trim(),
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages(prev => [...prev, userMsg]);
    if (!overridePrompt) setInput('');
    setLoading(true);

    const streamMsgId = Date.now() + 1;

    try {
      // 1. Try SSE streaming endpoint
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
        // Fallback to standard POST /api/chat if streaming response is not 200
        const fallbackRes = await fetch('/api/chat', {
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

        if (!fallbackRes.ok) {
          let errDetail = 'Request failed';
          try {
            const errData = await fallbackRes.json();
            errDetail = errData.detail || errData.message || JSON.stringify(errData);
          } catch {
            errDetail = await fallbackRes.text();
          }
          throw new Error(`Lear Bridge Error (${fallbackRes.status}): ${errDetail}`);
        }

        const data = await fallbackRes.json();
        setMessages(prev => [
          ...prev,
          {
            id: streamMsgId,
            sender: 'agent',
            text: data.text || 'I analyzed the infrastructure state.',
            command: data.command,
            actionRequired: data.actionRequired,
            executable: data.executable,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
        ]);
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
    loadGreeting(activeContext);
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
                <div className="p-2.5 bg-accent/15 text-accent rounded-xl border border-accent/25 shadow-sm">
                  <Sparkles size={18} />
                </div>
                <div>
                  <h3 className="font-bold text-base text-white">Lear Copilot</h3>
                  <p className="text-[11px] text-accent flex items-center gap-1.5 font-mono">
                    <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
                    {activeContext?.connectorId ? 'Telemetry Context Active' : 'Global Infrastructure Copilot'}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={handleClearChat}
                  title="Clear chat history"
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

            {/* Service Context Chip & Global Switcher */}
            {activeContext?.connectorId ? (
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

            {/* Suggested Prompt Chips */}
            {suggestedPrompts.length > 0 && messages.length <= 2 && (
              <div className="px-4 py-2 bg-[#090D15] border-t border-border-subtle/50 flex flex-col gap-1.5">
                <span className="text-[10px] uppercase font-bold tracking-wider text-gray-400">
                  Suggested Questions
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {suggestedPrompts.map((prompt, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleSend(prompt)}
                      disabled={loading}
                      className="flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded-lg bg-surface hover:bg-surface/80 border border-border-subtle hover:border-accent/40 text-gray-300 hover:text-white transition-all text-left cursor-pointer disabled:opacity-50"
                    >
                      <span>{prompt}</span>
                      <ArrowRight size={10} className="text-accent shrink-0" />
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Input Bar */}
            <div className="p-4 border-t border-border-subtle bg-surface/30">
              <div className="flex items-center gap-2 bg-surface border border-border-subtle rounded-xl px-3 py-1.5 focus-within:border-accent transition-all">
                <input
                  type="text"
                  placeholder={
                    activeContext?.connectorId
                      ? `Ask Copilot about ${activeContext.connectorId.toUpperCase()} telemetry or actions...`
                      : "Ask Copilot or use @connector (e.g. @aws, @k8s)..."
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
