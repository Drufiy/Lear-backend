import React from 'react';
import { AlertCircle, CheckCircle2, Info, Bell } from 'lucide-react';

export interface TimelineEvent {
  timestamp: string;
  connector?: string;
  event_type: string;
  summary: string;
  severity?: 'info' | 'warning' | 'error' | 'success';
}

interface EventTimelineProps {
  events: TimelineEvent[];
  label?: string;
  maxItems?: number;
}

export const EventTimeline: React.FC<EventTimelineProps> = ({
  events = [],
  label = 'Operational Timeline',
  maxItems = 5,
}) => {
  const displayEvents = events.slice(0, maxItems);

  const getIcon = (ev: TimelineEvent) => {
    const type = (ev.event_type || '').toLowerCase();
    const summary = (ev.summary || '').toLowerCase();

    if (type.includes('fail') || type.includes('error') || summary.includes('alarm') || summary.includes('error')) {
      return <AlertCircle size={14} className="text-rose-400" />;
    }
    if (type.includes('restart') || type.includes('warn') || summary.includes('warn')) {
      return <Bell size={14} className="text-amber-400" />;
    }
    if (type.includes('reboot') || type.includes('deploy') || summary.includes('success')) {
      return <CheckCircle2 size={14} className="text-accent" />;
    }
    return <Info size={14} className="text-cyan-400" />;
  };

  return (
    <div className="flex flex-col p-4 w-full">
      <div className="flex justify-between items-center mb-3">
        <span className="text-xs font-semibold uppercase tracking-wider text-gray-400">{label}</span>
        <span className="text-[11px] text-gray-500 font-mono">{events.length} events</span>
      </div>

      {displayEvents.length === 0 ? (
        <div className="flex items-center justify-center py-6 text-xs text-gray-500 font-mono">
          No recent events recorded
        </div>
      ) : (
        <div className="relative pl-4 space-y-3 before:absolute before:left-1.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-border-subtle">
          {displayEvents.map((ev, i) => (
            <div key={i} className="relative flex items-start gap-3 text-xs">
              <div className="absolute -left-4 mt-0.5 w-3 h-3 rounded-full bg-surface border border-border-subtle flex items-center justify-center">
                {getIcon(ev)}
              </div>
              <div className="flex-1 flex flex-col">
                <span className="font-medium text-gray-200">{ev.summary || ev.event_type}</span>
                <span className="text-[10px] text-gray-500 font-mono mt-0.5">
                  {ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''}
                  {ev.connector ? ` • ${ev.connector}` : ''}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default EventTimeline;
