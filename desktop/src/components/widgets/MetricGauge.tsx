import React from 'react';
import { motion } from 'framer-motion';

interface MetricGaugeProps {
  value: number; // 0 - 100
  label: string;
  unit?: string;
  size?: number;
}

export const MetricGauge: React.FC<MetricGaugeProps> = ({
  value,
  label,
  unit = '%',
  size = 180,
}) => {
  const safeValue = Math.min(Math.max(value || 0, 0), 100);
  const strokeWidth = 14;
  const radius = (size - strokeWidth) / 2;
  const circumference = Math.PI * radius; // Half circle arc
  const strokeDashoffset = circumference - (safeValue / 100) * circumference;

  // Determine color based on threshold
  let strokeColor = '#10B981'; // Green
  if (safeValue > 70 && safeValue <= 85) {
    strokeColor = '#F59E0B'; // Amber
  } else if (safeValue > 85) {
    strokeColor = '#F43F5E'; // Rose / Red
  }

  return (
    <div className="flex flex-col items-center justify-center p-4">
      <div className="relative flex items-center justify-center" style={{ width: size, height: size / 2 + 25 }}>
        <svg
          width={size}
          height={size / 2 + strokeWidth}
          className="overflow-visible"
        >
          <defs>
            <linearGradient id="gaugeGradient" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#10B981" />
              <stop offset="70%" stopColor="#F59E0B" />
              <stop offset="100%" stopColor="#F43F5E" />
            </linearGradient>
          </defs>

          {/* Background Arc */}
          <path
            d={`M ${strokeWidth / 2},${size / 2} A ${radius},${radius} 0 0,1 ${size - strokeWidth / 2},${size / 2}`}
            fill="none"
            stroke="rgba(255, 255, 255, 0.08)"
            strokeWidth={strokeWidth}
            strokeLinecap="round"
          />

          {/* Animated Value Arc */}
          <motion.path
            d={`M ${strokeWidth / 2},${size / 2} A ${radius},${radius} 0 0,1 ${size - strokeWidth / 2},${size / 2}`}
            fill="none"
            stroke={strokeColor}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circumference}
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset }}
            transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
          />
        </svg>

        {/* Center Metric Text */}
        <div className="absolute bottom-1 flex flex-col items-center">
          <div className="flex items-baseline">
            <span className="text-3xl font-bold tracking-tight text-white">
              {safeValue.toFixed(1)}
            </span>
            <span className="text-sm font-medium text-gray-400 ml-0.5">{unit}</span>
          </div>
          <span className="text-xs font-semibold text-gray-400 tracking-wider uppercase mt-1">{label}</span>
        </div>
      </div>

      {/* Min/Max Markers */}
      <div className="flex justify-between w-full px-4 text-[11px] text-gray-500 font-mono mt-1">
        <span>0{unit}</span>
        <span>100{unit}</span>
      </div>
    </div>
  );
};

export default MetricGauge;
