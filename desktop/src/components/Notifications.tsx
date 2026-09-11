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
} from 'lucide-react';
import useNotifications from '../hooks/useNotifications';

export default function Notifications() {
  const {
    notifications,
    unreadCount,
    markAsRead,
    markAllAsRead,
    clearAll,
  } = useNotifications();

  const [activeView, setActiveView] = useState<'alerts' | 'channels'>('alerts');
  const [severityFilter, setSeverityFilter] = useState<string>('all');

  const filteredNotifications = notifications.filter(n => {
    if (severityFilter === 'unread') return !n.read;
    if (severityFilter === 'error') return n.severity === 'error';
    if (severityFilter === 'warning') return n.severity === 'warning';
    return true;
  });

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

  // Notification routing channels list (preserved from previous version)
  const channels = [
    { id: 'slack', name: 'Slack', icon: MessageSquare, color: 'text-purple-400', status: 'connected' },
    { id: 'discord', name: 'Discord', icon: MessageSquare, color: 'text-indigo-400', status: 'disconnected' },
    { id: 'whatsapp', name: 'WhatsApp', icon: MessageSquare, color: 'text-green-500', status: 'disconnected' },
    { id: 'email', name: 'Email', icon: Mail, color: 'text-red-400', status: 'disconnected' },
    { id: 'pagerduty', name: 'PagerDuty', icon: ShieldAlert, color: 'text-green-400', status: 'disconnected' },
  ];

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
            In-App Alerts ({notifications.length})
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
            Routing Channels
          </button>
        </div>
      </div>

      {/* VIEW 1: IN-APP ALERTS */}
      {activeView === 'alerts' && (
        <div className="space-y-6">
          {/* Controls Bar */}
          <div className="flex flex-wrap justify-between items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500 font-mono">Filter:</span>
              {['all', 'unread', 'error', 'warning'].map(f => (
                <button
                  key={f}
                  onClick={() => setSeverityFilter(f)}
                  className={`px-3 py-1 rounded-lg text-xs font-semibold capitalize transition-all cursor-pointer ${
                    severityFilter === f
                      ? 'bg-accent text-gray-950 shadow'
                      : 'bg-surface text-gray-400 hover:text-white border border-border-subtle'
                  }`}
                >
                  {f}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-3">
              {unreadCount > 0 && (
                <button
                  onClick={markAllAsRead}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface hover:bg-surface-elevated border border-border-subtle text-xs font-semibold text-gray-300 hover:text-white transition-all cursor-pointer"
                >
                  <CheckCheck size={14} />
                  Mark all read
                </button>
              )}
              {notifications.length > 0 && (
                <button
                  onClick={clearAll}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface hover:bg-rose-500/10 border border-border-subtle hover:border-rose-500/30 text-xs font-semibold text-gray-400 hover:text-rose-400 transition-all cursor-pointer"
                >
                  <Trash2 size={14} />
                  Clear all
                </button>
              )}
            </div>
          </div>

          {/* Notifications List */}
          <div className="glass-panel rounded-2xl p-6 border border-border-subtle shadow-xl">
            {filteredNotifications.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-20 text-center text-gray-500">
                <Bell size={36} className="mb-3 text-gray-600" />
                <span className="text-sm font-medium text-gray-300">No notifications found</span>
                <span className="text-xs text-gray-600 mt-1">
                  Active watcher alerts and incident events will appear here in real time.
                </span>
              </div>
            ) : (
              <div className="space-y-3">
                {filteredNotifications.map(n => (
                  <div
                    key={n.id}
                    className={`flex items-start justify-between p-4 rounded-xl border transition-all ${
                      n.read
                        ? 'bg-surface/30 border-border-subtle opacity-75'
                        : 'bg-surface/70 border-accent/30 shadow-sm'
                    }`}
                  >
                    <div className="flex items-start gap-3.5">
                      <div className="p-2 rounded-lg bg-surface-elevated border border-border-subtle mt-0.5">
                        {getSeverityIcon(n.severity)}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className={`text-xs font-semibold ${n.read ? 'text-gray-300' : 'text-white'}`}>
                            {n.title}
                          </span>
                          {n.connector && (
                            <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-accent/15 text-accent">
                              {n.connector}
                            </span>
                          )}
                          {!n.read && (
                            <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
                          )}
                        </div>
                        <p className="text-[11px] text-gray-400 font-mono mt-1">
                          {n.message}
                        </p>
                        <span className="text-[10px] text-gray-500 font-mono mt-1 block">
                          {new Date(n.timestamp).toLocaleString()}
                        </span>
                      </div>
                    </div>

                    {!n.read && (
                      <button
                        onClick={() => markAsRead(n.id)}
                        className="text-xs text-accent hover:underline shrink-0 font-medium px-2 py-1 rounded bg-accent/10 cursor-pointer"
                      >
                        Mark read
                      </button>
                    )}
                  </div>
                ))}
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
                  <button className={`px-4 py-2 rounded-xl font-semibold text-xs transition-colors cursor-pointer ${
                    item.status === 'connected'
                      ? 'bg-surface hover:bg-surface-elevated text-gray-200 border border-border-subtle'
                      : 'bg-accent text-gray-950 hover:bg-accent-light'
                  }`}>
                    {item.status === 'connected' ? 'Manage' : 'Connect'}
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
              <button className="px-4 py-2 bg-surface hover:bg-surface-elevated border border-border-subtle hover:border-accent/40 rounded-xl text-white text-xs font-semibold transition-all cursor-pointer">
                Create Rule
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
