import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Maximize2 } from 'lucide-react';

export interface BarChartItem {
  id?: string;
  label: string;
  value: number;
  color?: string;
  unit?: string;
}

interface BarChartProps {
  data: BarChartItem[];
  label: string;
  unit?: string;
  color?: string;
  height?: number;
  onExpand?: () => void;
}

export const BarChart: React.FC<BarChartProps> = ({
  data = [],
  label,
  unit = '',
  color = '#FF3A89',
  height = 170,
  onExpand,
}) => {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  // If no data points exist
  if (!data || data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-44 bg-surface/40 rounded-xl border border-border-subtle p-4">
        <span className="text-xs text-gray-500 font-mono">No bar chart data available</span>
      </div>
    );
  }

  const values = data.map(d => d.value);
  const maxVal = Math.max(...values, 1);
  const totalVal = values.reduce((sum, v) => sum + v, 0);

  const paddingLeft = 36;
  const paddingRight = 16;
  const paddingTop = 28;
  const paddingBottom = 32;
  const width = 450;
  const chartWidth = width - paddingLeft - paddingRight;
  const chartHeight = height - paddingTop - paddingBottom;
  const chartBaseY = height - paddingBottom;

  const barCount = data.length;
  const slotWidth = chartWidth / barCount;
  const barWidth = Math.min(Math.max(slotWidth * 0.55, 14), 48);

  const hoveredItem = hoveredIdx !== null ? data[hoveredIdx] : null;

  return (
    <div className="flex flex-col p-4 w-full relative">
      {/* Header */}
      <div className="flex justify-between items-center mb-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">{label}</span>
          {onExpand && (
            <button
              onClick={onExpand}
              className="p-1 rounded text-gray-500 hover:text-white hover:bg-surface-elevated transition-colors cursor-pointer"
              title="Expand Chart View"
            >
              <Maximize2 size={12} />
            </button>
          )}
        </div>

        {hoveredItem ? (
          <div className="flex items-center gap-2 text-xs font-mono">
            <span className="text-gray-400">{hoveredItem.label}:</span>
            <span className="text-accent font-bold">
              {hoveredItem.value.toLocaleString()} {hoveredItem.unit || unit}
            </span>
            {totalVal > 0 && (
              <span className="text-[11px] text-gray-500">
                ({((hoveredItem.value / totalVal) * 100).toFixed(0)}%)
              </span>
            )}
          </div>
        ) : (
          <span className="text-xs font-mono text-gray-500">
            Total: {totalVal.toLocaleString()} {unit}
          </span>
        )}
      </div>

      {/* SVG Chart Area */}
      <div className="relative w-full overflow-hidden">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full h-auto overflow-visible"
          onMouseLeave={() => setHoveredIdx(null)}
        >
          <defs>
            {data.map((item, idx) => {
              const barColor = item.color || color;
              return (
                <linearGradient key={`grad-${idx}`} id={`barGrad-${idx}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={barColor} stopOpacity="0.95" />
                  <stop offset="100%" stopColor={barColor} stopOpacity="0.55" />
                </linearGradient>
              );
            })}
          </defs>

          {/* Grid lines & Y-axis labels */}
          <line
            x1={paddingLeft}
            y1={paddingTop}
            x2={width - paddingRight}
            y2={paddingTop}
            stroke="rgba(255,255,255,0.06)"
            strokeDasharray="3 3"
          />
          <text
            x={paddingLeft - 6}
            y={paddingTop + 3}
            textAnchor="end"
            fontSize="9"
            fill="rgba(255,255,255,0.3)"
            fontFamily="monospace"
          >
            {maxVal}
          </text>

          <line
            x1={paddingLeft}
            y1={paddingTop + chartHeight / 2}
            x2={width - paddingRight}
            y2={paddingTop + chartHeight / 2}
            stroke="rgba(255,255,255,0.06)"
            strokeDasharray="3 3"
          />
          <text
            x={paddingLeft - 6}
            y={paddingTop + chartHeight / 2 + 3}
            textAnchor="end"
            fontSize="9"
            fill="rgba(255,255,255,0.3)"
            fontFamily="monospace"
          >
            {Math.round(maxVal / 2)}
          </text>

          {/* Base baseline */}
          <line
            x1={paddingLeft}
            y1={chartBaseY}
            x2={width - paddingRight}
            y2={chartBaseY}
            stroke="rgba(255,255,255,0.12)"
          />
          <text
            x={paddingLeft - 6}
            y={chartBaseY + 3}
            textAnchor="end"
            fontSize="9"
            fill="rgba(255,255,255,0.3)"
            fontFamily="monospace"
          >
            0
          </text>

          {/* Bars */}
          {data.map((item, idx) => {
            const normalizedHeight = maxVal > 0 ? (item.value / maxVal) * chartHeight : 0;
            const barH = Math.max(normalizedHeight, item.value > 0 ? 3 : 0);
            const xCenter = paddingLeft + idx * slotWidth + slotWidth / 2;
            const barX = xCenter - barWidth / 2;
            const barY = chartBaseY - barH;
            const isHovered = hoveredIdx === idx;
            const barColor = item.color || color;

            return (
              <g
                key={`bar-${item.id || idx}`}
                className="cursor-pointer"
                onMouseEnter={() => setHoveredIdx(idx)}
              >
                {/* Invisible hover capture zone */}
                <rect
                  x={xCenter - slotWidth / 2}
                  y={paddingTop}
                  width={slotWidth}
                  height={chartHeight + paddingBottom}
                  fill="transparent"
                />

                {/* Animated Bar */}
                <motion.rect
                  x={barX}
                  width={barWidth}
                  rx={4}
                  ry={4}
                  fill={`url(#barGrad-${idx})`}
                  stroke={isHovered ? '#FFFFFF' : barColor}
                  strokeWidth={isHovered ? 1.5 : 0}
                  initial={{ height: 0, y: chartBaseY }}
                  animate={{ height: barH, y: barY }}
                  transition={{ duration: 0.5, delay: idx * 0.04, ease: [0.16, 1, 0.3, 1] }}
                  opacity={hoveredIdx === null || isHovered ? 1 : 0.45}
                />

                {/* Top value label */}
                {item.value > 0 && (
                  <text
                    x={xCenter}
                    y={barY - 5}
                    textAnchor="middle"
                    fontSize="10"
                    fontWeight="bold"
                    fill={isHovered ? '#FFFFFF' : 'rgba(255,255,255,0.7)'}
                    fontFamily="monospace"
                  >
                    {item.value >= 1000 ? `${(item.value / 1000).toFixed(1)}k` : item.value}
                  </text>
                )}

                {/* Bottom X-axis label */}
                <text
                  x={xCenter}
                  y={chartBaseY + 16}
                  textAnchor="middle"
                  fontSize="10"
                  fill={isHovered ? '#FF3A89' : 'rgba(255,255,255,0.5)'}
                  fontWeight={isHovered ? '600' : '400'}
                  className="transition-colors select-none"
                >
                  {item.label.length > 9 ? `${item.label.slice(0, 8)}…` : item.label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
};

export default BarChart;
