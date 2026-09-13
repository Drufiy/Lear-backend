import { useState } from 'react';
import {
  Bell,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  Info,
  CheckCheck,
  Trash2,
  Sliders,
  MessageSquare,
  Mail,
  ShieldAlert,
  Search,
  Sparkles,
  ExternalLink,
  RotateCcw,
} from 'lucide-react';
import useNotifications, { AppNotification } from '../hooks/useNotifications';
import { useLear } from '../context/LearContext';

export default function Notifications() {
  const {
    notifications,
    unreadCount,
    markAsRead,
    markAllAsRead,
    clearAll,
    refresh,
  } = useNotifications();

  const { setActiveTab, openChat } = useLear();

  const [activeView, setActiveView] = useState<'alerts' | 'channels'>('alerts');
  const [severityFilter, setSeverityFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Filter notifications based on severity and search query
  const filteredNotifications = notifications.filter(n => {
    // Severity filter
    if (severityFilter === 'unread' && n.read) return false;
    if (severityFilter === 'error' && n.severity !== 'error') return false;
    if (severityFilter === 'warning' && n.severity !== 'warning') return false;
    if (severityFilter === 'info' && n.severity !== 'info') return false;

    // Search query filter
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      const matchTitle = n.title?.toLowerCase().includes(q);
      const matchMsg = n.message?.toLowerCase().includes(q);
      const matchConn = n.connector?.toLowerCase().includes(q);
      if (!matchTitle && !matchMsg && !matchConn) return false;
    }

    return true;
  });

  // Group into NEW (unread) and EARLIER (read)
  const newNotifications = filteredNotifications.filter(n => !n.read);
  const earlierNotifications = filteredNotifications.filter(n => n.read);

  const getSeverityIcon = (sev: string) => {
    switch (sev) {
      case 'error':
        return <AlertCircle size={18} className="text-rose-400 shrink-0" />;
      case 'warning':
        return <AlertTriangle size={18} className="text-amber-400 shrink-0" />;
      case 'success':
        return <CheckCircle2 size={18} className="text-accent shrink-0" />;
      default:
        return <Info size={18} className="text-cyan-400 shrink-0" />;
    }
  };

  const formatRelativeTime = (timestamp: string) => {
    try {
      const date = new Date(timestamp);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffSecs = Math.floor(diffMs / 1000);
      const diffMins = Math.floor(diffSecs / 60);
      const diffHours = Math.floor(diffMins / 60);

      if (diffSecs < 60) return 'Just now';
      if (diffMins < 60) return `${diffMins}m ago`;
      if (diffHours < 24) return `${diffHours}h ago`;
      return date.toLocaleDateString();
    } catch {
      return timestamp;
    }
  };

  // External notification channels (preserved from previous version)
  const channels = [
    { id: 'slack', name: 'Slack', icon: MessageSquare, color: 'text-purple-400', status: 'connected' },
    { id: 'discord', name: 'Discord', icon: MessageSquare, color: 'text-indigo-400', status: 'disconnected' },
    { id: 'whatsapp', name: 'WhatsApp', icon: MessageSquare, color: 'text-green-500', status: 'disconnected' },
    { id: 'email', name: 'Email', icon: Mail, color: 'text-red-400', status: 'disconnected' },
    { id: 'pagerduty', name: 'PagerDuty', icon: ShieldAlert, color: 'text-green-400', status: 'disconnected' },
  ];

  const renderNotificationCard = (n: AppNotification) => (
    <div
      key={n.id}
      className={`flex flex-col sm:flex-row sm:items-start justify-between p-4 rounded-xl border transition-all gap-4 ${
        n.read
          ? 'bg-surface/30 border-border-subtle opacity-75 hover:opacity-100 hover:bg-surface/50'
          : 'bg-surface/70 border-accent/40 shadow-sm ring-1 ring-accent/15'
      }`}
    >
      <div className="flex items-start gap-3.5 min-w-0 flex-1">
        <div className={`p-2 rounded-lg bg-surface-elevated border shrink-0 mt-0.5 ${
          n.severity === 'error' ? 'border-rose-500/30' : n.severity === 'warning' ? 'border-amber-500/30' : 'border-border-subtle'
        }`}>
          {getSeverityIcon(n.severity)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`text-xs font-semibold ${n.read ? 'text-gray-300' : 'text-white font-bold'}`}>
              {n.title}
            </span>
            {n.connector && (
              <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-accent/15 text-accent font-semibold">
                {n.connector}
              </span>
            )}
            {!n.read && (
              <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
            )}
          </div>
          <p className="text-[11px] text-gray-300 font-mono mt-1 leading-relaxed">
            {n.message}
          </p>
          <div className="flex items-center gap-3 mt-2 text-[10px] text-gray-500 font-mono">
            <span>{formatRelativeTime(n.timestamp)}</span>
            <span>•</span>
            <span>{new Date(n.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
          </div>
        </div>
      </div>

      {/* Action Links (B6) */}
      <div className="flex items-center gap-2 shrink-0 sm:self-center">
        {n.connector && (
          <button
            onClick={() => openChat({ connectorId: n.connector })}
            className="flex items-center gap-1 text-[11px] text-accent hover:text-accent-light px-2.5 py-1.5 rounded-lg bg-accent/10 border border-accent/20 hover:border-accent/40 font-semibold transition-all cursor-pointer"
          >
            <Sparkles size={12} />
            <span>Investigate</span>
          </button>
        )}
        <button
          onClick={() => setActiveTab('dashboard')}
          className="flex items-center gap-1 text-[11px] text-gray-300 hover:text-white px-2.5 py-1.5 rounded-lg bg-surface border border-border-subtle hover:border-border font-medium transition-all cursor-pointer"
        >
          <ExternalLink size={12} />
          <span>Dashboard</span>
        </button>
        {!n.read && (
          <button
            onClick={() => markAsRead(n.id)}
            className="text-[11px] text-gray-400 hover:text-white px-2.5 py-1.5 rounded-lg hover:bg-surface-elevated font-medium transition-colors cursor-pointer"
          >
            Mark read
          </button>
        )}
      </div>
    </div>
  );

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-6">
      {/* Header & Tabs */}
      <div className="flex flex-wrap justify-between items-center gap-4 border-b border-border-subtle pb-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white mb-1 flex items-center gap-3">
            Notifications & Alerts
            {unreadCount > 0 && (
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-accent/20 text-accent font-mono font-bold">
                {unreadCount} unread
              </span>
            )}
          </h1>
          <p className="text-sm text-gray-400">
            Real-time infrastructure incidents, watcher alarms, and alert channel routing.
          </p>
        </div>

        {/* View Switcher Tabs */}
        <div className="flex items-center gap-1 p-1 bg-surface border border-border-subtle rounded-xl text-xs font-semibold">
          <button
            onClick={() => setActiveView('alerts')}
            className={`px-4 py-2 rounded-lg transition-all cursor-pointer flex items-center gap-2 ${
              activeView === 'alerts'
                ? 'bg-surface-elevated text-accent shadow'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            <Bell size={14} />
            Incident Center ({notifications.length})
          </button>
          <button
            onClick={() => setActiveView('channels')}
            className={`px-4 py-2 rounded-lg transition-all cursor-pointer flex items-center gap-2 ${
              activeView === 'channels'
                ? 'bg-surface-elevated text-accent shadow'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            <Sliders size={14} />
            Alert Channels
          </button>
        </div>
      </div>

      {/* VIEW 1: IN-APP ALERTS (NOTIFICATION CENTER) */}
      {activeView === 'alerts' && (
        <div className="space-y-6">
          {/* Controls Bar */}
          <div className="flex flex-wrap justify-between items-center gap-4">
            <div className="flex flex-wrap items-center gap-3">
              {/* Severity Filter Pills */}
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-gray-500 font-mono mr-1">Filter:</span>
                {[
                  { id: 'all', label: 'All' },
                  { id: 'unread', label: 'Unread' },
                  { id: 'error', label: 'Critical' },
                  { id: 'warning', label: 'Warning' },
                  { id: 'info', label: 'Info' },
                ].map(f => (
                  <button
                    key={f.id}
                    onClick={() => setSeverityFilter(f.id)}
                    className={`px-3 py-1 rounded-lg text-xs font-semibold capitalize transition-all cursor-pointer ${
                      severityFilter === f.id
                        ? 'bg-accent text-gray-950 shadow'
                        : 'bg-surface text-gray-400 hover:text-white border border-border-subtle hover:border-border'
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>

              {/* Search Bar */}
              <div className="relative">
                <Search size={13} className="absolute left-2.5 top-2 text-gray-500" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  placeholder="Search alerts..."
                  className="bg-surface border border-border-subtle rounded-lg pl-7 pr-2.5 py-1 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-accent"
                />
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex items-center gap-2">
              <button
                onClick={refresh}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface hover:bg-surface-elevated border border-border-subtle text-xs font-semibold text-gray-300 hover:text-white transition-all cursor-pointer"
              >
                <RotateCcw size={13} />
                <span>Refresh</span>
              </button>
              {unreadCount > 0 && (
                <button
                  onClick={markAllAsRead}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface hover:bg-surface-elevated border border-border-subtle text-xs font-semibold text-gray-300 hover:text-white transition-all cursor-pointer"
                >
                  <CheckCheck size={14} />
                  <span>Mark all read</span>
                </button>
              )}
              {notifications.length > 0 && (
                <button
                  onClick={clearAll}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface hover:bg-rose-500/10 border border-border-subtle hover:border-rose-500/30 text-xs font-semibold text-gray-400 hover:text-rose-400 transition-all cursor-pointer"
                >
                  <Trash2 size={14} />
                  <span>Clear all</span>
                </button>
              )}
            </div>
          </div>

          {/* Notifications Content */}
          <div className="glass-panel rounded-2xl p-6 border border-border-subtle shadow-xl space-y-6">
            {filteredNotifications.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-20 text-center text-gray-500">
                <div className="w-12 h-12 rounded-2xl bg-surface-elevated flex items-center justify-center mb-3 text-gray-400 border border-border-subtle">
                  <Bell size={24} />
                </div>
                <span className="text-sm font-medium text-gray-300">No alerts or incidents found</span>
                <span className="text-xs text-gray-500 mt-1 max-w-sm">
                  {searchQuery || severityFilter !== 'all'
                    ? 'No notifications match your active filter criteria.'
                    : 'Active watcher alarms and operational incidents will appear here in real time.'}
                </span>
              </div>
            ) : (
              <div className="space-y-6">
                {/* B4: NEW Group (Unread) */}
                {newNotifications.length > 0 && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between border-b border-border-subtle pb-2">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold uppercase tracking-wider text-accent">
                          New Alerts
                        </span>
                        <span className="px-1.5 py-0.2 rounded-full bg-accent/20 text-accent text-[10px] font-mono font-bold">
                          {newNotifications.length}
                        </span>
                      </div>
                      <span className="text-[10px] text-gray-500 font-mono">Unread</span>
                    </div>
                    <div className="space-y-2.5">
                      {newNotifications.map(renderNotificationCard)}
                    </div>
                  </div>
                )}

                {/* B4: EARLIER Group (Read) */}
                {earlierNotifications.length > 0 && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between border-b border-border-subtle pb-2">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold uppercase tracking-wider text-gray-400">
                          Earlier
                        </span>
                        <span className="px-1.5 py-0.2 rounded-full bg-surface-elevated text-gray-400 text-[10px] font-mono">
                          {earlierNotifications.length}
                        </span>
                      </div>
                      <span className="text-[10px] text-gray-500 font-mono">Acknowledged</span>
                    </div>
                    <div className="space-y-2.5">
                      {earlierNotifications.map(renderNotificationCard)}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* VIEW 2: ROUTING CHANNELS */}
      {activeView === 'channels' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <div className="space-y-4">
            <h2 className="text-base font-bold text-white">Configured Alert Channels</h2>
            {channels.map((item) => {
              const Icon = item.icon;
              return (
                <div key={item.id} className="glass-card flex items-center justify-between p-5 rounded-2xl border border-border-subtle">
                  <div className="flex items-center gap-4">
                    <div className={`p-3 rounded-xl bg-surface-elevated border border-border-subtle ${item.color}`}>
                      <Icon size={22} />
                    </div>
                    <div>
                      <h3 className="text-sm font-bold text-white">{item.name}</h3>
                      <p className="text-xs text-gray-500">{item.status === 'connected' ? 'Active & Receiving Alerts' : 'Not configured'}</p>
                    </div>
                  </div>
                  <button
                    onClick={() => setActiveTab('settings')}
                    className={`px-4 py-2 rounded-xl font-semibold text-xs transition-colors cursor-pointer ${
                      item.status === 'connected'
                        ? 'bg-surface hover:bg-surface-elevated text-gray-200 border border-border-subtle'
                        : 'bg-accent text-gray-950 hover:bg-accent-light'
                    }`}
                  >
                    {item.status === 'connected' ? 'Manage' : 'Configure in Settings'}
                  </button>
                </div>
              );
            })}
          </div>

          <div>
            <h2 className="text-base font-bold text-white mb-4">Routing Rules</h2>
            <div className="glass-card p-6 rounded-2xl border border-border-subtle flex flex-col items-center text-center justify-center min-h-[300px]">
              <Bell size={40} className="text-gray-600 mb-3" />
              <h3 className="text-sm font-bold text-white mb-1">No routing rules created</h3>
              <p className="text-xs text-gray-500 mb-5 max-w-sm">
                Create rules to dispatch critical alerts (e.g. P0 production failures) to dedicated channels like PagerDuty or Slack.
              </p>
              <button
                onClick={() => setActiveTab('settings')}
                className="px-4 py-2 bg-surface hover:bg-surface-elevated border border-border-subtle hover:border-accent/40 rounded-xl text-white text-xs font-semibold transition-all cursor-pointer"
              >
                Configure Routing in Settings
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
