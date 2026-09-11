import React from 'react';
import { ArrowUpRight, ArrowDownRight } from 'lucide-react';

interface MetricCardProps {
  label: string;
  value: string | number;
  unit?: string;
  change?: number; // e.g. +4.2 or -1.5
  history?: number[]; // for sparkline
  icon?: React.ReactNode;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  label,
  value,
  unit = '',
  change,
  history,
  icon,
}) => {
  const isPositive = (change || 0) >= 0;

  // Render miniature sparkline only when real historical data exists
  const hasHistory = history && history.length >= 2;
  let points = '';
  const width = 80;
  const height = 28;

  if (hasHistory) {
    const min = Math.min(...history);
    const max = Math.max(...history, 1);
    points = history.map((val, i) => {
      const x = (i / (history.length - 1)) * width;
      const y = height - ((val - min) / (max - min || 1)) * (height - 4) - 2;
      return `${x},${y}`;
    }).join(' ');
  }

  return (
    <div className="glass-card rounded-xl p-4 flex flex-col justify-between">
      <div className="flex items-center justify-between text-gray-400 mb-2">
        <span className="text-xs font-semibold uppercase tracking-wider">{label}</span>
        {icon && <div className="text-gray-400">{icon}</div>}
      </div>

      <div className="flex items-baseline justify-between mt-1">
        <div className="flex items-baseline gap-1">
          <span className="text-2xl font-bold tracking-tight text-white">{value}</span>
          {unit && <span className="text-xs font-medium text-gray-400">{unit}</span>}
        </div>

        {/* Sparkline */}
        {hasHistory && (
          <div className="w-20 h-7 overflow-visible">
            <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-full overflow-visible">
              <polyline
                fill="none"
                stroke={isPositive ? '#10B981' : '#F43F5E'}
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                points={points}
              />
            </svg>
          </div>
        )}
      </div>

      {change !== undefined && (
        <div className="flex items-center gap-1 mt-2 text-[11px] font-medium">
          {isPositive ? (
            <span className="flex items-center text-accent">
              <ArrowUpRight size={14} /> +{change.toFixed(1)}%
            </span>
          ) : (
            <span className="flex items-center text-rose-400">
              <ArrowDownRight size={14} /> {change.toFixed(1)}%
            </span>
          )}
          <span className="text-gray-500 ml-1">vs previous cycle</span>
        </div>
      )}
    </div>
  );
};

export default MetricCard;
