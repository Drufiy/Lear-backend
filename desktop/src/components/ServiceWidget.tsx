import { useState, useEffect, useRef, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Cloud,
  MessageSquare,
  Check,
  RefreshCw,
  AlertCircle,
  X,
  Activity,
  Maximize2,
  Table as TableIcon,
  Radio,
  Play,
  Square,
  Pause,
  Terminal,
  Sliders,
} from 'lucide-react';
import MetricGauge from './widgets/MetricGauge';
import MetricLineChart, { TimeSeriesPoint } from './widgets/MetricLineChart';
import MetricCard from './widgets/MetricCard';
import BarChart, { BarChartItem } from './widgets/BarChart';
import EventTimeline, { TimelineEvent } from './widgets/EventTimeline';
import StatusGrid, { StatusItem } from './widgets/StatusGrid';
import WidgetConfigurator, { ConfigurableWidget } from './WidgetConfigurator';
import useWebSocket from '../hooks/useWebSocket';

export interface ServiceWidgetProps {
  connectorId: string;
  resourceId?: string;
  displayName?: string;
  onOpenChat?: (connectorId: string, resourceId?: string, prompt?: string) => void;
}

type TimeRange = '15m' | '1h' | '6h' | '24h';

interface ExpandedWidgetState {
  type: 'line_chart' | 'bar_chart';
  title: string;
  unit?: string;
  data: any[];
}

export const ServiceWidget: React.FC<ServiceWidgetProps> = ({
  connectorId,
  resourceId = '',
  displayName,
  onOpenChat,
}) => {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [timeRange, setTimeRange] = useState<TimeRange>('1h');
  const [expandedWidget, setExpandedWidget] = useState<ExpandedWidgetState | null>(null);

  const [metrics, setMetrics] = useState<any[]>([]);
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [status, setStatus] = useState<string>('healthy');
  const [statusData, setStatusData] = useState<any>(null);
  const [customLayout, setCustomLayout] = useState<any[] | null>(null);
  const [isConfiguratorOpen, setIsConfiguratorOpen] = useState<boolean>(false);
  const [connectorInfo, setConnectorInfo] = useState<any>(null);

  // Watcher and live monitoring integration
  const { lastEvent } = useWebSocket();
  const [isWatching, setIsWatching] = useState<boolean>(false);
  const [isPaused, setIsPaused] = useState<boolean>(false);
  const [watchInterval, setWatchInterval] = useState<number>(5);
  const [livePulse, setLivePulse] = useState<boolean>(false);
  const [liveStreamOpen, setLiveStreamOpen] = useState<boolean>(false);
  const [liveFeed, setLiveFeed] = useState<any[]>([]);
  const [expandedRawId, setExpandedRawId] = useState<string | null>(null);

  // Rolling metric cache across polls: key -> TimeSeriesPoint[]
  const rollingHistoryRef = useRef<Map<string, TimeSeriesPoint[]>>(new Map());

  const fetchTelemetry = async (isManual = false) => {
    if (isManual) setRefreshing(true);
    setError(null);

    try {
      // 1. Fetch connector info (widget templates & metadata)
      if (!connectorInfo) {
        const resInfo = await fetch(`/api/connectors/${connectorId}`);
        if (resInfo.ok) {
          const info = await resInfo.json();
          setConnectorInfo(info);
        }
      }

      // 2. Fetch live metrics
      const url = resourceId 
        ? `/api/connectors/${connectorId}/metrics?resource=${encodeURIComponent(resourceId)}`
        : `/api/connectors/${connectorId}/metrics`;
      const resMetrics = await fetch(url);
      if (resMetrics.ok) {
        const data = await resMetrics.json();
        const incomingMetrics: any[] = data.metrics || [];
        setMetrics(incomingMetrics);
        setEvents(data.events || []);

        // Accumulate rolling history (capped at 40 points per metric)
        const nowIso = new Date().toISOString();
        incomingMetrics.forEach(m => {
          if (m.name && typeof m.value === 'number') {
            const history = rollingHistoryRef.current.get(m.name) || [];
            const newPoint: TimeSeriesPoint = {
              timestamp: m.timestamp || nowIso,
              value: m.value,
            };
            // Prevent duplicate timestamp insertions
            if (history.length === 0 || history[history.length - 1].timestamp !== newPoint.timestamp) {
              const updated = [...history, newPoint].slice(-40);
              rollingHistoryRef.current.set(m.name, updated);
            }
          }
        });
      } else {
        const errData = await resMetrics.json().catch(() => ({}));
        if (errData.code === 'CONNECTOR_NOT_CONFIGURED') {
          setStatus('unconfigured');
        } else {
          const msg = typeof errData.message === 'string' && errData.message
            ? errData.message
            : (typeof errData.detail === 'string' && errData.detail
                ? errData.detail
                : `Failed to fetch metrics (${resMetrics.status})`);
          setError(msg);
        }
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
    } catch (e: any) {
      console.error('Error fetching telemetry:', e);
      setError(typeof e?.message === 'string' ? e.message : 'Network error fetching service telemetry');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const fetchSavedWidgets = async () => {
    try {
      const url = resourceId
        ? `/api/connectors/${connectorId}/widgets?resource_id=${encodeURIComponent(resourceId)}`
        : `/api/connectors/${connectorId}/widgets`;
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        if (data.custom && Array.isArray(data.widgets) && data.widgets.length > 0) {
          setCustomLayout(data.widgets);
        }
      }
    } catch (e) {
      console.error('Error fetching custom widgets:', e);
    }
  };

  const handleSaveCustomLayout = async (newWidgets: ConfigurableWidget[]) => {
    const res = await fetch(`/api/connectors/${connectorId}/widgets`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resource_id: resourceId || '', widgets: newWidgets }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.message || err.detail || 'Failed to save widget layout');
    }
    setCustomLayout(newWidgets);
  };

  const handleResetCustomLayout = async () => {
    const url = resourceId
      ? `/api/connectors/${connectorId}/widgets?resource_id=${encodeURIComponent(resourceId)}`
      : `/api/connectors/${connectorId}/widgets`;
    const res = await fetch(url, { method: 'DELETE' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.message || err.detail || 'Failed to reset layout');
    }
    setCustomLayout(null);
  };

  useEffect(() => {
    fetchTelemetry();
    fetchSavedWidgets();
    const interval = setInterval(() => fetchTelemetry(false), 30000); // 30s auto-refresh
    return () => clearInterval(interval);
  }, [connectorId, resourceId]);

  // Check active watch status for this service
  const checkServiceWatchStatus = async () => {
    try {
      const res = await fetch('/api/watch/active');
      if (res.ok) {
        const data = await res.json();
        const found = (data.watches || []).find((w: any) =>
          w.connector.toLowerCase() === connectorId.toLowerCase() &&
          (!resourceId || (w.target && w.target.toLowerCase().includes(resourceId.toLowerCase())))
        );
        if (found) {
          setIsWatching(true);
          setIsPaused(found.status === 'paused');
          if (found.interval) setWatchInterval(found.interval);
        } else {
          setIsWatching(false);
          setIsPaused(false);
        }
      }
    } catch {
      // Ignore
    }
  };

  useEffect(() => {
    checkServiceWatchStatus();
  }, [connectorId, resourceId]);

  // Real-time integration: listen to WebSocket events for this service
  useEffect(() => {
    if (!lastEvent) return;

    const matchesConnector = !lastEvent.connector || lastEvent.connector.toLowerCase() === connectorId.toLowerCase();
    const matchesTarget = !resourceId || !lastEvent.watch_id || lastEvent.watch_id.toLowerCase().includes(resourceId.toLowerCase());

    if (matchesConnector && matchesTarget) {
      // 1. Append to timeline & live stream
      const newEv: TimelineEvent = {
        timestamp: lastEvent.timestamp || new Date().toISOString(),
        event_type: lastEvent.event_type || 'event',
        summary: lastEvent.summary || 'Live Telemetry Event',
        raw: lastEvent.raw,
      };

      setEvents(prev => [newEv, ...prev.slice(0, 49)]);
      setLiveFeed(prev => [lastEvent, ...prev.slice(0, 99)]);

      // 2. Extract numeric telemetry into metrics & rolling history in real time
      const raw = lastEvent.raw;
      if (raw && typeof raw === 'object') {
        const candidateVal = typeof raw.value === 'number' ? raw.value
          : (typeof raw.val === 'number' ? raw.val
          : (typeof raw.metric_value === 'number' ? raw.metric_value
          : (typeof raw.latency === 'number' ? raw.latency
          : (typeof raw.cpu_percent === 'number' ? raw.cpu_percent
          : null))));

        if (candidateVal !== null) {
          const metricName = lastEvent.event_type || 'live_metric';
          setMetrics(prev => {
            const exists = prev.find(m => m.name === metricName);
            if (exists) {
              return prev.map(m => m.name === metricName ? { ...m, value: candidateVal, timestamp: lastEvent.timestamp } : m);
            }
            return [{ name: metricName, value: candidateVal, unit: raw.unit || '', timestamp: lastEvent.timestamp }, ...prev];
          });

          const history = rollingHistoryRef.current.get(metricName) || [];
          rollingHistoryRef.current.set(metricName, [...history, { timestamp: lastEvent.timestamp, value: candidateVal }].slice(-40));
        }
      }

      // 3. Status transition on real-time events
      const etype = (lastEvent.event_type || '').toLowerCase();
      const summary = (lastEvent.summary || '').toLowerCase();
      if (etype.includes('fail') || etype.includes('error') || etype.includes('crash') || summary.includes('error')) {
        setStatus('critical');
      } else if (etype.includes('spike') || etype.includes('warn') || etype.includes('degraded')) {
        setStatus('degraded');
      } else if (etype.includes('recovered') || etype.includes('healthy')) {
        setStatus('healthy');
      }

      // 4. Live visual pulse
      setLivePulse(true);
      const pulseTimer = setTimeout(() => setLivePulse(false), 1800);
      return () => clearTimeout(pulseTimer);
    }
  }, [lastEvent, connectorId, resourceId]);

  const handleToggleWatch = async () => {
    const target = resourceId || 'default';
    if (isWatching) {
      try {
        const res = await fetch(`/api/connectors/${connectorId}/watch?target=${encodeURIComponent(target)}`, {
          method: 'DELETE',
        });
        if (res.ok) {
          setIsWatching(false);
          setIsPaused(false);
        }
      } catch (e) {
        console.error('Failed to stop watch:', e);
      }
    } else {
      try {
        const res = await fetch(`/api/connectors/${connectorId}/watch`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target, interval: watchInterval }),
        });
        if (res.ok) {
          setIsWatching(true);
          setIsPaused(false);
        }
      } catch (e) {
        console.error('Failed to start watch:', e);
      }
    }
  };

  const handleTogglePause = async () => {
    const target = resourceId || 'default';
    const endpoint = isPaused
      ? `/api/connectors/${connectorId}/watch/resume`
      : `/api/connectors/${connectorId}/watch/pause`;
    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target }),
      });
      if (res.ok) {
        setIsPaused(!isPaused);
      }
    } catch (e) {
      console.error('Failed to toggle pause:', e);
    }
  };

  // Filter duration in ms based on selected time range
  const timeRangeFilterMs = useMemo(() => {
    switch (timeRange) {
      case '15m': return 15 * 60 * 1000;
      case '1h': return 60 * 60 * 1000;
      case '6h': return 6 * 60 * 60 * 1000;
      case '24h': return 24 * 60 * 60 * 1000;
    }
  }, [timeRange]);

  // ---------------------------------------------------------------------------
  // DATA ADAPTERS
  // ---------------------------------------------------------------------------

  /**
   * Adapter: Time Series Points for Line Charts
   */
  const adaptTimeSeriesData = (keys: string[]): TimeSeriesPoint[] => {
    const cutoff = Date.now() - timeRangeFilterMs;
    const matchedPoints: TimeSeriesPoint[] = [];

    // Check rolling cache for matching metric keys
    rollingHistoryRef.current.forEach((points, metricName) => {
      const isMatch = keys.length === 0 || keys.some(k => metricName.toLowerCase().includes(k.toLowerCase()));
      if (isMatch) {
        matchedPoints.push(...points);
      }
    });

    // If cache was empty, fall back to current incoming metrics
    if (matchedPoints.length === 0) {
      metrics.forEach(m => {
        const isMatch = keys.length === 0 || keys.some(k => (m.name || '').toLowerCase().includes(k.toLowerCase()));
        if (isMatch && typeof m.value === 'number') {
          matchedPoints.push({
            timestamp: m.timestamp || new Date().toISOString(),
            value: m.value,
          });
        }
      });
    }

    // Sort chronologically and apply time range cutoff
    const sorted = matchedPoints
      .filter(p => new Date(p.timestamp).getTime() >= cutoff || matchedPoints.length <= 5)
      .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

    return sorted;
  };

  /**
   * Adapter: Categorical / Bar Items for BarChart
   */
  const adaptBarData = (keys: string[], defaultUnit = ''): BarChartItem[] => {
    const items: BarChartItem[] = [];

    // Case 1: Template specifies multiple distinct keys (e.g. Snyk severity breakdown)
    if (keys.length > 1) {
      keys.forEach((k, idx) => {
        const cleanKey = k.toLowerCase().replace(/^(severity_|pod_|metric_)/, '');
        const matched = metrics.find(m => (m.name || '').toLowerCase().includes(k.toLowerCase()));
        const val = matched && typeof matched.value === 'number' ? matched.value : 0;

        let color = '#FF3A89';
        if (cleanKey.includes('crit') || cleanKey.includes('high')) color = '#F43F5E';
        else if (cleanKey.includes('med') || cleanKey.includes('warn')) color = '#F59E0B';
        else if (cleanKey.includes('low') || cleanKey.includes('info')) color = '#38BDF8';
        else if (idx === 1) color = '#A855F7';
        else if (idx === 2) color = '#06B6D4';

        items.push({
          id: k,
          label: cleanKey.charAt(0).toUpperCase() + cleanKey.slice(1),
          value: val,
          color,
          unit: defaultUnit,
        });
      });
      return items;
    }

    // Case 2: Single key with multiple matching metrics in the stream (e.g. multiple pods or instances)
    const matching = metrics.filter(m =>
      keys.length === 0 || keys.some(k => (m.name || '').toLowerCase().includes(k.toLowerCase()))
    );

    if (matching.length > 0) {
      matching.slice(0, 8).forEach((m, idx) => {
        const val = typeof m.value === 'number' ? m.value : 0;
        const barLabel = m.resource_id || m.name || `Item ${idx + 1}`;
        items.push({
          id: `bar-${idx}`,
          label: barLabel.length > 12 ? `${barLabel.slice(0, 10)}…` : barLabel,
          value: val,
          unit: m.unit || defaultUnit,
          color: idx % 2 === 0 ? '#FF3A89' : '#A855F7',
        });
      });
      return items;
    }

    // Case 3: Single scalar metric with rolling history
    const matchedKey = keys[0] || '';
    const history = rollingHistoryRef.current.get(matchedKey) || [];
    if (history.length > 0) {
      history.slice(-7).forEach((p, idx) => {
        const date = new Date(p.timestamp);
        const timeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        items.push({
          id: `hist-${idx}`,
          label: timeStr,
          value: p.value,
          unit: defaultUnit,
          color: '#FF3A89',
        });
      });
    }

    return items;
  };

  /**
   * Adapter: Metric Card (scalar with real percentage delta)
   */
  const adaptMetricCardData = (keys: string[]) => {
    const matched = metrics.find(m =>
      keys.length === 0 || keys.some(k => (m.name || '').toLowerCase().includes(k.toLowerCase()))
    ) || (keys.length === 0 ? metrics[0] : null);

    const val = matched && typeof matched.value === 'number' ? matched.value : 0;
    const metricName = matched?.name || keys[0] || '';

    // Calculate delta and sparkline history from rolling cache
    const history = rollingHistoryRef.current.get(metricName) || [];
    const historyVals = history.map(h => h.value);

    let change: number | undefined = undefined;
    if (historyVals.length >= 2) {
      const curr = historyVals[historyVals.length - 1];
      const prev = historyVals[historyVals.length - 2];
      if (prev !== 0) {
        change = ((curr - prev) / Math.abs(prev)) * 100;
      }
    }

    return {
      value: matched ? (val % 1 === 0 ? val.toString() : val.toFixed(1)) : '—',
      rawVal: val,
      unit: matched?.unit || '',
      change,
      history: historyVals.length >= 2 ? historyVals.slice(-10) : undefined,
    };
  };

  /**
   * Adapter: Authentic Status Checks from Provider
   */
  const statusItems: StatusItem[] = useMemo(() => {
    const items: StatusItem[] = [];
    if (!statusData) return items;

    items.push({
      id: `${connectorId}_auth`,
      name: `${connectorInfo?.name || connectorId.toUpperCase()} Provider`,
      status: status === 'healthy' || status === 'running' || status === 'stable' ? 'healthy' : (status === 'unconfigured' ? 'warning' : 'error'),
      detail: statusData.detail?.message || (statusData.detail?.authenticated ? 'Authenticated' : status),
    });

    if (resourceId) {
      items.push({
        id: `${connectorId}_resource`,
        name: `Target: ${resourceId}`,
        status: status === 'healthy' || status === 'running' ? 'healthy' : (status === 'stopped' ? 'warning' : 'error'),
        detail: typeof statusData.detail === 'string' ? statusData.detail : (statusData.detail?.state || status),
      });
    }

    if (statusData.detail && typeof statusData.detail === 'object') {
      for (const [k, v] of Object.entries(statusData.detail)) {
        if (!['authenticated', 'message', 'state'].includes(k) && typeof v !== 'object') {
          const sVal = String(v).toLowerCase();
          const isGood = sVal === 'ok' || sVal === 'true' || sVal === 'passed' || sVal === 'healthy';
          items.push({
            id: `chk_${k}`,
            name: k.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
            status: isGood ? 'healthy' : 'warning',
            detail: String(v),
          });
        }
      }
    }

    return items;
  }, [statusData, connectorId, resourceId, status, connectorInfo]);

  // Active Widgets: customLayout (AI generated) OR widget_templates from registry
  const activeWidgets = useMemo(() => {
    if (customLayout && customLayout.length > 0) {
      return customLayout;
    }
    if (connectorInfo?.widget_templates && connectorInfo.widget_templates.length > 0) {
      return connectorInfo.widget_templates;
    }
    // Dynamic default template if connector has not loaded templates yet
    return [
      { id: 'gauge', type: 'gauge', label: 'Utilization', metric_keys: ['cpu', 'utilization'] },
      { id: 'chart', type: 'line_chart', label: 'Telemetry Trend', metric_keys: ['metric'] },
      { id: 'timeline', type: 'event_timeline', label: 'Alarms & Watcher Events' },
      { id: 'status', type: 'status_grid', label: 'System Verification' },
    ];
  }, [customLayout, connectorInfo]);

  // ---------------------------------------------------------------------------
  // RENDER
  // ---------------------------------------------------------------------------

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className={`glass-card rounded-2xl p-6 relative overflow-hidden transition-all duration-500 border ${
        livePulse ? 'border-accent shadow-[0_0_30px_rgba(34,197,94,0.18)] ring-1 ring-accent/30' : 'border-border-subtle'
      }`}
    >
      {/* Header Bar */}
      <div className="flex flex-wrap justify-between items-center gap-4 pb-5 border-b border-border-subtle">
        <div className="flex items-center gap-3">
          <div
            className="p-3 rounded-xl border border-white/10"
            style={{ backgroundColor: `${connectorInfo?.color || '#FF3A89'}20` }}
          >
            <Cloud size={24} style={{ color: connectorInfo?.color || '#FF3A89' }} />
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

        {/* Action Controls & Filters */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Per-Service Watch Control (Phase D2) */}
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-xl bg-surface border border-border-subtle">
            {isWatching ? (
              <>
                <span className="relative flex h-2 w-2 mr-0.5">
                  <span className={`absolute inline-flex h-full w-full rounded-full opacity-75 ${isPaused ? 'bg-amber-400' : 'animate-ping bg-accent'}`} />
                  <span className={`relative inline-flex rounded-full h-2 w-2 ${isPaused ? 'bg-amber-400' : 'bg-accent'}`} />
                </span>
                <span className="text-[11px] font-mono font-semibold text-gray-200">
                  {isPaused ? 'Paused' : `Live (${watchInterval}s)`}
                </span>
                <button
                  onClick={handleTogglePause}
                  className="p-1 rounded text-gray-400 hover:text-white transition-colors cursor-pointer"
                  title={isPaused ? 'Resume Watching' : 'Pause Watching'}
                >
                  {isPaused ? <Play size={11} className="text-accent" /> : <Pause size={11} className="text-amber-400" />}
                </button>
                <button
                  onClick={handleToggleWatch}
                  className="p-1 rounded text-gray-400 hover:text-rose-400 transition-colors cursor-pointer"
                  title="Stop Watching Service"
                >
                  <Square size={11} />
                </button>
              </>
            ) : (
              <button
                onClick={handleToggleWatch}
                className="flex items-center gap-1.5 text-xs text-gray-300 hover:text-accent transition-colors font-medium cursor-pointer"
                title="Start live background telemetry watch"
              >
                <Radio size={13} className="text-accent" />
                <span>Watch Service</span>
              </button>
            )}
          </div>

          {/* Live Feed Toggle Button (Phase D3) */}
          <button
            onClick={() => setLiveStreamOpen(!liveStreamOpen)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-xl border text-xs font-medium transition-all cursor-pointer ${
              liveStreamOpen
                ? 'bg-accent/20 border-accent/40 text-accent'
                : 'bg-surface hover:bg-surface-elevated border-border-subtle text-gray-300'
            }`}
            title="Toggle real-time live event feed"
          >
            <Activity size={13} className={livePulse ? 'animate-bounce text-accent' : ''} />
            <span>Live Feed</span>
            {liveFeed.length > 0 && (
              <span className="px-1.5 py-0.2 rounded-full bg-accent/30 text-accent font-mono text-[10px]">
                {liveFeed.length}
              </span>
            )}
          </button>

          {/* Time Range Selector */}
          <div className="flex items-center bg-surface border border-border-subtle rounded-lg p-0.5 text-xs font-mono">
            {(['15m', '1h', '6h', '24h'] as TimeRange[]).map(tr => (
              <button
                key={tr}
                onClick={() => setTimeRange(tr)}
                className={`px-2 py-1 rounded-md transition-all cursor-pointer ${
                  timeRange === tr
                    ? 'bg-accent/20 text-accent font-bold shadow-sm'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                {tr}
              </button>
            ))}
          </div>

          {/* Refresh Manual Trigger */}
          <button
            onClick={() => fetchTelemetry(true)}
            disabled={refreshing}
            className="p-2 rounded-lg bg-surface hover:bg-surface-elevated border border-border-subtle text-gray-400 hover:text-white transition-all cursor-pointer"
            title="Poll live telemetry now"
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin text-accent' : ''} />
          </button>

          {/* AI Customize / Configure Layout */}
          <button
            onClick={() => setIsConfiguratorOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface hover:bg-surface-elevated border border-border-subtle hover:border-accent/40 text-xs font-medium text-gray-200 transition-all cursor-pointer"
            title="Configure widget placements, reorder, or synthesize with AI"
          >
            <Sliders size={14} className="text-accent" />
            Customize Layout
          </button>

          {/* Ask Lear */}
          {onOpenChat && (
            <button
              onClick={() => onOpenChat(connectorId, resourceId, `Analyze telemetry for ${displayName || connectorId}`)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-accent/15 hover:bg-accent/25 border border-accent/30 text-xs font-medium text-accent transition-all cursor-pointer"
            >
              <MessageSquare size={14} />
              Ask Lear
            </button>
          )}

          {/* Live Status Badge */}
          <div className="flex items-center gap-2 px-3 py-1 bg-surface border border-border-subtle rounded-full text-xs font-medium ml-1">
            <div
              className={`w-2 h-2 rounded-full ${
                status === 'healthy' || status === 'running' || status === 'stable'
                  ? 'bg-accent shadow-[0_0_6px_rgba(255,58,137,0.5)]'
                  : status === 'unconfigured'
                  ? 'bg-amber-400'
                  : 'bg-rose-500'
              }`}
            />
            <span className="capitalize">{status}</span>
          </div>
        </div>
      </div>

      {/* Collapsible Live Event Stream Feed (Phase D3) */}
      <AnimatePresence>
        {liveStreamOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="mt-4 p-4 rounded-xl bg-surface/90 border border-accent/25 backdrop-blur-md overflow-hidden space-y-3"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs font-bold text-white">
                <Terminal size={14} className="text-accent" />
                <span>Real-Time WebSocket Feed</span>
                <span className="text-gray-400 font-normal font-mono text-[11px]">
                  ({liveFeed.length} events received)
                </span>
              </div>
              <div className="flex items-center gap-2">
                {liveFeed.length > 0 && (
                  <button
                    onClick={() => setLiveFeed([])}
                    className="text-[11px] text-gray-400 hover:text-white px-2 py-0.5 rounded bg-surface border border-border-subtle cursor-pointer"
                  >
                    Clear Stream
                  </button>
                )}
                <button
                  onClick={() => setLiveStreamOpen(false)}
                  className="text-gray-400 hover:text-white p-1 rounded cursor-pointer"
                >
                  <X size={14} />
                </button>
              </div>
            </div>

            {liveFeed.length === 0 ? (
              <div className="py-6 text-center text-xs text-gray-400 font-mono">
                Awaiting incoming WebSocket telemetry events for {displayName || connectorId}...
              </div>
            ) : (
              <div className="max-h-52 overflow-y-auto space-y-2 pr-1 custom-scrollbar">
                {liveFeed.map((ev, idx) => {
                  const isErr = (ev.event_type || '').toLowerCase().includes('fail') || (ev.event_type || '').toLowerCase().includes('error');
                  const isWarn = (ev.event_type || '').toLowerCase().includes('spike') || (ev.event_type || '').toLowerCase().includes('warn');
                  const isRawOpen = expandedRawId === `${idx}_${ev.timestamp}`;

                  return (
                    <div
                      key={idx}
                      className={`p-2.5 rounded-lg border text-xs font-mono transition-colors ${
                        isErr
                          ? 'bg-rose-500/10 border-rose-500/30 text-rose-200'
                          : isWarn
                          ? 'bg-amber-500/10 border-amber-500/30 text-amber-200'
                          : 'bg-surface-elevated border-border-subtle text-gray-300'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${isErr ? 'bg-rose-400' : isWarn ? 'bg-amber-400' : 'bg-accent'}`} />
                          <span className="font-bold text-white uppercase text-[10px] bg-white/10 px-1 py-0.2 rounded">
                            {ev.event_type}
                          </span>
                          <span className="truncate text-gray-200">{ev.summary}</span>
                        </div>
                        <div className="flex items-center gap-2 shrink-0 text-[10px] text-gray-400">
                          <span>{new Date(ev.timestamp).toLocaleTimeString()}</span>
                          {ev.raw && (
                            <button
                              onClick={() => setExpandedRawId(isRawOpen ? null : `${idx}_${ev.timestamp}`)}
                              className="text-accent hover:underline text-[10px] cursor-pointer"
                            >
                              {isRawOpen ? 'Hide' : 'Raw'}
                            </button>
                          )}
                        </div>
                      </div>

                      {isRawOpen && ev.raw && (
                        <pre className="mt-2 p-2 bg-black/50 rounded text-[10px] text-gray-300 overflow-x-auto">
                          {JSON.stringify(ev.raw, null, 2)}
                        </pre>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Error State */}
      {error && (
        <div className="mt-4 p-4 rounded-xl bg-rose-500/10 border border-rose-500/25 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 text-rose-300 text-xs">
            <AlertCircle size={18} className="shrink-0 text-rose-400" />
            <div>
              <p className="font-semibold">Telemetry Polling Failed</p>
              <p className="text-gray-400 text-[11px] mt-0.5">
                {typeof error === 'string' ? error : JSON.stringify(error)}
              </p>
            </div>
          </div>
          <button
            onClick={() => fetchTelemetry(true)}
            className="px-3 py-1.5 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 text-rose-200 text-xs font-medium transition-colors cursor-pointer"
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading Skeleton */}
      {loading ? (
        <div className="pt-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3].map(i => (
            <div
              key={i}
              className={`glass-panel rounded-xl h-44 p-4 animate-pulse flex flex-col justify-between ${
                i === 2 ? 'lg:col-span-2' : ''
              }`}
            >
              <div className="h-3 w-28 bg-white/5 rounded" />
              <div className="h-16 w-full bg-white/5 rounded-lg" />
              <div className="h-2 w-20 bg-white/5 rounded" />
            </div>
          ))}
        </div>
      ) : metrics.length === 0 && events.length === 0 && !statusData ? (
        /* Empty State */
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <div className="w-12 h-12 rounded-xl bg-surface border border-border-subtle flex items-center justify-center text-gray-500 mb-3">
            <Activity size={22} />
          </div>
          <h4 className="text-sm font-semibold text-white">No Live Metrics Available</h4>
          <p className="text-xs text-gray-400 max-w-sm mt-1 mb-4">
            No telemetry stream detected for this resource. Start a watcher or check provider credentials to stream live performance data.
          </p>
          <button
            onClick={() => fetchTelemetry(true)}
            className="px-4 py-2 rounded-xl bg-surface hover:bg-surface-elevated border border-border-subtle text-xs font-medium text-white transition-colors cursor-pointer"
          >
            Check Again
          </button>
        </div>
      ) : (
        /* Dynamic Widget Grid */
        <div className="space-y-6 pt-6">
          {customLayout && (
            <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-accent font-medium bg-accent/10 border border-accent/25 px-4 py-2.5 rounded-xl">
              <div className="flex items-center gap-2">
                <Check size={15} />
                <span>
                  Custom Layout Active: <strong>{customLayout.length}</strong> widgets configured for this service
                </span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setIsConfiguratorOpen(true)}
                  className="px-2.5 py-1 rounded-lg bg-accent/20 hover:bg-accent/30 text-accent text-xs font-semibold transition-colors cursor-pointer"
                >
                  Configure Layout
                </button>
                <button
                  onClick={handleResetCustomLayout}
                  className="px-2.5 py-1 rounded-lg bg-surface hover:bg-surface-elevated text-gray-400 hover:text-white border border-border-subtle text-xs transition-colors cursor-pointer"
                >
                  Reset to Defaults
                </button>
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {activeWidgets.map((widget: any, idx: number) => {
              const wType = widget.type || 'metric_card';
              const keys: string[] = widget.metric_keys || [];
              const unit = widget.unit || '';
              const widgetLabel = widget.label || 'Telemetry';
              const span = widget.position?.span || (wType === 'status_grid' ? 3 : (wType === 'line_chart' || wType === 'bar_chart' || wType === 'event_timeline' ? 2 : 1));
              const colSpanClass = span === 3 ? 'col-span-1 md:col-span-2 lg:col-span-3' : (span === 2 ? 'col-span-1 md:col-span-2 lg:col-span-2' : 'col-span-1');

              // 1. Radial Gauge
              if (wType === 'gauge') {
                const cardData = adaptMetricCardData(keys);
                return (
                  <div key={widget.id || idx} className={`glass-panel rounded-xl flex items-center justify-center p-4 relative group ${colSpanClass}`}>
                    <MetricGauge
                      value={cardData.rawVal}
                      label={widgetLabel}
                      unit={unit || cardData.unit || '%'}
                    />
                    {onOpenChat && (
                      <button
                        onClick={() => onOpenChat(connectorId, resourceId, `Diagnose ${widgetLabel} currently at ${cardData.rawVal}${unit || cardData.unit || '%'}`)}
                        className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 p-1.5 rounded-lg bg-surface-elevated border border-border-subtle text-gray-400 hover:text-accent transition-all cursor-pointer"
                        title="Ask Lear about this metric"
                      >
                        <MessageSquare size={13} />
                      </button>
                    )}
                  </div>
                );
              }

              // 2. Timeseries Line Chart
              if (wType === 'line_chart') {
                const chartData = adaptTimeSeriesData(keys);
                return (
                  <div key={widget.id || idx} className={`glass-panel rounded-xl relative group ${colSpanClass}`}>
                    <MetricLineChart
                      data={chartData}
                      label={widgetLabel}
                      unit={unit}
                      color={connectorInfo?.color || '#FF3A89'}
                      onExpand={() =>
                        setExpandedWidget({
                          type: 'line_chart',
                          title: widgetLabel,
                          unit,
                          data: chartData,
                        })
                      }
                    />
                    {onOpenChat && (
                      <button
                        onClick={() => onOpenChat(connectorId, resourceId, `Analyze trends in ${widgetLabel}`)}
                        className="absolute top-4 right-10 opacity-0 group-hover:opacity-100 p-1.5 rounded-lg bg-surface-elevated border border-border-subtle text-gray-400 hover:text-accent transition-all cursor-pointer"
                        title="Ask Lear about this chart"
                      >
                        <MessageSquare size={13} />
                      </button>
                    )}
                  </div>
                );
              }

              // 3. Bar Chart (Categorical / Frequency breakdown)
              if (wType === 'bar_chart') {
                const barData = adaptBarData(keys, unit);
                return (
                  <div key={widget.id || idx} className={`glass-panel rounded-xl relative group ${colSpanClass}`}>
                    <BarChart
                      data={barData}
                      label={widgetLabel}
                      unit={unit}
                      color={connectorInfo?.color || '#FF3A89'}
                      onExpand={() =>
                        setExpandedWidget({
                          type: 'bar_chart',
                          title: widgetLabel,
                          unit,
                          data: barData,
                        })
                      }
                    />
                    {onOpenChat && (
                      <button
                        onClick={() => onOpenChat(connectorId, resourceId, `Inspect breakdown of ${widgetLabel}`)}
                        className="absolute top-4 right-10 opacity-0 group-hover:opacity-100 p-1.5 rounded-lg bg-surface-elevated border border-border-subtle text-gray-400 hover:text-accent transition-all cursor-pointer"
                        title="Ask Lear about this chart"
                      >
                        <MessageSquare size={13} />
                      </button>
                    )}
                  </div>
                );
              }

              // 4. Metric KPI Card
              if (wType === 'metric_card') {
                const cardData = adaptMetricCardData(keys);
                return (
                  <div key={widget.id || idx} className={`glass-panel rounded-xl flex flex-col justify-center gap-3 p-4 relative group ${colSpanClass}`}>
                    <MetricCard
                      label={widgetLabel}
                      value={cardData.value}
                      unit={unit || cardData.unit}
                      change={cardData.change}
                      history={cardData.history}
                    />
                    {onOpenChat && (
                      <button
                        onClick={() => onOpenChat(connectorId, resourceId, `Explain current value of ${widgetLabel}: ${cardData.value} ${unit || cardData.unit}`)}
                        className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 p-1.5 rounded-lg bg-surface-elevated border border-border-subtle text-gray-400 hover:text-accent transition-all cursor-pointer"
                        title="Ask Lear about this metric"
                      >
                        <MessageSquare size={13} />
                      </button>
                    )}
                  </div>
                );
              }

              // 5. Event & Alarm Timeline
              if (wType === 'event_timeline') {
                const matchedEvents = events.filter(ev =>
                  keys.length === 0 || keys.some(k => (ev.event_type || '').toLowerCase().includes(k.toLowerCase()))
                );
                return (
                  <div key={widget.id || idx} className={`glass-panel rounded-xl ${colSpanClass}`}>
                    <EventTimeline
                      events={matchedEvents.length > 0 ? matchedEvents : events}
                      label={widgetLabel}
                    />
                  </div>
                );
              }

              // 6. Health Checks Status Grid
              if (wType === 'status_grid') {
                return (
                  <div key={widget.id || idx} className={`glass-panel rounded-xl ${colSpanClass}`}>
                    <StatusGrid
                      items={statusItems}
                      label={widgetLabel}
                    />
                  </div>
                );
              }

              // Fallback
              return (
                <div key={widget.id || idx} className={`glass-panel rounded-xl p-4 flex flex-col justify-between ${colSpanClass}`}>
                  <span className="text-xs font-semibold uppercase tracking-wider text-gray-400 block mb-2">{widgetLabel}</span>
                  <div className="flex items-baseline gap-2">
                    <span className="text-2xl font-bold text-white">—</span>
                    <span className="text-xs text-gray-400">{unit}</span>
                  </div>
                  {widget.description && <p className="text-[11px] text-gray-500 mt-2">{widget.description}</p>}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Expand Modal View (Phase D2) */}
      <AnimatePresence>
        {expandedWidget && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-black/80 backdrop-blur-md">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="glass-card rounded-2xl border border-border-subtle p-6 w-full max-w-4xl max-h-[85vh] overflow-y-auto flex flex-col gap-6 shadow-2xl"
            >
              {/* Modal Header */}
              <div className="flex justify-between items-center pb-4 border-b border-border-subtle">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 rounded-xl bg-accent/15 border border-accent/30 text-accent">
                    <Maximize2 size={20} />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-white">{expandedWidget.title}</h3>
                    <p className="text-xs text-gray-400">
                      High-resolution telemetry inspection • {expandedWidget.data.length} datapoints
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => setExpandedWidget(null)}
                  className="p-2 rounded-lg bg-surface hover:bg-surface-elevated text-gray-400 hover:text-white transition-colors cursor-pointer"
                >
                  <X size={18} />
                </button>
              </div>

              {/* High-Resolution Chart Display */}
              <div className="glass-panel rounded-xl p-4">
                {expandedWidget.type === 'line_chart' ? (
                  <MetricLineChart
                    data={expandedWidget.data}
                    label={expandedWidget.title}
                    unit={expandedWidget.unit}
                    color={connectorInfo?.color || '#FF3A89'}
                    height={280}
                  />
                ) : (
                  <BarChart
                    data={expandedWidget.data}
                    label={expandedWidget.title}
                    unit={expandedWidget.unit}
                    color={connectorInfo?.color || '#FF3A89'}
                    height={280}
                  />
                )}
              </div>

              {/* Data Table */}
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-xs font-semibold text-gray-300">
                  <TableIcon size={14} className="text-accent" />
                  Raw Datapoints
                </div>
                <div className="max-h-52 overflow-y-auto rounded-xl border border-border-subtle bg-surface/40">
                  <table className="w-full text-xs text-left">
                    <thead className="bg-surface-elevated text-gray-400 font-mono border-b border-border-subtle sticky top-0">
                      <tr>
                        <th className="px-4 py-2">Index</th>
                        <th className="px-4 py-2">Label / Timestamp</th>
                        <th className="px-4 py-2 text-right">Value</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border-subtle font-mono">
                      {expandedWidget.data.map((item: any, i: number) => (
                        <tr key={i} className="hover:bg-white/5 transition-colors">
                          <td className="px-4 py-2 text-gray-500">{i + 1}</td>
                          <td className="px-4 py-2 text-gray-300">
                            {item.timestamp ? new Date(item.timestamp).toLocaleTimeString() : item.label || '—'}
                          </td>
                          <td className="px-4 py-2 text-right font-bold text-accent">
                            {item.value?.toLocaleString() || 0} {item.unit || expandedWidget.unit}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Modal Footer */}
              <div className="flex justify-end gap-3 pt-2 border-t border-border-subtle">
                {onOpenChat && (
                  <button
                    onClick={() => {
                      setExpandedWidget(null);
                      onOpenChat(
                        connectorId,
                        resourceId,
                        `Deep dive analysis of ${expandedWidget.title} with ${expandedWidget.data.length} datapoints`
                      );
                    }}
                    className="flex items-center gap-2 px-4 py-2 rounded-xl bg-accent text-gray-950 font-bold text-xs hover:bg-accent-light transition-all cursor-pointer shadow-lg"
                  >
                    <MessageSquare size={14} />
                    Analyze in Lear
                  </button>
                )}
                <button
                  onClick={() => setExpandedWidget(null)}
                  className="px-4 py-2 rounded-xl bg-surface hover:bg-surface-elevated text-gray-300 text-xs font-medium transition-colors cursor-pointer"
                >
                  Close
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Widget Layout Configurator Modal */}
      <WidgetConfigurator
        isOpen={isConfiguratorOpen}
        onClose={() => setIsConfiguratorOpen(false)}
        connectorId={connectorId}
        connectorName={displayName || connectorInfo?.name}
        resourceId={resourceId}
        currentWidgets={activeWidgets}
        onSaveLayout={handleSaveCustomLayout}
        onResetLayout={handleResetCustomLayout}
      />
    </motion.div>
  );
};

export default ServiceWidget;
