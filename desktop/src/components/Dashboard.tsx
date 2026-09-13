import { useState, useEffect, useCallback } from 'react';
import {
  Activity,
  ShieldCheck,
  Stethoscope,
  Sparkles,
  Plus,
  Server,
  AlertTriangle,
  ArrowRight,
  RefreshCw,
  Layers,
  Radio,
  FileText,
  Clock,
} from 'lucide-react';
import { WatcherPanel } from './WatcherPanel';
import ServiceWidget from './ServiceWidget';
import ErrorBoundary from './ErrorBoundary';
import useWatcher from '../hooks/useWatcher';
import { useLear } from '../context/LearContext';

interface DashboardProps {
  activeProject?: any;
  activeEnvironment?: string;
  onOpenWizard?: () => void;
}

interface DashboardSummary {
  status: 'healthy' | 'degraded' | 'error' | 'unconfigured';
  health_score: number;
  counts: {
    total_services: number;
    configured_connectors: number;
    unconfigured_connectors: number;
    healthy: number;
    degraded: number;
    error: number;
  };
  active_watches_count: number;
  projects_count: number;
  cached?: boolean;
}

interface DashboardActivityItem {
  watch_id?: string;
  connector?: string;
  event_type?: string;
  summary?: string;
  timestamp?: string;
  severity?: 'info' | 'warning' | 'error';
}

export default function Dashboard({
  activeProject: propProject,
  activeEnvironment: propEnvironment = 'Production',
  onOpenWizard,
}: DashboardProps) {
  const {
    projects,
    activeProject: ctxProject,
    activeEnvironment: ctxEnvironment,
    setActiveTab,
    setOpenCreateProjectModal,
    openChat,
  } = useLear();

  const currentProject = propProject || ctxProject;
  const currentEnvironment = propEnvironment || ctxEnvironment || 'Production';

  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [activityEvents, setActivityEvents] = useState<DashboardActivityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const {
    isConnected,
    watcherState,
    activeWatches,
    activeWatchDetails,
    events: liveWatcherEvents,
    startWatch,
    stopWatch,
    pauseWatch,
    resumeWatch,
  } = useWatcher();

  // Extract services for the active environment
  const currentEnvObj = currentProject?.environments?.find(
    (e: any) => e.name.toLowerCase() === currentEnvironment.toLowerCase()
  ) || currentProject?.environments?.[0];

  const services = currentEnvObj?.services || [];

  // Fetch dashboard summary
  const fetchSummary = useCallback(async () => {
    try {
      const res = await fetch('/api/dashboard/summary');
      if (res.ok) {
        const data = await res.json();
        setSummary(data);
      }
    } catch (e) {
      console.error('Failed to fetch dashboard summary:', e);
    }
  }, []);

  // Fetch recent cross-service activity
  const fetchActivity = useCallback(async () => {
    try {
      const res = await fetch('/api/dashboard/activity?limit=8');
      if (res.ok) {
        const data = await res.json();
        if (data.events && Array.isArray(data.events)) {
          setActivityEvents(data.events);
        }
      }
    } catch (e) {
      console.error('Failed to fetch dashboard activity:', e);
    }
  }, []);

  // Initial load & periodic refresh
  useEffect(() => {
    let mounted = true;
    const loadAll = async () => {
      setLoading(true);
      await Promise.all([fetchSummary(), fetchActivity()]);
      if (mounted) setLoading(false);
    };
    loadAll();

    const interval = setInterval(() => {
      fetchSummary();
      fetchActivity();
    }, 15000);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [fetchSummary, fetchActivity]);

  const handleManualRefresh = async () => {
    setRefreshing(true);
    await Promise.all([fetchSummary(), fetchActivity()]);
    setRefreshing(false);
  };

  const handleToggleWatchAll = () => {
    if (watcherState === 'ACTIVE') {
      services.forEach((s: any) => stopWatch(s.connector_id, s.resource_id));
    } else {
      services.forEach((s: any) => startWatch(s.connector_id, s.resource_id || 'default'));
    }
  };

  const handleOpenChatForService = (connectorId: string, resourceId?: string) => {
    openChat({ connectorId, resourceId });
  };

  const isAlerting = watcherState === 'ALERTING' || summary?.status === 'error';
  const healthScore = summary?.health_score ?? (services.length === 0 ? 0 : isAlerting ? 60 : 100);
  const totalProjectsCount = projects.length || summary?.projects_count || 1;
  const totalServicesCount = summary?.counts?.total_services || services.length;

  // Segment widths for the animated health bar
  const healthyCount = summary?.counts?.healthy ?? services.length;
  const degradedCount = summary?.counts?.degraded ?? 0;
  const errorCount = summary?.counts?.error ?? 0;
  const totalEntities = Math.max(1, healthyCount + degradedCount + errorCount);

  const healthyPct = (healthyCount / totalEntities) * 100;
  const degradedPct = (degradedCount / totalEntities) * 100;
  const errorPct = (errorCount / totalEntities) * 100;

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      {/* 1. Mission Control Header */}
      <div className="flex flex-wrap justify-between items-start gap-4 pb-2 border-b border-border-subtle/60">
        <div>
          <div className="flex items-center gap-3 mb-1.5">
            <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
              {currentProject?.name || 'Default Project'}
            </h1>
            <span className="text-xs font-mono font-bold px-2.5 py-1 rounded-lg bg-surface border border-border-subtle text-accent shadow-sm">
              {currentEnvironment}
            </span>
            {isConnected && (
              <span className="flex items-center gap-1 text-[11px] font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" /> Live Telemetry
              </span>
            )}
          </div>
          <p className="text-xs md:text-sm text-gray-400 flex items-center gap-2">
            <span>
              Mission Control: Monitoring <strong className="text-white font-semibold">{totalServicesCount}</strong> services across{' '}
              <strong className="text-white font-semibold">{totalProjectsCount}</strong> projects.
            </span>
          </p>
        </div>

        {/* Quick Actions Command Bar */}
        <div className="flex flex-wrap items-center gap-2.5">
          <button
            onClick={handleManualRefresh}
            disabled={refreshing}
            title="Refresh dashboard metrics"
            className="p-2.5 rounded-xl bg-surface hover:bg-surface-elevated border border-border-subtle text-gray-300 hover:text-white transition-all cursor-pointer disabled:opacity-50"
          >
            <RefreshCw size={15} className={refreshing ? 'animate-spin text-accent' : ''} />
          </button>

          <button
            onClick={() => setActiveTab('activity')}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-surface hover:bg-surface-elevated border border-border-subtle text-xs font-semibold text-gray-300 hover:text-white transition-all cursor-pointer"
          >
            <FileText size={14} className="text-gray-400" />
            <span>Activity Log</span>
          </button>

          <button
            onClick={() => setOpenCreateProjectModal(true)}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-surface hover:bg-surface-elevated border border-border-subtle text-xs font-semibold text-gray-300 hover:text-white transition-all cursor-pointer"
          >
            <Plus size={14} className="text-accent" />
            <span>New Project</span>
          </button>

          <button
            onClick={() => openChat(null)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-accent text-gray-950 font-bold text-xs hover:bg-accent-light transition-all shadow-lg cursor-pointer"
          >
            <Sparkles size={15} />
            <span>Open Lear Copilot</span>
          </button>
        </div>
      </div>

      {/* Critical Incident Banner */}
      {isAlerting && (
        <div className="bg-rose-500/15 border border-rose-500/40 rounded-2xl p-4 flex items-center justify-between gap-4 animate-pulse shadow-lg shadow-rose-950/20">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-rose-500/25 rounded-xl text-rose-400 border border-rose-500/40">
              <AlertTriangle size={20} />
            </div>
            <div>
              <h3 className="text-sm font-bold text-rose-300">Critical Anomaly Detected</h3>
              <p className="text-xs text-rose-300/80">
                Watcher stream detected errors or elevated latency in active infrastructure.
              </p>
            </div>
          </div>
          <button
            onClick={() => openChat(null)}
            className="px-4 py-2 bg-rose-500 hover:bg-rose-600 text-white rounded-xl text-xs font-bold transition-all shadow cursor-pointer shrink-0"
          >
            Investigate with Copilot
          </button>
        </div>
      )}

      {/* 2. System Health Strip & Segmented Progress Bar */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 animate-pulse">
          {[1, 2, 3, 4].map(idx => (
            <div key={idx} className="h-28 rounded-2xl bg-surface/40 border border-border-subtle" />
          ))}
        </div>
      ) : (
        <div className="space-y-4">
          {/* Top KPI Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
            {/* System Health Score Card */}
            <div className="glass-panel rounded-2xl p-5 border border-border-subtle flex flex-col justify-between">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-gray-400 font-medium">System Health Score</span>
                <div
                  className={`p-1.5 rounded-lg ${
                    healthScore >= 90
                      ? 'bg-emerald-500/20 text-emerald-400'
                      : healthScore >= 70
                      ? 'bg-amber-500/20 text-amber-400'
                      : 'bg-rose-500/20 text-rose-400'
                  }`}
                >
                  <Activity size={16} />
                </div>
              </div>
              <div className="flex items-baseline gap-2.5">
                <h2 className="text-3xl font-extrabold text-white">{healthScore}%</h2>
                <span
                  className={`text-xs font-bold uppercase tracking-wider ${
                    healthScore >= 90
                      ? 'text-emerald-400'
                      : healthScore >= 70
                      ? 'text-amber-400'
                      : 'text-rose-400'
                  }`}
                >
                  {summary?.status || (healthScore >= 90 ? 'Optimal' : 'Degraded')}
                </span>
              </div>
            </div>

            {/* Active Watches KPI */}
            <div className="glass-panel rounded-2xl p-5 border border-border-subtle flex flex-col justify-between">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-gray-400 font-medium">Active Watch Handles</span>
                <div className="p-1.5 rounded-lg bg-accent/15 text-accent">
                  <Radio size={16} />
                </div>
              </div>
              <div className="flex items-baseline gap-2">
                <h2 className="text-3xl font-extrabold text-white">
                  {summary?.active_watches_count ?? activeWatches.length}
                </h2>
                <span className="text-xs font-semibold text-gray-400 font-mono">
                  {watcherState === 'ACTIVE' ? 'LIVE' : watcherState}
                </span>
              </div>
            </div>

            {/* Connected Services KPI */}
            <div className="glass-panel rounded-2xl p-5 border border-border-subtle flex flex-col justify-between">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-gray-400 font-medium">Connected Services</span>
                <div className="p-1.5 rounded-lg bg-blue-500/15 text-blue-400">
                  <ShieldCheck size={16} />
                </div>
              </div>
              <div className="flex items-baseline gap-2">
                <h2 className="text-3xl font-extrabold text-white">{services.length}</h2>
                <span className="text-xs text-gray-400 font-mono">in {currentEnvironment}</span>
              </div>
            </div>

            {/* Total Projects KPI */}
            <div className="glass-panel rounded-2xl p-5 border border-border-subtle flex flex-col justify-between">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-gray-400 font-medium">Total Project Stacks</span>
                <div className="p-1.5 rounded-lg bg-purple-500/15 text-purple-400">
                  <Layers size={16} />
                </div>
              </div>
              <div className="flex items-baseline justify-between">
                <h2 className="text-3xl font-extrabold text-white">{totalProjectsCount}</h2>
                <button
                  onClick={() => setActiveTab('projects')}
                  className="text-xs text-accent hover:underline font-semibold cursor-pointer"
                >
                  View All &rarr;
                </button>
              </div>
            </div>
          </div>

          {/* Segmented Animated System Health Bar */}
          <div className="glass-panel rounded-2xl p-4 border border-border-subtle bg-surface/30">
            <div className="flex items-center justify-between mb-2 text-xs">
              <span className="font-semibold text-gray-300">Infrastructure Health Distribution</span>
              <div className="flex items-center gap-4 text-[11px] font-mono">
                <span className="flex items-center gap-1 text-emerald-400">
                  <span className="w-2 h-2 rounded-full bg-emerald-400" />
                  {healthyCount} Healthy
                </span>
                {degradedCount > 0 && (
                  <span className="flex items-center gap-1 text-amber-400">
                    <span className="w-2 h-2 rounded-full bg-amber-400" />
                    {degradedCount} Degraded
                  </span>
                )}
                {errorCount > 0 && (
                  <span className="flex items-center gap-1 text-rose-400">
                    <span className="w-2 h-2 rounded-full bg-rose-400" />
                    {errorCount} Error
                  </span>
                )}
              </div>
            </div>

            {/* Progress Segment Bar */}
            <div className="w-full h-3 rounded-full bg-black/50 overflow-hidden flex p-0.5 border border-border-subtle">
              {healthyPct > 0 && (
                <div
                  style={{ width: `${healthyPct}%` }}
                  className="h-full bg-emerald-500 rounded-l-full transition-all duration-500 shadow-sm"
                  title={`${healthyPct.toFixed(1)}% Healthy`}
                />
              )}
              {degradedPct > 0 && (
                <div
                  style={{ width: `${degradedPct}%` }}
                  className="h-full bg-amber-500 transition-all duration-500 shadow-sm"
                  title={`${degradedPct.toFixed(1)}% Degraded`}
                />
              )}
              {errorPct > 0 && (
                <div
                  style={{ width: `${errorPct}%` }}
                  className="h-full bg-rose-500 rounded-r-full transition-all duration-500 shadow-sm"
                  title={`${errorPct.toFixed(1)}% Error`}
                />
              )}
            </div>
          </div>
        </div>
      )}

      {/* 3. Mission Control Main Grid (Split View) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column (8 Cols): Watcher Panel & Service Widgets */}
        <div className="lg:col-span-8 space-y-6">
          {/* Live Watcher Control Center */}
          <WatcherPanel
            state={watcherState}
            activeCount={activeWatches.length}
            eventCount={liveWatcherEvents.length}
            isConnected={isConnected}
            activeDetails={activeWatchDetails}
            onToggleWatch={handleToggleWatchAll}
            onPauseWatch={pauseWatch}
            onResumeWatch={resumeWatch}
            onStopWatch={stopWatch}
          />

          {/* Service Telemetry Widgets */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <Server size={18} className="text-accent" />
                <span>Service Telemetry &amp; Widgets</span>
              </h3>
              <span className="text-xs font-mono text-gray-400">
                {services.length} registered in {currentEnvironment}
              </span>
            </div>

            {services.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center glass-panel rounded-2xl border border-dashed border-border-subtle">
                <div className="w-12 h-12 rounded-2xl bg-surface flex items-center justify-center mb-3 text-gray-400">
                  <Server size={22} />
                </div>
                <h4 className="text-base font-bold text-white mb-1">
                  No Services Configured in {currentEnvironment}
                </h4>
                <p className="text-xs text-gray-400 max-w-sm mb-5">
                  Connect an AWS EC2 instance, Kubernetes cluster, or GitHub repository to visualize live metrics.
                </p>
                <button
                  onClick={() => {
                    if (onOpenWizard) onOpenWizard();
                    else setActiveTab('integrations');
                  }}
                  className="flex items-center gap-2 px-4 py-2 rounded-xl bg-accent hover:bg-accent-light text-gray-950 font-bold text-xs transition-all cursor-pointer shadow-lg"
                >
                  <Plus size={15} /> Connect Infrastructure Service
                </button>
              </div>
            ) : (
              <div className="space-y-6">
                {services.map((svc: any, index: number) => (
                  <ErrorBoundary
                    key={`${svc.connector_id}-${svc.resource_id || index}`}
                    fallbackTitle={`${svc.display_name || svc.connector_id} Widget Error`}
                    fallbackMessage="Unable to render service widget. Check connection and logs."
                  >
                    <ServiceWidget
                      connectorId={svc.connector_id}
                      resourceId={svc.resource_id}
                      displayName={svc.display_name}
                      onOpenChat={handleOpenChatForService}
                    />
                  </ErrorBoundary>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right Column (4 Cols): Live Activity Feed & Diagnostics */}
        <div className="lg:col-span-4 space-y-6">
          {/* Recent Cross-Service Activity Feed */}
          <div className="glass-panel rounded-2xl p-5 border border-border-subtle flex flex-col h-[520px]">
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-border-subtle">
              <div className="flex items-center gap-2">
                <Clock size={16} className="text-accent" />
                <h3 className="font-bold text-sm text-white">Recent Activity</h3>
              </div>
              <button
                onClick={() => setActiveTab('activity')}
                className="text-[11px] text-accent hover:underline font-semibold cursor-pointer"
              >
                View All &rarr;
              </button>
            </div>

            {/* Events Stream */}
            <div className="flex-1 overflow-y-auto space-y-3 pr-1">
              {activityEvents.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-center text-gray-500 text-xs">
                  <Clock size={24} className="mb-2 opacity-40" />
                  <p>No activity events recorded yet.</p>
                  <p className="text-[10px] text-gray-600 mt-1">
                    Start a watch or run Copilot actions to generate events.
                  </p>
                </div>
              ) : (
                activityEvents.map((item, idx) => {
                  const isErr = item.severity === 'error' || item.event_type?.includes('ERROR') || item.event_type?.includes('FAIL');
                  const isWarn = item.severity === 'warning';
                  return (
                    <div
                      key={idx}
                      className={`p-3 rounded-xl border text-xs leading-snug transition-all ${
                        isErr
                          ? 'bg-rose-500/10 border-rose-500/30 text-rose-200'
                          : isWarn
                          ? 'bg-amber-500/10 border-amber-500/30 text-amber-200'
                          : 'bg-surface/60 border-border-subtle text-gray-300 hover:border-accent/40'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2 mb-1 text-[10px]">
                        <span className="font-mono uppercase font-bold text-accent">
                          {item.connector || 'SYSTEM'}
                        </span>
                        <span className="text-gray-500 font-mono">
                          {item.timestamp ? new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
                        </span>
                      </div>
                      <p className="font-medium text-gray-200 text-xs line-clamp-2">
                        {item.summary || item.event_type || 'Infrastructure event'}
                      </p>
                      {item.watch_id && (
                        <span className="inline-block mt-1.5 text-[9px] font-mono text-gray-400 bg-black/30 px-1.5 py-0.5 rounded">
                          {item.watch_id}
                        </span>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Quick System Diagnostics Card */}
          <div className="glass-panel rounded-2xl p-5 border border-border-subtle bg-surface/20 space-y-3.5">
            <div className="flex items-center gap-2">
              <Stethoscope size={16} className="text-accent" />
              <h3 className="font-bold text-sm text-white">System Diagnostics</h3>
            </div>
            <p className="text-xs text-gray-400 leading-relaxed">
              Analyze all active infrastructure services, verify telemetry latencies, and check for anomalies.
            </p>

            <button
              onClick={() => openChat(null)}
              className="flex items-center justify-center gap-2 w-full py-2.5 px-3 rounded-xl bg-surface hover:bg-surface-elevated border border-border-subtle hover:border-accent/50 text-xs font-bold text-white transition-all cursor-pointer shadow-sm"
            >
              <Sparkles size={14} className="text-accent" />
              <span>Launch Copilot Diagnostics</span>
            </button>

            <div className="pt-2 border-t border-border-subtle flex flex-col gap-1.5">
              <span className="text-[10px] uppercase font-bold text-gray-400 tracking-wider">
                Common Inquiries
              </span>
              <button
                onClick={() => openChat(null)}
                className="text-left text-[11px] text-gray-400 hover:text-white transition-colors cursor-pointer flex items-center justify-between py-1"
              >
                <span>&bull; Check for crash-looping containers</span>
                <ArrowRight size={10} className="text-accent" />
              </button>
              <button
                onClick={() => openChat(null)}
                className="text-left text-[11px] text-gray-400 hover:text-white transition-colors cursor-pointer flex items-center justify-between py-1"
              >
                <span>&bull; Audit active watcher latencies</span>
                <ArrowRight size={10} className="text-accent" />
              </button>
              <button
                onClick={() => openChat(null)}
                className="text-left text-[11px] text-gray-400 hover:text-white transition-colors cursor-pointer flex items-center justify-between py-1"
              >
                <span>&bull; Verify credentials and STS status</span>
                <ArrowRight size={10} className="text-accent" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
