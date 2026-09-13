import React from 'react';
import { Radio, Play, Square, AlertTriangle, Activity, Clock } from 'lucide-react';
import { WatcherState } from '../hooks/useWatcher';
import { WebSocketEvent } from '../hooks/useWebSocket';

interface WatcherPanelProps {
  state: WatcherState;
  activeCount: number;
  eventCount: number;
  isConnected: boolean;
  onToggleWatch?: (interval: number) => void;
  recentEvents?: WebSocketEvent[];
}

export const WatcherPanel: React.FC<WatcherPanelProps> = ({
  state,
  activeCount,
  eventCount,
  isConnected,
  onToggleWatch,
  recentEvents = [],
}) => {
  const [interval, setInterval] = React.useState<number>(5);
  const [nextPollIn, setNextPollIn] = React.useState<number>(0);

  // Countdown timer for next poll
  React.useEffect(() => {
    if (state !== 'ACTIVE' && state !== 'ALERTING') {
      setNextPollIn(0);
      return;
    }
    setNextPollIn(interval);
    const pollTimer = window.setInterval(() => {
      setNextPollIn(prev => (prev > 0 ? prev - 1 : interval));
    }, 1000);
    return () => window.clearInterval(pollTimer);
  }, [state, interval]);

  const getStateBadge = () => {
    switch (state) {
      case 'ACTIVE':
        return (
          <div className="flex items-center gap-2 px-3 py-1 bg-accent/15 border border-accent/30 text-accent rounded-full text-xs font-semibold transition-all duration-300">
            <span className="w-2 h-2 rounded-full bg-accent pulse-radar animate-pulse" />
            LIVE MONITORING ACTIVE
          </div>
        );
      case 'ALERTING':
        return (
          <div className="flex items-center gap-2 px-3 py-1 bg-rose-500/15 border border-rose-500/30 text-rose-400 rounded-full text-xs font-semibold animate-pulse transition-all duration-300">
            <AlertTriangle size={14} className="animate-bounce" />
            CRITICAL ALERT DETECTED
          </div>
        );
      case 'STARTING':
        return (
          <div className="flex items-center gap-2 px-3 py-1 bg-amber-500/15 border border-amber-500/30 text-amber-400 rounded-full text-xs font-semibold transition-all duration-300">
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-spin" />
            CONNECTING WATCHER...
          </div>
        );
      case 'DEGRADED':
        return (
          <div className="flex items-center gap-2 px-3 py-1 bg-amber-500/15 border border-amber-500/30 text-amber-400 rounded-full text-xs font-semibold transition-all duration-300">
            <Activity size={14} className="animate-pulse" />
            DEGRADED
          </div>
        );
      case 'ERROR':
        return (
          <div className="flex items-center gap-2 px-3 py-1 bg-rose-500/15 border border-rose-500/30 text-rose-400 rounded-full text-xs font-semibold transition-all duration-300">
            <AlertTriangle size={14} />
            WATCHER ERROR
          </div>
        );
      default:
        return (
          <div className="flex items-center gap-2 px-3 py-1 bg-surface border border-border-subtle text-gray-400 rounded-full text-xs font-semibold transition-all duration-300">
            <span className="w-2 h-2 rounded-full bg-gray-500" />
            STANDBY / IDLE
          </div>
        );
    }
  };

  const getEventSeverity = (event: WebSocketEvent) => {
    const type = (event.event_type || '').toLowerCase();
    if (type.includes('fail') || type.includes('error') || type.includes('alarm')) return 'text-rose-400';
    if (type.includes('warn') || type.includes('spike')) return 'text-amber-400';
    return 'text-gray-300';
  };

  return (
    <div className="glass-panel rounded-2xl p-5 flex flex-wrap items-center justify-between gap-4 border border-border-subtle shadow-xl">
      <div className="flex items-center gap-4">
        <div className="p-3 bg-surface rounded-xl border border-border-subtle flex items-center justify-center text-accent">
          <Radio size={22} className={state === 'ACTIVE' ? 'animate-pulse text-accent' : 'text-gray-400'} />
        </div>
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-base font-bold text-white tracking-tight">Lear Real-Time Watcher</h2>
            {getStateBadge()}
          </div>
          <p className="text-xs text-gray-400 mt-1">
            Continuous background telemetry stream • {isConnected ? (
              <span className="text-emerald-400">WebSocket Connected</span>
            ) : (
              <span className="text-amber-400">Connecting to bridge...</span>
            )}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-6">
        <div className="flex items-center gap-4 text-xs font-mono">
          <div className="flex flex-col items-end">
            <span className="text-gray-400">Active Handles</span>
            <span className="text-white font-bold text-sm">{activeCount}</span>
          </div>
          <div className="w-px h-7 bg-border-subtle" />
          <div className="flex flex-col items-end">
            <span className="text-gray-400">Events Streamed</span>
            <span className="text-accent font-bold text-sm">{eventCount}</span>
          </div>
          {(state === 'ACTIVE' || state === 'ALERTING') && (
            <>
              <div className="w-px h-7 bg-border-subtle" />
              <div className="flex flex-col items-end">
                <span className="text-gray-400 flex items-center gap-1"><Clock size={10} /> Next Poll</span>
                <span className="text-accent font-bold text-sm">{nextPollIn}s</span>
              </div>
            </>
          )}
        </div>

        {onToggleWatch && (
          <div className="flex items-center gap-3">
            <select
              value={interval}
              onChange={(e) => setInterval(Number(e.target.value))}
              disabled={state === 'ACTIVE'}
              className="bg-surface border border-border-subtle rounded-xl px-3 py-1.5 text-xs text-white outline-none focus:border-accent"
            >
              <option value={5}>5s</option>
              <option value={15}>15s</option>
              <option value={60}>60s</option>
            </select>
            <button
              onClick={() => onToggleWatch(interval)}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl font-semibold text-xs transition-all cursor-pointer shadow-lg ${
                state === 'ACTIVE'
                  ? 'bg-rose-500/20 hover:bg-rose-500/30 text-rose-400 border border-rose-500/30'
                  : 'bg-accent text-gray-950 hover:bg-accent-light'
              }`}
            >
              {state === 'ACTIVE' ? (
                <>
                  <Square size={14} /> Stop Watching
                </>
              ) : (
                <>
                  <Play size={14} /> Start Watching
                </>
              )}
            </button>
          </div>
        )}
      </div>

      {/* Recent Events Stream */}
      {recentEvents.length > 0 && (
        <div className="w-full mt-2 border-t border-border-subtle pt-3">
          <div className="text-xs text-gray-400 mb-2 font-semibold">Recent Events</div>
          <div className="max-h-24 overflow-y-auto space-y-1 scrollbar-thin">
            {recentEvents.slice(0, 5).map((event, idx) => (
              <div key={idx} className={`text-xs flex items-center gap-2 ${getEventSeverity(event)}`}>
                <span className="text-gray-500 font-mono">{new Date(event.timestamp).toLocaleTimeString()}</span>
                <span className="text-gray-400">•</span>
                <span className="font-medium">{event.connector || 'system'}</span>
                <span className="text-gray-500">•</span>
                <span>{event.summary || event.event_type}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default WatcherPanel;
