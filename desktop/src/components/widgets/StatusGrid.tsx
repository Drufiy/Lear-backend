import React from 'react';
import { CheckCircle2, XCircle, AlertTriangle, ShieldCheck } from 'lucide-react';

export interface StatusItem {
  id: string;
  name: string;
  status: 'healthy' | 'error' | 'warning' | 'unknown' | string;
  detail?: string;
}

interface StatusGridProps {
  items: StatusItem[];
  label?: string;
}

export const StatusGrid: React.FC<StatusGridProps> = ({
  items = [],
  label = 'Health Checks',
}) => {
  const getBadge = (status: string) => {
    const s = (status || '').toLowerCase();
    if (s === 'healthy' || s === 'passed' || s === 'running' || s === 'synced') {
      return (
        <span className="flex items-center gap-1 text-[11px] font-medium text-accent bg-accent/10 px-2 py-0.5 rounded-full">
          <CheckCircle2 size={12} /> Healthy
        </span>
      );
    }
    if (s === 'warning' || s === 'degraded' || s === 'restarting') {
      return (
        <span className="flex items-center gap-1 text-[11px] font-medium text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded-full">
          <AlertTriangle size={12} /> Warning
        </span>
      );
    }
    if (s === 'error' || s === 'failed' || s === 'crash-looping') {
      return (
        <span className="flex items-center gap-1 text-[11px] font-medium text-rose-400 bg-rose-400/10 px-2 py-0.5 rounded-full">
          <XCircle size={12} /> Error
        </span>
      );
    }
    return (
      <span className="flex items-center gap-1 text-[11px] font-medium text-gray-400 bg-gray-800/50 px-2 py-0.5 rounded-full">
        <ShieldCheck size={12} /> {status || 'Unknown'}
      </span>
    );
  };

  return (
    <div className="flex flex-col p-4 w-full">
      <span className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-3">{label}</span>
      {items.length === 0 ? (
        <div className="flex items-center justify-center py-4 text-xs text-gray-500 font-mono">
          No check items registered
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {items.map(item => (
            <div
              key={item.id}
              className="flex items-center justify-between p-2.5 rounded-lg bg-surface/50 border border-border-subtle hover:border-border-hover transition-colors"
            >
              <div className="flex flex-col">
                <span className="text-xs font-medium text-gray-200">{item.name}</span>
                {item.detail && (
                  <span className="text-[10px] text-gray-500 font-mono">
                    {typeof item.detail === 'string' ? item.detail : JSON.stringify(item.detail)}
                  </span>
                )}
              </div>
              <div>{getBadge(item.status)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default StatusGrid;
