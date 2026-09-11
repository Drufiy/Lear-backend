import React, { useState } from 'react';

export interface TimeSeriesPoint {
  timestamp: string;
  value: number;
}

interface MetricLineChartProps {
  data: TimeSeriesPoint[];
  label: string;
  unit?: string;
  color?: string;
  height?: number;
}

export const MetricLineChart: React.FC<MetricLineChartProps> = ({
  data = [],
  label,
  unit = '',
  color = '#FF3A89',
  height = 160,
}) => {
  const [hoveredPoint, setHoveredPoint] = useState<TimeSeriesPoint | null>(null);
  const [hoverX, setHoverX] = useState<number | null>(null);

  if (!data || data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-40 bg-surface/40 rounded-xl border border-border-subtle p-4">
        <span className="text-xs text-gray-500">No time-series data available</span>
      </div>
    );
  }

  const values = data.map(d => d.value);
  const minVal = Math.min(0, ...values);
  const maxVal = Math.max(...values, 1);
  const padding = 20;
  const width = 450;
  const chartHeight = height - padding * 2;

  // Build points for SVG
  const points = data.map((d, i) => {
    const x = padding + (i / Math.max(data.length - 1, 1)) * (width - padding * 2);
    const normalizedY = (d.value - minVal) / (maxVal - minVal || 1);
    const y = height - padding - normalizedY * chartHeight;
    return { x, y, point: d };
  });

  // Generate smooth SVG path
  const pathD = points.reduce((acc, curr, idx, arr) => {
    if (idx === 0) return `M ${curr.x},${curr.y}`;
    const prev = arr[idx - 1];
    const cp1x = prev.x + (curr.x - prev.x) / 2;
    const cp1y = prev.y;
    const cp2x = prev.x + (curr.x - prev.x) / 2;
    const cp2y = curr.y;
    return `${acc} C ${cp1x},${cp1y} ${cp2x},${cp2y} ${curr.x},${curr.y}`;
  }, '');

  // Close path for area gradient fill
  const areaD = `${pathD} L ${points[points.length - 1].x},${height - padding} L ${points[0].x},${height - padding} Z`;

  return (
    <div className="flex flex-col p-4 w-full relative">
      <div className="flex justify-between items-center mb-2">
        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">{label}</span>
        {hoveredPoint ? (
          <span className="text-xs font-mono text-accent">
            {hoveredPoint.value.toFixed(2)} {unit}
          </span>
        ) : (
          <span className="text-xs font-mono text-gray-500">
            Latest: {data[data.length - 1].value.toFixed(1)} {unit}
          </span>
        )}
      </div>

      <div className="relative w-full overflow-hidden">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full h-auto overflow-visible"
          onMouseLeave={() => {
            setHoveredPoint(null);
            setHoverX(null);
          }}
        >
          <defs>
            <linearGradient id={`areaGradient-${label}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity="0.28" />
              <stop offset="100%" stopColor={color} stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          <line x1={padding} y1={padding} x2={width - padding} y2={padding} stroke="rgba(255,255,255,0.05)" strokeDasharray="3 3" />
          <line x1={padding} y1={height / 2} x2={width - padding} y2={height / 2} stroke="rgba(255,255,255,0.05)" strokeDasharray="3 3" />
          <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke="rgba(255,255,255,0.08)" />

          {/* Area Fill */}
          <path d={areaD} fill={`url(#areaGradient-${label})`} />

          {/* Line Stroke */}
          <path d={pathD} fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />

          {/* Interactive Hover Line and Points */}
          {points.map((pt, i) => (
            <g key={i}>
              <circle
                cx={pt.x}
                cy={pt.y}
                r="3"
                fill={color}
                className="transition-all duration-150"
              />
              <rect
                x={pt.x - 10}
                y={0}
                width={20}
                height={height}
                fill="transparent"
                className="cursor-pointer"
                onMouseEnter={() => {
                  setHoveredPoint(pt.point);
                  setHoverX(pt.x);
                }}
              />
            </g>
          ))}

          {hoverX !== null && (
            <line
              x1={hoverX}
              y1={padding}
              x2={hoverX}
              y2={height - padding}
              stroke="rgba(255,255,255,0.3)"
              strokeWidth="1"
              strokeDasharray="2 2"
            />
          )}
        </svg>
      </div>

      <div className="flex justify-between items-center text-[10px] text-gray-500 font-mono mt-1 px-1">
        <span>{data[0]?.timestamp ? new Date(data[0].timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}</span>
        <span>{data[data.length - 1]?.timestamp ? new Date(data[data.length - 1].timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}</span>
      </div>
    </div>
  );
};

export default MetricLineChart;
