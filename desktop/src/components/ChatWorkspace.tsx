import React, { useState, useEffect, useRef } from 'react';
import {
  Sparkles,
  Send,
  Paperclip,
  Check,
  Copy,
  RefreshCw,
  Search,
  Plus,
  CheckCircle2,
  XCircle,
  Bot,
  User,
  X,
  FileCode,
} from 'lucide-react';

export interface ChatAttachment {
  filename: string;
  content: string;
  size?: number;
}

export interface ChatMessageRecord {
  id: string;
  sender: string;
  role: 'user' | 'assistant' | 'system';
  text: string;
  origin?: 'slack' | 'email' | 'dashboard' | 'incident' | string;
  timestamp: string;
  attachment?: ChatAttachment;
  quick_replies?: string[];
}

export interface ChatSessionData {
  session_id: string;
  title: string;
  origin: 'slack' | 'email' | 'dashboard' | 'incident' | string;
  service: string;
  incident_id?: string | null;
  status: 'ACTIVE' | 'RESOLVED' | 'DENIED' | string;
  created_at: string;
  last_activity: string;
  messages: ChatMessageRecord[];
  attachments?: ChatAttachment[];
}

export interface SessionMeta {
  session_id: string;
  title: string;
  origin: string;
  service: string;
  incident_id?: string | null;
  status: string;
  last_activity: string;
  created_at_epoch?: number;
  message_count: number;
}

export const ChatWorkspace: React.FC = () => {
  // Sessions and Active Chat state
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [activeSession, setActiveSession] = useState<ChatSessionData | null>(null);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [loadingChat, setLoadingChat] = useState(false);
  const [sending, setSending] = useState(false);

  // Filters & Search
  const [filterOrigin, setFilterOrigin] = useState<'all' | 'slack' | 'email' | 'dashboard' | 'incident'>('all');
  const [searchQuery, setSearchQuery] = useState('');

  // Input & Upload state
  const [inputText, setInputText] = useState('');
  const [attachedFile, setAttachedFile] = useState<ChatAttachment | null>(null);
  const [uploadingFile, setUploadingFile] = useState(false);
  const [copiedCodeId, setCopiedCodeId] = useState<string | null>(null);
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 1. Check URL parameters for session
  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      const sessionParam = params.get('session');
      if (sessionParam) {
        setActiveSessionId(sessionParam);
      }
    } catch {}
  }, []);

  // 2. Fetch Sessions List
  const fetchSessions = async (selectId?: string) => {
    setLoadingSessions(true);
    try {
      const res = await fetch('/api/chat/sessions');
      if (res.ok) {
        const data = await res.json();
        const list: SessionMeta[] = data.sessions || [];
        setSessions(list);

        // Auto select first session or specified session
        if (selectId) {
          setActiveSessionId(selectId);
        } else if (!activeSessionId && list.length > 0) {
          setActiveSessionId(list[0].session_id);
        }
      }
    } catch (e) {
      console.error('Error fetching chat sessions:', e);
    } finally {
      setLoadingSessions(false);
    }
  };

  useEffect(() => {
    fetchSessions();
  }, []);

  // 3. Fetch Active Session details
  const fetchActiveSession = async (sessionId: string) => {
    setLoadingChat(true);
    try {
      const res = await fetch(`/api/chat/sessions/${sessionId}`);
      if (res.ok) {
        const data = await res.json();
        setActiveSession(data.session);
      }
    } catch (e) {
      console.error(`Error loading session ${sessionId}:`, e);
    } finally {
      setLoadingChat(false);
    }
  };

  useEffect(() => {
    if (activeSessionId) {
      fetchActiveSession(activeSessionId);
    }
  }, [activeSessionId]);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [activeSession?.messages, sending]);

  // 4. Create New Session
  const handleCreateNewSession = async () => {
    try {
      const res = await fetch('/api/chat/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: 'New SRE Investigation',
          origin: 'dashboard',
          service: 'checkout-api',
        }),
      });
      if (res.ok) {
        const data = await res.json();
        const newSid = data.session?.session_id;
        if (newSid) {
          await fetchSessions(newSid);
        }
      }
    } catch (e) {
      console.error('Error creating new session:', e);
    }
  };

  // 5. Send Message
  const handleSendMessage = async (customPrompt?: string) => {
    const textToSend = customPrompt || inputText;
    if ((!textToSend.trim() && !attachedFile) || !activeSessionId || sending) return;

    setSending(true);
    const attachmentPayload = attachedFile ? { ...attachedFile } : null;

    // Optimistic local append
    const tempUserMsg: ChatMessageRecord = {
      id: `temp_${Date.now()}`,
      sender: 'Dashboard (Operator)',
      role: 'user',
      text: `dashboard: Operator: ${textToSend}`,
      origin: 'dashboard',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      attachment: attachmentPayload || undefined,
    };

    setActiveSession((prev) => {
      if (!prev) return null;
      return {
        ...prev,
        messages: [...prev.messages, tempUserMsg],
      };
    });

    setInputText('');
    setAttachedFile(null);

    try {
      const res = await fetch(`/api/chat/sessions/${activeSessionId}/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: textToSend,
          sender: 'Operator',
          origin: 'dashboard',
          attachment: attachmentPayload,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        if (data.session) {
          setActiveSession(data.session);
        }
      }
      fetchSessions();
    } catch (e) {
      console.error('Error sending message to Copilot:', e);
    } finally {
      setSending(false);
    }
  };

  // 6. Handle File Upload
  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setUploadingFile(true);
    try {
      const formData = new FormData();
      formData.append('file', file);

      const res = await fetch('/api/chat/upload', {
        method: 'POST',
        body: formData,
      });

      if (res.ok) {
        const data = await res.json();
        setAttachedFile({
          filename: data.filename,
          content: data.content,
          size: data.size,
        });
      } else {
        alert('Failed to upload file. Ensure it is a text/log document under 5MB.');
      }
    } catch (e) {
      console.error('File upload failed:', e);
      alert('File upload error');
    } finally {
      setUploadingFile(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  // 7. Approve / Deny Action Handlers
  const handleApproveAction = async (incidentId: string) => {
    try {
      setActionFeedback('Applying approved ConfigMap patch and rolling out deployment...');
      const res = await fetch(`/api/incident/${incidentId}/approve`, { method: 'POST' });
      if (res.ok) {
        setActionFeedback('✅ Fix Applied Successfully! Verification probe passed.');
        setTimeout(() => setActionFeedback(null), 4000);
        if (activeSessionId) fetchActiveSession(activeSessionId);
        fetchSessions();
      }
    } catch (e) {
      setActionFeedback('Approval action failed.');
    }
  };

  const handleDenyAction = async (incidentId: string) => {
    try {
      setActionFeedback('Halting autonomous remediation and escalating to human...');
      const res = await fetch(`/api/incident/${incidentId}/deny`, { method: 'POST' });
      if (res.ok) {
        setActionFeedback('❌ Remediation Denied. Autonomous action halted.');
        setTimeout(() => setActionFeedback(null), 4000);
        if (activeSessionId) fetchActiveSession(activeSessionId);
        fetchSessions();
      }
    } catch (e) {
      setActionFeedback('Denial action failed.');
    }
  };

  // Filter sessions
  const filteredSessions = sessions.filter((s) => {
    if (filterOrigin !== 'all' && s.origin?.toLowerCase() !== filterOrigin.toLowerCase()) {
      return false;
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      return (
        s.title?.toLowerCase().includes(q) ||
        s.service?.toLowerCase().includes(q) ||
        s.session_id?.toLowerCase().includes(q) ||
        (s.incident_id && s.incident_id.toLowerCase().includes(q))
      );
    }
    return true;
  });

  // Badge helpers
  const getOriginBadge = (origin: string) => {
    switch (origin?.toLowerCase()) {
      case 'slack':
        return { label: 'Slack', bg: 'bg-[#4A154B]/30 text-[#ECB22E] border-[#E01E5A]/40' };
      case 'email':
        return { label: 'Email', bg: 'bg-blue-500/20 text-sky-400 border-sky-500/40' };
      case 'incident':
        return { label: 'Incident', bg: 'bg-rose-500/20 text-rose-400 border-rose-500/40' };
      case 'dashboard':
      default:
        return { label: 'Dashboard', bg: 'bg-cyan-500/20 text-[#00F0FF] border-cyan-500/40' };
    }
  };

  const handleCopyCode = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedCodeId(id);
    setTimeout(() => setCopiedCodeId(null), 2000);
  };

  // Render markdown text with codeblocks, lists, and formatting
  const renderMessageContent = (text: string, msgId: string) => {
    const lines = text.split('\n');
    const nodes: React.ReactNode[] = [];
    let inCode = false;
    let codeLines: string[] = [];
    let codeLang = '';

    lines.forEach((line, idx) => {
      if (line.trim().startsWith('```')) {
        if (!inCode) {
          inCode = true;
          codeLang = line.replace('```', '').trim() || 'log';
          codeLines = [];
        } else {
          inCode = false;
          const codeSnippet = codeLines.join('\n');
          const codeKey = `${msgId}_code_${idx}`;
          nodes.push(
            <div key={codeKey} className="my-2 rounded-lg border border-[#1E293B] bg-[#07090E] overflow-hidden text-xs font-mono">
              <div className="flex items-center justify-between px-3 py-1.5 bg-[#0D121F] border-b border-[#1E293B] text-[11px] text-gray-400">
                <span>{codeLang || 'console'}</span>
                <button
                  onClick={() => handleCopyCode(codeSnippet, codeKey)}
                  className="flex items-center gap-1 text-gray-400 hover:text-white transition-colors"
                >
                  {copiedCodeId === codeKey ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>{copiedCodeId === codeKey ? 'Copied' : 'Copy'}</span>
                </button>
              </div>
              <pre className="p-3 overflow-x-auto text-emerald-300 font-mono text-xs leading-relaxed whitespace-pre-wrap">
                {codeSnippet}
              </pre>
            </div>
          );
        }
      } else if (inCode) {
        codeLines.push(line);
      } else {
        // Regular line formatting
        if (line.startsWith('### ')) {
          nodes.push(
            <h4 key={`h_${idx}`} className="text-sm font-bold text-white mt-2 mb-1">
              {line.replace('### ', '')}
            </h4>
          );
        } else if (line.startsWith('## ')) {
          nodes.push(
            <h3 key={`h_${idx}`} className="text-base font-bold text-[#00F0FF] mt-3 mb-1">
              {line.replace('## ', '')}
            </h3>
          );
        } else if (line.startsWith('• ') || line.startsWith('- ')) {
          nodes.push(
            <div key={`li_${idx}`} className="flex items-start gap-2 my-0.5 text-xs text-gray-200">
              <span className="text-[#00F0FF] mt-0.5">•</span>
              <span>{formatInlineMarkdown(line.substring(2))}</span>
            </div>
          );
        } else if (line.trim() === '') {
          nodes.push(<div key={`sp_${idx}`} className="h-1.5" />);
        } else {
          nodes.push(
            <p key={`p_${idx}`} className="my-1 text-xs text-gray-200 leading-relaxed">
              {formatInlineMarkdown(line)}
            </p>
          );
        }
      }
    });

    return nodes;
  };

  const formatInlineMarkdown = (str: string) => {
    const parts = str.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
    return parts.map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return (
          <strong key={i} className="font-semibold text-white">
            {part.slice(2, -2)}
          </strong>
        );
      }
      if (part.startsWith('`') && part.endsWith('`')) {
        return (
          <code key={i} className="px-1.5 py-0.5 rounded bg-black/50 border border-[#1E293B] text-[#00F0FF] font-mono text-[11px]">
            {part.slice(1, -1)}
          </code>
        );
      }
      return part;
    });
  };

  return (
    <div className="flex h-full w-full bg-[#080B11] text-gray-100 overflow-hidden font-sans">
      {/* ─── LEFT COLUMN: Session History & Audit Log ─── */}
      <div className="w-80 md:w-96 border-r border-[#1E293B] bg-[#0A0E18] flex flex-col h-full flex-shrink-0">
        {/* Header */}
        <div className="p-4 border-b border-[#1E293B] flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500/20 to-blue-500/20 border border-cyan-500/30 flex items-center justify-center text-[#00F0FF]">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-bold tracking-wide text-white flex items-center gap-1.5">
                Lear SRE Chat
              </h2>
              <p className="text-[11px] text-gray-400 font-mono">Shared Multi-Channel Audit</p>
            </div>
          </div>
          <button
            onClick={handleCreateNewSession}
            title="Start new investigation"
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-md bg-[#00F0FF]/10 hover:bg-[#00F0FF]/20 text-[#00F0FF] border border-[#00F0FF]/30 text-xs font-medium transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>New</span>
          </button>
        </div>

        {/* Filter Tabs */}
        <div className="p-2 border-b border-[#1E293B] bg-[#07090E]/60 flex items-center gap-1 overflow-x-auto text-[11px]">
          {(['all', 'slack', 'email', 'dashboard', 'incident'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setFilterOrigin(tab)}
              className={`px-2.5 py-1 rounded capitalize font-medium whitespace-nowrap transition-all ${
                filterOrigin === tab
                  ? 'bg-[#00F0FF] text-[#041019] font-bold shadow-sm'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-[#111624]'
              }`}
            >
              {tab === 'all' ? 'All' : tab === 'slack' ? '💬 Slack' : tab === 'email' ? '✉️ Email' : tab === 'dashboard' ? '🖥️ Dash' : '🚨 Incident'}
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="p-2.5 border-b border-[#1E293B] bg-[#0A0E18]">
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-gray-500" />
            <input
              type="text"
              placeholder="Search chat history & audit..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 text-xs rounded-md bg-[#0E1322] border border-[#1E293B] text-gray-200 placeholder-gray-500 focus:outline-none focus:border-[#00F0FF]/50 transition-colors"
            />
          </div>
        </div>

        {/* Sessions List */}
        <div className="flex-1 overflow-y-auto divide-y divide-[#1E293B]/60">
          {loadingSessions && sessions.length === 0 ? (
            <div className="p-8 text-center text-xs text-gray-500 flex flex-col items-center gap-2">
              <RefreshCw className="w-4 h-4 animate-spin text-[#00F0FF]" />
              <span>Loading audit sessions...</span>
            </div>
          ) : filteredSessions.length === 0 ? (
            <div className="p-8 text-center text-xs text-gray-500">
              No sessions found matching filters.
            </div>
          ) : (
            filteredSessions.map((session) => {
              const isSelected = session.session_id === activeSessionId;
              const badge = getOriginBadge(session.origin);
              return (
                <div
                  key={session.session_id}
                  onClick={() => setActiveSessionId(session.session_id)}
                  className={`p-3 cursor-pointer transition-all ${
                    isSelected
                      ? 'bg-[#111625] border-l-2 border-[#00F0FF]'
                      : 'hover:bg-[#0E1322]/80 border-l-2 border-transparent'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2 mb-1.5">
                    <span className="text-xs font-medium text-white truncate max-w-[190px]">
                      {session.title}
                    </span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded border font-mono ${badge.bg}`}>
                      {badge.label}
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-[11px] text-gray-400 font-mono">
                    <span className="truncate max-w-[130px] text-gray-400">
                      {session.service || 'checkout-api'}
                    </span>
                    <div className="flex items-center gap-2">
                      <span>{session.message_count} msgs</span>
                      {session.status === 'RESOLVED' ? (
                        <span className="text-emerald-400">✓</span>
                      ) : session.status === 'DENIED' ? (
                        <span className="text-rose-400">✗</span>
                      ) : (
                        <span className="text-amber-400">●</span>
                      )}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Audit Log Footer Status */}
        <div className="p-3 border-t border-[#1E293B] bg-[#07090E] text-[11px] flex items-center justify-between text-gray-400 font-mono">
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            Live Audit Stream
          </span>
          <span>{sessions.length} total sessions</span>
        </div>
      </div>

      {/* ─── RIGHT COLUMN: Active Chat Conversation & Actions ─── */}
      <div className="flex-1 flex flex-col h-full bg-[#080B11] relative overflow-hidden">
        {activeSession ? (
          <>
            {/* Top Workspace Header */}
            <div className="px-6 py-3.5 border-b border-[#1E293B] bg-[#0B0F19] flex items-center justify-between z-10">
              <div className="flex items-center gap-3">
                <div className="flex flex-col">
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-bold text-white tracking-wide">
                      {activeSession.title}
                    </h3>
                    <span className={`text-[10px] px-2 py-0.5 rounded border font-mono ${getOriginBadge(activeSession.origin).bg}`}>
                      {getOriginBadge(activeSession.origin).label}
                    </span>
                    {activeSession.incident_id && (
                      <span className="text-[10px] px-2 py-0.5 rounded bg-rose-500/10 text-rose-400 border border-rose-500/30 font-mono">
                        {activeSession.incident_id}
                      </span>
                    )}
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded font-mono uppercase ${
                        activeSession.status === 'RESOLVED'
                          ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                          : activeSession.status === 'DENIED'
                          ? 'bg-rose-500/10 text-rose-400 border border-rose-500/30'
                          : 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30'
                      }`}
                    >
                      {activeSession.status}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-[11px] text-gray-400 font-mono mt-0.5">
                    <span>Target: {activeSession.service}</span>
                    <span>•</span>
                    <span>Cluster: AWS EKS lear-demo (ap-south-1)</span>
                    <span>•</span>
                    <span>Last: {activeSession.last_activity}</span>
                  </div>
                </div>
              </div>

              {/* Action Buttons in Header */}
              <div className="flex items-center gap-2">
                <button
                  onClick={() => fetchActiveSession(activeSession.session_id)}
                  title="Reload conversation"
                  className="p-1.5 rounded-md hover:bg-[#1E293B] text-gray-400 hover:text-white transition-colors"
                >
                  <RefreshCw className={`w-4 h-4 ${loadingChat ? 'animate-spin text-[#00F0FF]' : ''}`} />
                </button>
              </div>
            </div>

            {/* Action Feedback Banner */}
            {actionFeedback && (
              <div className="px-6 py-2 bg-gradient-to-r from-emerald-950/40 to-cyan-950/40 border-b border-emerald-500/30 text-emerald-300 text-xs flex items-center gap-2 font-mono animate-fadeIn">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span>{actionFeedback}</span>
              </div>
            )}

            {/* Messages Feed */}
            <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
              {activeSession.messages.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center p-8 text-gray-400">
                  <div className="w-12 h-12 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-[#00F0FF] mb-3">
                    <Sparkles className="w-6 h-6" />
                  </div>
                  <h4 className="text-sm font-semibold text-white mb-1">Lear Autonomous SRE Ready</h4>
                  <p className="text-xs text-gray-500 max-w-sm mb-4">
                    Ask questions, upload pod logs, or inspect Kubernetes deployments. Slack, Email, and Dashboard chats stay strictly separated with full audit persistence.
                  </p>
                </div>
              ) : (
                activeSession.messages.map((msg, idx) => {
                  const isUser = msg.role === 'user';
                  return (
                    <div
                      key={msg.id || idx}
                      className={`flex gap-3 max-w-4xl ${isUser ? 'ml-auto flex-row-reverse' : 'mr-auto'}`}
                    >
                      {/* Avatar */}
                      <div
                        className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 text-xs font-bold border ${
                          isUser
                            ? 'bg-[#1E293B] text-gray-200 border-gray-700'
                            : 'bg-gradient-to-br from-[#00F0FF]/20 to-blue-500/20 text-[#00F0FF] border-[#00F0FF]/30'
                        }`}
                      >
                        {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
                      </div>

                      {/* Message Content Bubble */}
                      <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
                        <div className="flex items-center gap-2 mb-1 px-1 text-[11px] text-gray-400 font-mono">
                          <span className="font-semibold text-gray-300">{msg.sender}</span>
                          <span>•</span>
                          <span>{msg.timestamp}</span>
                        </div>

                        <div
                          className={`rounded-xl px-4 py-3 text-xs leading-relaxed border ${
                            isUser
                              ? 'bg-[#0E1626] border-[#1E2E48] text-gray-100 shadow-sm'
                              : 'bg-[#0A0E18] border-[#1E293B] text-gray-200 shadow-md w-full'
                          }`}
                        >
                          {/* Attached file bubble */}
                          {msg.attachment && (
                            <div className="mb-2.5 p-2.5 rounded-lg bg-[#07090E] border border-[#1E293B] flex items-center justify-between text-xs font-mono">
                              <div className="flex items-center gap-2 text-cyan-400">
                                <FileCode className="w-4 h-4" />
                                <span className="font-bold">{msg.attachment.filename}</span>
                                {msg.attachment.size && (
                                  <span className="text-[10px] text-gray-500">
                                    ({Math.round(msg.attachment.size / 1024)} KB)
                                  </span>
                                )}
                              </div>
                            </div>
                          )}

                          {/* Message Text / Markdown */}
                          <div className="markdown-body">
                            {renderMessageContent(msg.text, msg.id || String(idx))}
                          </div>

                          {/* Interactive Remediation Actions inside message if incident awaiting approval */}
                          {msg.role === 'assistant' &&
                            activeSession.incident_id &&
                            activeSession.status === 'ACTIVE' && (
                              <div className="mt-4 pt-3 border-t border-[#1E293B] flex items-center gap-2.5">
                                <button
                                  onClick={() => handleApproveAction(activeSession.incident_id!)}
                                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/40 text-xs font-bold transition-colors"
                                >
                                  <CheckCircle2 className="w-3.5 h-3.5" />
                                  <span>Approve & Apply Fix</span>
                                </button>
                                <button
                                  onClick={() => handleDenyAction(activeSession.incident_id!)}
                                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/40 text-xs font-bold transition-colors"
                                >
                                  <XCircle className="w-3.5 h-3.5" />
                                  <span>Deny Fix</span>
                                </button>
                              </div>
                            )}
                        </div>
                      </div>
                    </div>
                  );
                })
              )}

              {/* Streaming / Sending Indicator */}
              {sending && (
                <div className="flex gap-3 max-w-xl mr-auto animate-pulse">
                  <div className="w-7 h-7 rounded-lg bg-cyan-500/20 border border-cyan-500/30 text-[#00F0FF] flex items-center justify-center">
                    <Bot className="w-4 h-4" />
                  </div>
                  <div className="bg-[#0A0E18] border border-[#1E293B] rounded-xl px-4 py-2.5 text-xs text-gray-400 font-mono flex items-center gap-2">
                    <Sparkles className="w-3.5 h-3.5 text-[#00F0FF] animate-spin" />
                    <span>Lear investigating cluster telemetry & formulating reply...</span>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {/* Quick Action Chips */}
            <div className="px-6 py-2 border-t border-[#1E293B]/60 bg-[#0A0E18]/60 flex items-center gap-2 overflow-x-auto text-[11px]">
              <span className="text-gray-500 text-[10px] uppercase font-mono tracking-wider flex-shrink-0">
                Suggested:
              </span>
              {[
                '⚡ Full Infrastructure Triage (with Graphs)',
                'Verify cluster health & microservice status',
                'Inspect checkout-api pod logs',
                'Check database replica connectivity',
                'Approve latest incident remediation',
              ].map((chip) => (
                <button
                  key={chip}
                  onClick={() => handleSendMessage(chip === '⚡ Full Infrastructure Triage (with Graphs)' ? 'Perform full cluster health check and audit all pod statuses.' : chip)}
                  className={`px-2.5 py-1 rounded-full text-xs whitespace-nowrap transition-colors border ${
                    chip.startsWith('⚡')
                      ? 'bg-accent/15 hover:bg-accent/25 text-accent border-accent/40 font-semibold'
                      : 'bg-[#0E1626] hover:bg-[#152035] text-gray-300 hover:text-white border-[#1E293B]'
                  }`}
                >
                  {chip}
                </button>
              ))}
            </div>

            {/* Attached File Preview Pill */}
            {attachedFile && (
              <div className="px-6 py-1.5 bg-[#0D1322] border-t border-[#1E293B] flex items-center justify-between text-xs text-cyan-300 font-mono">
                <div className="flex items-center gap-2">
                  <Paperclip className="w-3.5 h-3.5 text-cyan-400" />
                  <span className="font-bold">{attachedFile.filename}</span>
                  <span className="text-[10px] text-gray-400">
                    ({Math.round((attachedFile.size || 0) / 1024)} KB)
                  </span>
                </div>
                <button
                  onClick={() => setAttachedFile(null)}
                  className="p-1 text-gray-400 hover:text-white"
                  title="Remove attachment"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {/* Bottom Input Area */}
            <div className="p-4 border-t border-[#1E293B] bg-[#0A0E18]">
              <div className="relative flex items-center rounded-xl bg-[#0E1322] border border-[#1E293B] focus-within:border-[#00F0FF]/50 transition-colors p-1.5">
                {/* File Upload Hidden Input */}
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={handleFileUpload}
                  accept=".log,.txt,.json,.yaml,.yml,.csv,.py,.ts,.sh"
                  className="hidden"
                />

                {/* Upload Button */}
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploadingFile || sending}
                  title="Upload log or configuration file"
                  className="p-2 text-gray-400 hover:text-cyan-400 hover:bg-[#1E293B]/50 rounded-lg transition-colors flex-shrink-0"
                >
                  {uploadingFile ? (
                    <RefreshCw className="w-4 h-4 animate-spin text-cyan-400" />
                  ) : (
                    <Paperclip className="w-4 h-4" />
                  )}
                </button>

                {/* Textarea Input */}
                <textarea
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleSendMessage();
                    }
                  }}
                  placeholder="Ask Lear SRE or paste logs... (Enter to send, Shift+Enter for newline)"
                  rows={1}
                  className="flex-1 bg-transparent px-3 py-1.5 text-xs text-white placeholder-gray-500 focus:outline-none resize-none font-sans"
                />

                {/* Send Button */}
                <button
                  onClick={() => handleSendMessage()}
                  disabled={(!inputText.trim() && !attachedFile) || sending}
                  className={`p-2 rounded-lg transition-all flex-shrink-0 ${
                    inputText.trim() || attachedFile
                      ? 'bg-[#00F0FF] text-[#041019] hover:bg-[#38BDF8] shadow-md'
                      : 'text-gray-600 cursor-not-allowed'
                  }`}
                >
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-center p-8">
            <div className="w-12 h-12 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-[#00F0FF] mb-3">
              <Sparkles className="w-6 h-6" />
            </div>
            <h3 className="text-base font-bold text-white mb-1">No Chat Session Selected</h3>
            <p className="text-xs text-gray-400 max-w-sm mb-4">
              Select an investigation session from the audit list on the left, or create a new session.
            </p>
            <button
              onClick={handleCreateNewSession}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[#00F0FF] text-[#041019] text-xs font-bold hover:bg-[#38BDF8] transition-colors"
            >
              <Plus className="w-4 h-4" />
              <span>Start New Investigation</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default ChatWorkspace;
