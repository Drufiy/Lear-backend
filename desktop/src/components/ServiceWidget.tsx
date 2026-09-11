import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Cloud, Sparkles, MessageSquare, Check } from 'lucide-react';
import MetricGauge from './widgets/MetricGauge';
import MetricLineChart, { TimeSeriesPoint } from './widgets/MetricLineChart';
import MetricCard from './widgets/MetricCard';
import EventTimeline, { TimelineEvent } from './widgets/EventTimeline';
import StatusGrid, { StatusItem } from './widgets/StatusGrid';

export interface ServiceWidgetProps {
  connectorId: string;
  resourceId?: string;
  displayName?: string;
  onOpenChat?: (connectorId: string, resourceId?: string) => void;
}

export const ServiceWidget: React.FC<ServiceWidgetProps> = ({
  connectorId,
  resourceId = '',
  displayName,
  onOpenChat,
}) => {
  const [loading, setLoading] = useState(true);
  const [generatingAI, setGeneratingAI] = useState(false);
  const [metrics, setMetrics] = useState<any[]>([]);
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [status, setStatus] = useState<string>('healthy');
  const [statusData, setStatusData] = useState<any>(null);
  const [customLayout, setCustomLayout] = useState<any[] | null>(null);
  const [connectorInfo, setConnectorInfo] = useState<any>(null);

  const fetchTelemetry = async () => {
    try {
      // 1. Fetch connector info (includes widget_templates from registry)
      const resInfo = await fetch(`/api/connectors/${connectorId}`);
      if (resInfo.ok) {
        const info = await resInfo.json();
        setConnectorInfo(info);
      }

      // 2. Fetch live metrics
      const url = resourceId 
        ? `/api/connectors/${connectorId}/metrics?resource=${encodeURIComponent(resourceId)}`
        : `/api/connectors/${connectorId}/metrics`;
      const resMetrics = await fetch(url);
      if (resMetrics.ok) {
        const data = await resMetrics.json();
        setMetrics(data.metrics || []);
        setEvents(data.events || []);
      }

      // 3. Fetch live status
      const statusUrl = resourceId
        ? `/api/connectors/${connectorId}/status?resource=${encodeURIComponent(resourceId)}`
        : `/api/connectors/${connectorId}/status`;
      const resStatus = await fetch(statusUrl);
      if (resStatus.ok) {
        const sData = await resStatus.json();
        setStatus(sData.status || 'healthy');
        setStatusData(sData);
      }
    } catch (e) {
      console.error('Error fetching telemetry:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTelemetry();
    const interval = setInterval(fetchTelemetry, 30000); // 30s auto-refresh
    return () => clearInterval(interval);
  }, [connectorId, resourceId]);

  const handleGenerateAIWidgets = async () => {
    setGeneratingAI(true);
    try {
      const res = await fetch(`/api/connectors/${connectorId}/generate-widgets`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resource_id: resourceId, prompt: 'Generate optimal monitoring layout' }),
      });
      if (res.ok) {
        const data = await res.json();
        setCustomLayout(data.widgets || []);
      }
    } catch (e) {
      console.error('Error generating AI widgets:', e);
    } finally {
      setGeneratingAI(false);
    }
  };

  // Build real time series points from metrics (no synthetic fallbacks)
  const timeSeriesData: TimeSeriesPoint[] = metrics.map(m => ({
    timestamp: m.timestamp || new Date().toISOString(),
    value: typeof m.value === 'number' ? m.value : 0,
  }));

  // Build authentic status check items from live status response
  const statusItems: StatusItem[] = [];
  if (statusData) {
    statusItems.push({
      id: `${connectorId}_auth`,
      name: `${connectorInfo?.name || connectorId.toUpperCase()} Provider`,
      status: status === 'healthy' || status === 'running' || status === 'stable' ? 'healthy' : (status === 'unconfigured' ? 'warning' : 'error'),
      detail: statusData.detail?.message || (statusData.detail?.authenticated ? 'Authenticated' : status),
    });

    if (resourceId) {
      statusItems.push({
        id: `${connectorId}_resource`,
        name: `Resource: ${resourceId}`,
        status: status === 'healthy' || status === 'running' ? 'healthy' : (status === 'stopped' ? 'warning' : 'error'),
        detail: typeof statusData.detail === 'string' ? statusData.detail : (statusData.detail?.state || status),
      });
    }

    if (statusData.detail && typeof statusData.detail === 'object') {
      for (const [k, v] of Object.entries(statusData.detail)) {
        if (!['authenticated', 'message', 'state'].includes(k) && typeof v !== 'object') {
          const sVal = String(v).toLowerCase();
          const isGood = sVal === 'ok' || sVal === 'true' || sVal === 'passed' || sVal === 'healthy';
          statusItems.push({
            id: `chk_${k}`,
            name: k.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
            status: isGood ? 'healthy' : 'warning',
            detail: String(v),
          });
        }
      }
    }
  }

  // Active widgets: customLayout (AI generated) OR widget_templates from registry
  const activeWidgets = customLayout && customLayout.length > 0
    ? customLayout
    : (connectorInfo?.widget_templates && connectorInfo.widget_templates.length > 0
        ? connectorInfo.widget_templates
        : [
            { id: 'gauge', type: 'gauge', label: 'Utilization', metric_keys: ['cpu', 'utilization'] },
            { id: 'chart', type: 'line_chart', label: 'Telemetry Trend', metric_keys: ['metric'] },
            { id: 'timeline', type: 'event_timeline', label: 'Alarms & Watcher Events' },
            { id: 'status', type: 'status_grid', label: 'System Verification' },
          ]);

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card rounded-2xl p-6 relative overflow-hidden"
    >
      {/* Header Bar */}
      <div className="flex flex-wrap justify-between items-center gap-4 pb-5 border-b border-border-subtle">
        <div className="flex items-center gap-3">
          <div
            className="p-3 rounded-xl border border-white/10"
            style={{ backgroundColor: `${connectorInfo?.color || '#FF9900'}20` }}
          >
            <Cloud size={24} style={{ color: connectorInfo?.color || '#FF9900' }} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-bold text-lg text-white">
                {displayName || connectorInfo?.name || connectorId.toUpperCase()}
              </h3>
              {resourceId && (
                <span className="text-xs font-mono px-2 py-0.5 rounded bg-surface border border-border-subtle text-gray-400">
                  {resourceId}
                </span>
              )}
            </div>
            <p className="text-xs text-gray-400 mt-0.5">
              {connectorInfo?.description || 'Active live telemetry pipeline'}
            </p>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2">
          <button
            onClick={handleGenerateAIWidgets}
            disabled={generatingAI}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface hover:bg-surface-elevated border border-border-subtle hover:border-accent/40 text-xs font-medium text-gray-200 transition-all cursor-pointer"
            title="AI generates customized widgets based on live telemetry"
          >
            <Sparkles size={14} className={generatingAI ? 'animate-spin text-accent' : 'text-accent'} />
            {generatingAI ? 'Synthesizing...' : 'AI Generate Widgets'}
          </button>

          {onOpenChat && (
            <button
              onClick={() => onOpenChat(connectorId, resourceId)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-accent/15 hover:bg-accent/25 border border-accent/30 text-xs font-medium text-accent transition-all cursor-pointer"
            >
              <MessageSquare size={14} />
              Ask Copilot
            </button>
          )}

          <div className="flex items-center gap-2 px-3 py-1 bg-surface border border-border-subtle rounded-full text-xs font-medium ml-2">
            <div
              className={`w-2 h-2 rounded-full ${
                status === 'healthy' ? 'bg-accent animate-pulse' : 'bg-rose-500'
              }`}
            />
            <span className="capitalize">{status}</span>
          </div>
        </div>
      </div>

      {/* Dynamic Widget Grid */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <div className="w-8 h-8 rounded-full border-2 border-accent border-t-transparent animate-spin" />
        </div>
      ) : (
        <div className="space-y-6 pt-6">
          {customLayout && (
            <div className="flex items-center gap-2 text-xs text-accent font-medium bg-accent/10 border border-accent/25 px-3 py-1.5 rounded-xl">
              <Check size={14} />
              AI synthesized custom widget configuration ({customLayout.length} widgets active)
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {activeWidgets.map((widget: any, idx: number) => {
              const wType = widget.type || 'metric_card';
              const keys: string[] = widget.metric_keys || [];

              // Find matching metric from live stream
              const matchedMetric = metrics.find(m =>
                keys.some(k => (m.name || '').toLowerCase().includes(k.toLowerCase()))
              ) || (keys.length === 0 ? metrics[0] : null);

              const metricVal = matchedMetric && typeof matchedMetric.value === 'number' ? matchedMetric.value : 0;
              const unit = widget.unit || matchedMetric?.unit || '';

              // Filter matching timeseries points
              const matchedPoints: TimeSeriesPoint[] = metrics
                .filter(m => keys.length === 0 || keys.some(k => (m.name || '').toLowerCase().includes(k.toLowerCase())))
                .map(m => ({
                  timestamp: m.timestamp || new Date().toISOString(),
                  value: typeof m.value === 'number' ? m.value : 0,
                }));

              // 1. Radial Gauge
              if (wType === 'gauge') {
                return (
                  <div key={widget.id || idx} className="glass-panel rounded-xl flex items-center justify-center p-4">
                    <MetricGauge
                      value={metricVal}
                      label={widget.label || matchedMetric?.name || 'Utilization'}
                      unit={unit || '%'}
                    />
                  </div>
                );
              }

              // 2. Timeseries Line Chart (pure live data, no synthetic fallback)
              if (wType === 'line_chart') {
                const chartData = matchedPoints.length > 0 ? matchedPoints : timeSeriesData;
                return (
                  <div key={widget.id || idx} className="glass-panel rounded-xl lg:col-span-2">
                    <MetricLineChart
                      data={chartData}
                      label={widget.label || 'Telemetry Trend'}
                      unit={unit}
                      color={connectorInfo?.color || '#10B981'}
                    />
                  </div>
                );
              }

              // 3. Metric KPI Card (real change computed from consecutive points, no hardcoded change={2.4})
              if (wType === 'metric_card') {
                const historyVals = matchedPoints.map(p => p.value);
                let trendChange: number | undefined = undefined;
                if (historyVals.length >= 2) {
                  const last = historyVals[historyVals.length - 1];
                  const prev = historyVals[historyVals.length - 2];
                  if (prev !== 0) {
                    trendChange = ((last - prev) / Math.abs(prev)) * 100;
                  }
                }

                return (
                  <div key={widget.id || idx} className="glass-panel rounded-xl flex flex-col justify-center gap-3 p-4">
                    <MetricCard
                      label={widget.label || matchedMetric?.name || 'Metric'}
                      value={matchedMetric ? metricVal.toFixed(1) : '—'}
                      unit={unit}
                      change={trendChange}
                      history={historyVals.length >= 2 ? historyVals : undefined}
                    />
                  </div>
                );
              }

              // 4. Event & Alarm Timeline
              if (wType === 'event_timeline') {
                const matchedEvents = events.filter(ev =>
                  keys.length === 0 || keys.some(k => (ev.event_type || '').toLowerCase().includes(k.toLowerCase()))
                );
                return (
                  <div key={widget.id || idx} className="glass-panel rounded-xl lg:col-span-2">
                    <EventTimeline
                      events={matchedEvents.length > 0 ? matchedEvents : events}
                      label={widget.label || 'Alarms & Watcher Events'}
                    />
                  </div>
                );
              }

              // 5. Health Checks Status Grid (pure authentic status checks from provider)
              if (wType === 'status_grid') {
                return (
                  <div key={widget.id || idx} className="glass-panel rounded-xl lg:col-span-3">
                    <StatusGrid
                      items={statusItems}
                      label={widget.label || 'System Verification'}
                    />
                  </div>
                );
              }

              // Fallback for bar_chart or custom widget types
              return (
                <div key={widget.id || idx} className="glass-panel rounded-xl p-4 flex flex-col justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wider text-gray-400 block mb-2">{widget.label}</span>
                  <div className="flex items-baseline gap-2">
                    <span className="text-2xl font-bold text-white">{matchedMetric ? metricVal.toFixed(1) : '—'}</span>
                    <span className="text-xs text-gray-400">{unit}</span>
                  </div>
                  {widget.description && <p className="text-[11px] text-gray-500 mt-2">{widget.description}</p>}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </motion.div>
  );
};

export default ServiceWidget;
