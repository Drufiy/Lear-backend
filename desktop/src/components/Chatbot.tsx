import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Send, Bot, User, Check, Terminal } from 'lucide-react';

export default function Chatbot({ isOpen, onClose }: { isOpen: boolean, onClose: () => void }) {
  const [messages, setMessages] = useState<Array<{ id: number, sender: string, text: string, actionRequired?: boolean }>>([
    { id: 1, sender: 'agent', text: 'Hello! I am Prash. I am monitoring your infrastructure. How can I help you today?' }
  ]);
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim()) return;
    
    const newMsg = { id: Date.now(), sender: 'user', text: input };
    setMessages(prev => [...prev, newMsg]);
    setInput('');
    
    // Send to backend
    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: input })
      });
      const data = await res.json();
      
      setMessages(prev => [...prev, { 
        id: Date.now(), 
        sender: 'agent', 
        text: data.text, 
        actionRequired: data.actionRequired,
        command: data.command 
      }]);
    } catch (e) {
      setMessages(prev => [...prev, { id: Date.now(), sender: 'agent', text: "Error reaching the backend." }]);
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
            transition={{ type: 'spring', bounce: 0, duration: 0.4 }}
            className="fixed right-0 top-0 bottom-0 w-full max-w-md bg-gray-950 border-l border-gray-800 z-50 flex flex-col shadow-2xl"
          >
            <div className="flex items-center justify-between p-6 border-b border-gray-800 bg-gray-900/50">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-accent/20 text-accent rounded-lg">
                  <Terminal size={20} />
                </div>
                <div>
                  <h3 className="font-semibold text-lg">Prash Copilot</h3>
                  <p className="text-xs text-accent flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" /> Online
                  </p>
                </div>
              </div>
              <button onClick={onClose} className="p-2 text-gray-400 hover:text-white rounded-lg hover:bg-gray-800 transition-colors">
                <X size={20} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {messages.map(msg => (
                <div key={msg.id} className={`flex gap-4 ${msg.sender === 'user' ? 'flex-row-reverse' : ''}`}>
                  <div className={`p-2 rounded-full h-fit ${msg.sender === 'user' ? 'bg-blue-500/20 text-blue-400' : 'bg-gray-800 text-accent'}`}>
                    {msg.sender === 'user' ? <User size={18} /> : <Bot size={18} />}
                  </div>
                  <div className={`flex flex-col gap-2 max-w-[75%] ${msg.sender === 'user' ? 'items-end' : 'items-start'}`}>
                    <div className={`p-3 rounded-2xl ${msg.sender === 'user' ? 'bg-blue-600/20 text-blue-100 rounded-tr-sm' : 'bg-gray-900 border border-gray-800 text-gray-300 rounded-tl-sm'}`}>
                      {msg.text}
                    </div>
                    {msg.actionRequired && (
                      <button className="flex items-center gap-2 bg-accent text-black px-4 py-2 rounded-lg text-sm font-semibold hover:bg-[#2da36c] transition-colors">
                        <Check size={16} /> Approve Action
                      </button>
                    )}
                  </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>

            <div className="p-4 border-t border-gray-800 bg-gray-900/50">
              <div className="relative flex items-center">
                <input
                  type="text"
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSend()}
                  placeholder="Ask Prash to investigate or type /fix..."
                  className="w-full bg-gray-950 border border-gray-800 rounded-xl pl-4 pr-12 py-3 focus:outline-none focus:border-accent text-sm transition-colors"
                />
                <button 
                  onClick={handleSend}
                  disabled={!input.trim()}
                  className="absolute right-2 p-2 text-accent disabled:text-gray-600 disabled:cursor-not-allowed hover:bg-accent/10 rounded-lg transition-colors"
                >
                  <Send size={18} />
                </button>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
