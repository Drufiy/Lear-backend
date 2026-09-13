import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Radio,
  Play,
  Square,
  AlertTriangle,
  Clock,
  Pause,
  ChevronDown,
  Layers,
  X
} from 'lucide-react';
import { WatcherState, ActiveWatchDetail } from '../hooks/useWatcher';

interface WatcherPanelProps {
  state: WatcherState;
  activeCount: number;
  eventCount: number;
  isConnected: boolean;
  activeDetails?: ActiveWatchDetail[];
  onToggleWatch?: (interval: number) => void;
  onPauseWatch?: (watchId: string) => void;
  onResumeWatch?: (watchId: string) => void;
  onStopWatch?: (connectorId: string, target?: string, watchId?: string) => void;
}

export const WatcherPanel: React.FC<WatcherPanelProps> = ({
  state,
  activeCount,
  eventCount,
  isConnected,
  activeDetails = [],
  onToggleWatch,
  onPauseWatch,
  onResumeWatch,
  onStopWatch,
}) => {
  const [interval, setInterval] = useState<number>(5);
  const [countdown, setCountdown] = useState<number>(interval);
  const [showDetails, setShowDetails] = useState<boolean>(false);

  // Sync countdown whenever interval changes
  useEffect(() => {
    setCountdown(interval);
  }, [interval]);

  // Next poll countdown timer active during live watching
  useEffect(() => {
    if (state !== 'ACTIVE' && state !== 'ALERTING' && state !== 'DEGRADED') {
      setCountdown(interval);
      return;
    }

    const timer = window.setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) {
          return interval;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [state, interval]);

  // Reset countdown whenever event count increments
  useEffect(() => {
    if (eventCount > 0) {
      setCountdown(interval);
    }
  }, [eventCount, interval]);

  const getStateBadge = () => {
    switch (state) {
      case 'ACTIVE':
        return (
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="flex items-center gap-2 px-3 py-1 bg-accent/15 border border-accent/30 text-accent rounded-full text-xs font-semibold"
          >
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-accent" />
            </span>
            LIVE MONITORING ACTIVE
          </motion.div>
        );
      case 'ALERTING':
        return (
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="flex items-center gap-2 px-3 py-1 bg-rose-500/15 border border-rose-500/30 text-rose-400 rounded-full text-xs font-semibold animate-pulse"
          >
            <AlertTriangle size={14} className="animate-bounce" />
            CRITICAL ALERT DETECTED
          </motion.div>
        );
      case 'DEGRADED':
        return (
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="flex items-center gap-2 px-3 py-1 bg-amber-500/15 border border-amber-500/30 text-amber-400 rounded-full text-xs font-semibold"
          >
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping" />
            DEGRADED TELEMETRY
          </motion.div>
        );
      case 'STARTING':
        return (
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="flex items-center gap-2 px-3 py-1 bg-amber-500/15 border border-amber-500/30 text-amber-400 rounded-full text-xs font-semibold"
          >
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-spin" />
            CONNECTING WATCHER...
          </motion.div>
        );
      default:
        return (
          <div className="flex items-center gap-2 px-3 py-1 bg-surface border border-border-subtle text-gray-400 rounded-full text-xs font-semibold">
            <span className="w-2 h-2 rounded-full bg-gray-500" />
            STANDBY / IDLE
          </div>
        );
    }
  };

  const isLive = state === 'ACTIVE' || state === 'ALERTING' || state === 'DEGRADED';

  return (
    <div className="glass-panel rounded-2xl p-5 border border-border-subtle shadow-xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        {/* Left: Indicator & Status */}
        <div className="flex items-center gap-4">
          <div className="relative">
            <div className="p-3 bg-surface rounded-xl border border-border-subtle flex items-center justify-center text-accent">
              <Radio size={22} className={isLive ? 'animate-pulse text-accent' : 'text-gray-400'} />
            </div>
            {/* Dynamic radar ripple wave */}
            {isLive && (
              <span className="absolute -inset-1 rounded-2xl bg-accent/20 animate-ping pointer-events-none" />
            )}
          </div>
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-base font-bold text-white tracking-tight">Lear Real-Time Watcher</h2>
              {getStateBadge()}
            </div>
            <p className="text-xs text-gray-400 mt-1">
              Continuous background telemetry stream • {isConnected ? 'WebSocket Connected' : 'Connecting to bridge...'}
            </p>
          </div>
        </div>

        {/* Right: Metrics & Controls */}
        <div className="flex items-center gap-6">
          {/* Next Poll Countdown */}
          {isLive && (
            <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-xl bg-surface border border-border-subtle text-xs font-mono text-gray-300">
              <Clock size={13} className="text-accent animate-spin" />
              <span>Next poll in</span>
              <span className="text-accent font-bold">{countdown}s</span>
            </div>
          )}

          {/* Counts */}
          <div className="flex items-center gap-4 text-xs font-mono">
            <button
              onClick={() => setShowDetails(!showDetails)}
              className="flex flex-col items-end hover:opacity-80 transition-opacity cursor-pointer text-left"
              title="Click to view active watch handles"
            >
              <span className="text-gray-400 flex items-center gap-1">
                Active Handles <ChevronDown size={11} className={`transition-transform ${showDetails ? 'rotate-180' : ''}`} />
              </span>
              <span className="text-white font-bold text-sm">{activeCount}</span>
            </button>
            <div className="w-px h-7 bg-border-subtle" />
            <div className="flex flex-col items-end">
              <span className="text-gray-400">Events Streamed</span>
              <span className="text-accent font-bold text-sm">{eventCount}</span>
            </div>
          </div>

          {/* Controls */}
          {onToggleWatch && (
            <div className="flex items-center gap-3">
              <select
                value={interval}
                onChange={(e) => setInterval(Number(e.target.value))}
                disabled={isLive}
                className="bg-surface border border-border-subtle rounded-xl px-3 py-1.5 text-xs text-white outline-none focus:border-accent disabled:opacity-50"
              >
                <option value={5}>5s interval</option>
                <option value={15}>15s interval</option>
                <option value={30}>30s interval</option>
                <option value={60}>60s interval</option>
              </select>

              <button
                onClick={() => onToggleWatch(interval)}
                className={`flex items-center gap-2 px-4 py-2 rounded-xl font-semibold text-xs transition-all cursor-pointer shadow-lg ${
                  isLive
                    ? 'bg-rose-500/20 hover:bg-rose-500/30 text-rose-400 border border-rose-500/30'
                    : 'bg-accent text-gray-950 hover:bg-accent-light'
                }`}
              >
                {isLive ? (
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
      </div>

      {/* Active Watch Handles Drawer */}
      <AnimatePresence>
        {showDetails && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="pt-4 border-t border-border-subtle overflow-hidden"
          >
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2 text-xs font-semibold text-gray-300">
                <Layers size={14} className="text-accent" />
                <span>Monitored Handles ({activeDetails.length})</span>
              </div>
              <button
                onClick={() => setShowDetails(false)}
                className="text-gray-400 hover:text-white p-1 rounded-lg"
              >
                <X size={13} />
              </button>
            </div>

            {activeDetails.length === 0 ? (
              <div className="p-4 rounded-xl bg-surface text-center text-xs text-gray-400">
                No individual handles active. Click "Start Watching" or enable monitoring on service widgets below.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {activeDetails.map(w => (
                  <div
                    key={w.watch_id}
                    className="p-3 rounded-xl bg-surface border border-border-subtle flex items-center justify-between gap-3 text-xs"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-white uppercase tracking-wider text-[10px] bg-white/10 px-1.5 py-0.5 rounded">
                          {w.connector}
                        </span>
                        <span className="text-gray-300 truncate font-mono">{w.target}</span>
                      </div>
                      <div className="flex items-center gap-2 mt-1 text-[11px] text-gray-400">
                        <span className={`w-1.5 h-1.5 rounded-full ${
                          w.status === 'healthy' ? 'bg-accent' :
                          w.status === 'paused' ? 'bg-gray-400' :
                          w.status === 'degraded' ? 'bg-amber-400' : 'bg-rose-400'
                        }`} />
                        <span className="capitalize">{w.status}</span>
                        <span>•</span>
                        <span>{w.interval}s interval</span>
                      </div>
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0">
                      {w.status === 'paused' ? (
                        onResumeWatch && (
                          <button
                            onClick={() => onResumeWatch(w.watch_id)}
                            className="p-1.5 rounded-lg bg-surface-elevated hover:bg-white/10 text-accent transition-colors"
                            title="Resume Watch"
                          >
                            <Play size={13} />
                          </button>
                        )
                      ) : (
                        onPauseWatch && (
                          <button
                            onClick={() => onPauseWatch(w.watch_id)}
                            className="p-1.5 rounded-lg bg-surface-elevated hover:bg-white/10 text-amber-400 transition-colors"
                            title="Pause Watch"
                          >
                            <Pause size={13} />
                          </button>
                        )
                      )}

                      {onStopWatch && (
                        <button
                          onClick={() => onStopWatch(w.connector, w.target, w.watch_id)}
                          className="p-1.5 rounded-lg bg-surface-elevated hover:bg-rose-500/20 text-gray-400 hover:text-rose-400 transition-colors"
                          title="Stop Watch"
                        >
                          <Square size={13} />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default WatcherPanel;
