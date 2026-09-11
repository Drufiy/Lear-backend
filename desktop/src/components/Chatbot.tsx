import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Send, Check, Terminal, Sparkles, Play } from 'lucide-react';

interface ChatbotProps {
  isOpen: boolean;
  onClose: () => void;
  serviceContext?: {
    connectorId?: string;
    resourceId?: string;
  } | null;
}

interface Message {
  id: number;
  sender: 'user' | 'agent';
  text: string;
  actionRequired?: boolean;
  command?: string[];
  executable?: boolean;
  executed?: boolean;
}

export default function Chatbot({ isOpen, onClose, serviceContext }: ChatbotProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 1,
      sender: 'agent',
      text: 'Hello! I am Lear Copilot. I analyze your live infrastructure telemetry in real-time. How can I assist your operational workflow?',
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [executingActionId, setExecutingActionId] = useState<number | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userText = input.trim();
    const newMsg: Message = { id: Date.now(), sender: 'user', text: userText };
    setMessages(prev => [...prev, newMsg]);
    setInput('');
    setLoading(true);

    try {
      const payload: any = { message: userText };
      if (serviceContext) {
        payload.service_context = serviceContext;
      }

      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) throw new Error('API response failed');
      const data = await res.json();

      setMessages(prev => [
        ...prev,
        {
          id: Date.now() + 1,
          sender: 'agent',
          text: data.text || 'I analyzed the infrastructure state.',
          command: data.command,
          actionRequired: data.actionRequired,
          executable: data.executable,
        },
      ]);
    } catch (e) {
      setMessages(prev => [
        ...prev,
        { id: Date.now() + 1, sender: 'agent', text: 'Error connecting to the Lear reasoning engine.' },
      ]);
    } finally {
      setLoading(false);
    }
  };

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
          service_context: serviceContext,
        }),
      });

      const data = await res.json();
      setMessages(prev =>
        prev.map(m => (m.id === msgId ? { ...m, executed: true } : m))
      );

      setMessages(prev => [
        ...prev,
        {
          id: Date.now(),
          sender: 'agent',
          text: data.success
            ? `Execution succeeded for \`prash ${command.join(' ')}\`:\n\n${data.output || 'Action dispatched and applied to infrastructure.'}`
            : `Execution failed for \`prash ${command.join(' ')}\`:\n\n${data.output || 'Action execution returned an error.'}`,
        },
      ]);
    } catch (e: any) {
      setMessages(prev => [
        ...prev,
        {
          id: Date.now(),
          sender: 'agent',
          text: `Failed to dispatch command to Lear Engine: ${e?.message || String(e)}`,
        },
      ]);
    } finally {
      setExecutingActionId(null);
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/60 z-40 backdrop-blur-sm"
          />
          <motion.div
            initial={{ x: '100%', opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: '100%', opacity: 0 }}
            transition={{ type: 'spring', bounce: 0, duration: 0.35 }}
            className="fixed right-0 top-0 bottom-0 w-full max-w-md bg-[#080B11] border-l border-border-subtle z-50 flex flex-col shadow-2xl"
          >
            {/* Header */}
            <div className="p-5 border-b border-border-subtle bg-surface/40 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="p-2.5 bg-accent/15 text-accent rounded-xl border border-accent/25">
                  <Sparkles size={18} />
                </div>
                <div>
                  <h3 className="font-bold text-base text-white">Lear Copilot</h3>
                  <p className="text-[11px] text-accent flex items-center gap-1.5 font-mono">
                    <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" /> Telemetry Context Active
                  </p>
                </div>
              </div>
              <button
                onClick={onClose}
                className="p-1.5 text-gray-400 hover:text-white rounded-lg hover:bg-surface transition-colors cursor-pointer"
              >
                <X size={18} />
              </button>
            </div>

            {/* Service Context Chip */}
            {serviceContext?.connectorId && (
              <div className="px-5 py-2 bg-surface/70 border-b border-border-subtle flex items-center gap-2 text-xs">
                <span className="text-gray-400">Context:</span>
                <span className="px-2 py-0.5 rounded bg-accent/15 text-accent font-mono font-medium">
                  {serviceContext.connectorId.toUpperCase()}
                  {serviceContext.resourceId ? ` / ${serviceContext.resourceId}` : ''}
                </span>
              </div>
            )}

            {/* Message Feed */}
            <div className="flex-1 overflow-y-auto p-5 space-y-4">
              {messages.map(msg => (
                <div
                  key={msg.id}
                  className={`flex flex-col ${msg.sender === 'user' ? 'items-end' : 'items-start'}`}
                >
                  <div
                    className={`max-w-[85%] p-3.5 rounded-2xl text-xs leading-relaxed ${
                      msg.sender === 'user'
                        ? 'bg-accent text-gray-950 font-medium rounded-tr-none'
                        : 'bg-surface border border-border-subtle text-gray-200 rounded-tl-none'
                    }`}
                  >
                    <p className="whitespace-pre-wrap">{msg.text}</p>

                    {/* Action Execution Button */}
                    {msg.command && (
                      <div className="mt-3 pt-2.5 border-t border-border-subtle flex flex-col gap-2">
                        <div className="flex items-center gap-1.5 text-[10px] font-mono text-gray-400">
                          <Terminal size={12} />
                          <code>prash {msg.command.join(' ')}</code>
                        </div>
                        {msg.executed ? (
                          <span className="flex items-center gap-1 text-[11px] text-accent font-semibold">
                            <Check size={14} /> Action Dispatched
                          </span>
                        ) : (
                          <button
                            onClick={() => handleExecuteAction(msg.id, msg.command)}
                            disabled={executingActionId === msg.id}
                            className="flex items-center justify-center gap-1.5 w-full py-1.5 px-3 rounded-lg bg-accent/20 hover:bg-accent/30 border border-accent/40 text-accent font-bold text-xs transition-all cursor-pointer disabled:opacity-50"
                          >
                            {executingActionId === msg.id ? (
                              <>
                                <div className="w-3 h-3 rounded-full border-2 border-accent border-t-transparent animate-spin" />
                                <span>Executing Action...</span>
                              </>
                            ) : (
                              <>
                                <Play size={12} />
                                <span>Execute Action</span>
                              </>
                            )}
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {loading && (
                <div className="flex items-center gap-2 text-xs text-gray-500 font-mono">
                  <span className="w-1.5 h-1.5 rounded-full bg-accent animate-ping" />
                  Lear is analyzing live metrics...
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input Bar */}
            <div className="p-4 border-t border-border-subtle bg-surface/30">
              <div className="flex items-center gap-2 bg-surface border border-border-subtle rounded-xl px-3 py-1.5 focus-within:border-accent transition-all">
                <input
                  type="text"
                  placeholder="Ask Copilot about telemetry or actions..."
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSend()}
                  className="flex-1 bg-transparent text-xs text-white placeholder-gray-500 focus:outline-none py-1.5"
                />
                <button
                  onClick={handleSend}
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
