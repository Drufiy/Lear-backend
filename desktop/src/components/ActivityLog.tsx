import { useState } from 'react';
import { Activity, Filter, Clock } from 'lucide-react';
import useWatcher from '../hooks/useWatcher';

export default function ActivityLog() {
  const { events } = useWatcher();
  const [filter, setFilter] = useState<string>('all');

  const filteredEvents = events.filter(ev => {
    if (filter === 'all') return true;
    return (ev.connector || '').toLowerCase() === filter.toLowerCase();
  });

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-6">
      <div className="flex flex-wrap justify-between items-center gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white mb-1">Activity & Audit Log</h1>
          <p className="text-sm text-gray-400">
            Real-time event stream captured by the Lear Watcher across all monitored services.
          </p>
        </div>

        {/* Filter buttons */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500 font-mono flex items-center gap-1">
            <Filter size={12} /> Filter:
          </span>
          {['all', 'aws', 'github', 'datadog'].map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1 rounded-lg text-xs font-semibold capitalize transition-all cursor-pointer ${
                filter === f
                  ? 'bg-accent text-gray-950 shadow'
                  : 'bg-surface text-gray-400 hover:text-white border border-border-subtle'
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      <div className="glass-panel rounded-2xl p-6 border border-border-subtle shadow-xl">
        {filteredEvents.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center text-gray-500">
            <Clock size={32} className="mb-2 text-gray-600" />
            <span className="text-sm font-medium">No activity events recorded yet</span>
            <span className="text-xs text-gray-600 mt-1">Start watching a service to stream events in real time.</span>
          </div>
        ) : (
          <div className="space-y-3">
            {filteredEvents.map((ev, i) => (
              <div
                key={i}
                className="flex items-start justify-between p-4 rounded-xl bg-surface/50 border border-border-subtle hover:border-border-hover transition-colors"
              >
                <div className="flex items-start gap-3">
                  <div className="p-2 rounded-lg bg-surface-elevated border border-border-subtle text-accent mt-0.5">
                    <Activity size={16} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-xs text-white">{ev.summary || ev.event_type}</span>
                      {ev.connector && (
                        <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-accent/15 text-accent">
                          {ev.connector}
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] text-gray-400 font-mono mt-1">
                      Event Type: {ev.event_type}
                    </p>
                  </div>
                </div>

                <span className="text-[11px] text-gray-500 font-mono shrink-0">
                  {new Date(ev.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
