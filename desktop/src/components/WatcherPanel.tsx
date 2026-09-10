import { Radio, Play, Square, AlertTriangle } from 'lucide-react';
import { WatcherState } from '../hooks/useWatcher';

interface WatcherPanelProps {
  state: WatcherState;
  activeCount: number;
  eventCount: number;
  isConnected: boolean;
  onToggleWatch?: () => void;
}

export const WatcherPanel: React.FC<WatcherPanelProps> = ({
  state,
  activeCount,
  eventCount,
  isConnected,
  onToggleWatch,
}) => {
  const getStateBadge = () => {
    switch (state) {
      case 'ACTIVE':
        return (
          <div className="flex items-center gap-2 px-3 py-1 bg-accent/15 border border-accent/30 text-accent rounded-full text-xs font-semibold">
            <span className="w-2 h-2 rounded-full bg-accent pulse-radar" />
            LIVE MONITORING ACTIVE
          </div>
        );
      case 'ALERTING':
        return (
          <div className="flex items-center gap-2 px-3 py-1 bg-rose-500/15 border border-rose-500/30 text-rose-400 rounded-full text-xs font-semibold animate-pulse">
            <AlertTriangle size={14} />
            CRITICAL ALERT DETECTED
          </div>
        );
      case 'STARTING':
        return (
          <div className="flex items-center gap-2 px-3 py-1 bg-amber-500/15 border border-amber-500/30 text-amber-400 rounded-full text-xs font-semibold">
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-spin" />
            CONNECTING WATCHER...
          </div>
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
            Continuous background telemetry stream • {isConnected ? 'WebSocket Connected' : 'Connecting to bridge...'}
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
        </div>

        {onToggleWatch && (
          <button
            onClick={onToggleWatch}
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
        )}
      </div>
    </div>
  );
};

export default WatcherPanel;
