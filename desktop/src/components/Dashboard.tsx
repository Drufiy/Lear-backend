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
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  ShieldAlert,
  Brain,
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
    pushToast,
  } = useLear();

  const currentProject = propProject || ctxProject;
  const currentEnvironment = propEnvironment || ctxEnvironment || 'Production';

  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [activityEvents, setActivityEvents] = useState<DashboardActivityItem[]>([]);
  const [incidents, setIncidents] = useState<any[]>([]);
  const [latestIncident, setLatestIncident] = useState<any | null>(null);
  const [expandedThinkingId, setExpandedThinkingId] = useState<string | null>(null);
  const [notifiedIncidentIds, setNotifiedIncidentIds] = useState<Set<string>>(new Set());
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

  // Fetch all incidents from backend
  const fetchIncidents = useCallback(async () => {
    try {
      const res = await fetch('/api/incidents');
      if (res.ok) {
        const data = await res.json();
        const list = data.incidents || [];
        setIncidents(list);
        if (list.length > 0) {
          const top = list[0];
          setLatestIncident(top);

          // Trigger in-app approval notification toast once per incident
          if (top.status === 'ACTIVE' && top.requires_approval && !notifiedIncidentIds.has(top.incident_id)) {
            setNotifiedIncidentIds(prev => new Set(prev).add(top.incident_id));
            pushToast({
              title: `⚠️ Approval Required: ${top.service}`,
              message: top.proposed_remediation || top.diagnosis,
              severity: 'error',
              incidentId: top.incident_id,
              incidentData: {
                incidentId: top.incident_id,
                title: top.title,
                errorSummary: top.error_summary,
                diagnosis: top.diagnosis,
                agentThinking: top.agent_thinking,
                tags: top.tags,
                severity: top.severity,
                requiresApproval: top.requires_approval,
              },
            });
          }
        } else {
          setLatestIncident(null);
        }
      }
    } catch (e) {
      console.error('Failed to fetch incidents:', e);
    }
  }, [notifiedIncidentIds, pushToast]);

  // Initial load & fast periodic polling (3.5s) for instant error detection
  useEffect(() => {
    let mounted = true;
    const loadAll = async () => {
      setLoading(true);
      await Promise.all([fetchSummary(), fetchActivity(), fetchIncidents()]);
      if (mounted) setLoading(false);
    };
    loadAll();

    const interval = setInterval(() => {
      fetchSummary();
      fetchActivity();
      fetchIncidents();
    }, 3500);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [fetchSummary, fetchActivity, fetchIncidents]);

  const handleManualRefresh = async () => {
    setRefreshing(true);
    await Promise.all([fetchSummary(), fetchActivity(), fetchIncidents()]);
    setRefreshing(false);
  };

  const handleApproveIncident = async (incId: string) => {
    try {
      await fetch(`/api/incident/${incId}/approve`, { method: 'POST' });
      await fetchIncidents();
    } catch (e) {
      console.error('Approval failed:', e);
    }
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
            onClick={() => openChat({ initialPrompt: 'Provide real-time operational diagnostics and cluster status.' })}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-accent text-gray-950 font-bold text-xs hover:bg-accent-light transition-all shadow-lg cursor-pointer"
          >
            <Sparkles size={15} />
            <span>Open Lear Copilot</span>
          </button>
        </div>
      </div>

      {/* Context-Aware Incident Banner */}
      {latestIncident && latestIncident.status === 'ACTIVE' ? (
        <div className="bg-gradient-to-r from-rose-950/70 via-[#0E1422] to-rose-950/50 border-2 border-rose-500/60 rounded-2xl p-5 shadow-2xl shadow-rose-950/40 flex flex-col md:flex-row md:items-center justify-between gap-4 animate-in fade-in duration-300">
          <div className="flex items-start gap-3.5">
            <div className="p-3 bg-rose-500/20 rounded-xl text-rose-400 border border-rose-500/40 shrink-0">
              <ShieldAlert size={22} className="animate-pulse" />
            </div>
            <div className="space-y-1.5">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="px-2 py-0.5 rounded bg-rose-500/30 text-rose-300 font-mono font-bold text-[10px] border border-rose-500/50 uppercase">
                  {latestIncident.severity || 'CRITICAL'}
                </span>
                {latestIncident.tags?.map((tag: string, tidx: number) => (
                  <span
                    key={tidx}
                    className={`px-2 py-0.5 rounded font-mono font-bold text-[10px] border ${
                      tag.includes('FAILOVER')
                        ? 'bg-purple-500/20 text-purple-300 border-purple-500/40'
                        : tag.includes('APPROVAL')
                        ? 'bg-amber-500/20 text-amber-300 border-amber-500/40 animate-pulse'
                        : 'bg-white/10 text-gray-300 border-white/15'
                    }`}
                  >
                    [{tag}]
                  </span>
                ))}
                <span className="text-gray-400 font-mono text-[10px]">{latestIncident.cluster}</span>
              </div>
              <h3 className="text-sm md:text-base font-bold text-white leading-snug">{latestIncident.title}</h3>
              <p className="text-xs text-rose-200/90 leading-relaxed font-mono text-[11.5px]">
                {latestIncident.diagnosis || latestIncident.error_summary}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2.5 shrink-0 self-end md:self-center">
            {latestIncident.requires_approval && (
              <button
                onClick={() => handleApproveIncident(latestIncident.incident_id)}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-bold transition-all shadow-md cursor-pointer flex items-center gap-1.5"
              >
                <CheckCircle2 size={14} />
                <span>Approve Fix</span>
              </button>
            )}
            <button
              onClick={() =>
                openChat({
                  incidentId: latestIncident.incident_id,
                  title: latestIncident.title,
                  errorSummary: latestIncident.error_summary,
                  diagnosis: latestIncident.diagnosis,
                  agentThinking: latestIncident.agent_thinking,
                  tags: latestIncident.tags,
                  severity: latestIncident.severity,
                  requiresApproval: latestIncident.requires_approval,
                })
              }
              className="px-4 py-2 bg-rose-500 hover:bg-rose-600 text-white rounded-xl text-xs font-bold transition-all shadow-lg cursor-pointer flex items-center gap-1.5"
            >
              <Sparkles size={14} />
              <span>Resolve with Copilot</span>
            </button>
          </div>
        </div>
      ) : isAlerting ? (
        <div className="bg-rose-500/15 border border-rose-500/40 rounded-2xl p-4 flex items-center justify-between gap-4 animate-pulse shadow-lg shadow-rose-950/20">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-rose-500/25 rounded-xl text-rose-400 border border-rose-500/40">
              <AlertTriangle size={20} />
            </div>
            <div>
              <h3 className="text-sm font-bold text-rose-300">Cluster Anomaly Detected</h3>
              <p className="text-xs text-rose-300/80">
                Watcher stream detected errors or elevated latency in active infrastructure.
              </p>
            </div>
          </div>
          <button
            onClick={() =>
              openChat({
                title: 'Cluster Telemetry Anomaly',
                initialPrompt: 'Investigate cluster anomaly and container restart latencies.',
              })
            }
            className="px-4 py-2 bg-rose-500 hover:bg-rose-600 text-white rounded-xl text-xs font-bold transition-all shadow cursor-pointer shrink-0"
          >
            Investigate with Copilot
          </button>
        </div>
      ) : null}

      {/* 2. System Health Strip & Segmented Progress Bar */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 animate-pulse">
          {[1, 2, 3, 4].map(idx => (
            <div key={idx} className="h-28 rounded-2xl bg-surface/40 border border-border-subtle" />
          ))}
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Health Score Tile */}
            <div className="glass-panel rounded-2xl p-5 border border-border-subtle relative overflow-hidden flex flex-col justify-between h-32 group hover:border-accent/30 transition-all">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-gray-400 tracking-wider uppercase">Infrastructure Health</span>
                <div
                  className={`p-2 rounded-xl ${
                    healthScore >= 90
                      ? 'bg-emerald-500/10 text-emerald-400'
                      : healthScore >= 70
                      ? 'bg-amber-500/10 text-amber-400'
                      : 'bg-rose-500/10 text-rose-400'
                  }`}
                >
                  <ShieldCheck size={18} />
                </div>
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-3xl font-extrabold text-white tracking-tight">{healthScore}%</span>
                <span className="text-[11px] font-medium text-gray-400 font-mono">operational</span>
              </div>
            </div>

            {/* Configured Connectors */}
            <div className="glass-panel rounded-2xl p-5 border border-border-subtle relative overflow-hidden flex flex-col justify-between h-32 group hover:border-accent/30 transition-all">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-gray-400 tracking-wider uppercase">Active Integrations</span>
                <div className="p-2 rounded-xl bg-accent/10 text-accent">
                  <Layers size={18} />
                </div>
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-3xl font-extrabold text-white tracking-tight">
                  {summary?.counts?.configured_connectors ?? 0}
                </span>
                <span className="text-[11px] font-medium text-gray-400 font-mono">of 13 connectors</span>
              </div>
            </div>

            {/* Active Services */}
            <div className="glass-panel rounded-2xl p-5 border border-border-subtle relative overflow-hidden flex flex-col justify-between h-32 group hover:border-accent/30 transition-all">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-gray-400 tracking-wider uppercase">Monitored Services</span>
                <div className="p-2 rounded-xl bg-purple-500/10 text-purple-400">
                  <Server size={18} />
                </div>
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-3xl font-extrabold text-white tracking-tight">{totalServicesCount}</span>
                <span className="text-[11px] font-medium text-gray-400 font-mono">active in {currentEnvironment}</span>
              </div>
            </div>

            {/* Watcher Stream Status */}
            <div className="glass-panel rounded-2xl p-5 border border-border-subtle relative overflow-hidden flex flex-col justify-between h-32 group hover:border-accent/30 transition-all">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-gray-400 tracking-wider uppercase">Telemetry Stream</span>
                <div
                  className={`p-2 rounded-xl ${
                    watcherState === 'ACTIVE'
                      ? 'bg-emerald-500/10 text-emerald-400'
                      : watcherState === 'ALERTING'
                      ? 'bg-rose-500/10 text-rose-400'
                      : 'bg-surface text-gray-400'
                  }`}
                >
                  <Radio size={18} className={watcherState === 'ACTIVE' ? 'animate-pulse' : ''} />
                </div>
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-xl font-bold font-mono text-white tracking-tight">
                  {watcherState === 'ACTIVE' ? 'STREAMING' : watcherState}
                </span>
                <span className="text-[11px] font-medium text-gray-400 font-mono">
                  {activeWatches.length} active watches
                </span>
              </div>
            </div>
          </div>

          {/* Segmented Status Progress Bar */}
          <div className="p-4 rounded-2xl bg-surface/30 border border-border-subtle space-y-2">
            <div className="flex items-center justify-between text-xs font-mono">
              <span className="text-gray-400 font-sans font-semibold">Service Status Distribution</span>
              <div className="flex items-center gap-4 text-[11px]">
                <span className="flex items-center gap-1.5 text-emerald-400">
                  <span className="w-2 h-2 rounded-full bg-emerald-400" />
                  {healthyCount} Healthy ({Math.round(healthyPct)}%)
                </span>
                <span className="flex items-center gap-1.5 text-amber-400">
                  <span className="w-2 h-2 rounded-full bg-amber-400" />
                  {degradedCount} Degraded ({Math.round(degradedPct)}%)
                </span>
                <span className="flex items-center gap-1.5 text-rose-400">
                  <span className="w-2 h-2 rounded-full bg-rose-400" />
                  {errorCount} Error ({Math.round(errorPct)}%)
                </span>
              </div>
            </div>
            <div className="w-full h-2 rounded-full bg-surface-elevated overflow-hidden flex">
              <div
                style={{ width: `${healthyPct}%` }}
                className="bg-emerald-500 transition-all duration-500 shadow-sm"
              />
              <div
                style={{ width: `${degradedPct}%` }}
                className="bg-amber-500 transition-all duration-500 shadow-sm"
              />
              <div
                style={{ width: `${errorPct}%` }}
                className="bg-rose-500 transition-all duration-500 shadow-sm"
              />
            </div>
          </div>
        </div>
      )}

      {/* 3. Main Dashboard Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Column (8 Cols): Services & Watcher Control */}
        <div className="lg:col-span-8 space-y-8">
          {/* Real-time Watcher Sentinel Panel */}
          <WatcherPanel
            state={watcherState}
            activeCount={activeWatches.length}
            eventCount={liveWatcherEvents.length}
            isConnected={isConnected}
            activeDetails={activeWatchDetails}
            onToggleWatch={handleToggleWatchAll}
            onPauseWatch={w => pauseWatch(w)}
            onResumeWatch={w => resumeWatch(w)}
            onStopWatch={(c, t, w) => stopWatch(c, t, w)}
          />

          {/* Active Services Grid */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <Activity size={18} className="text-accent" />
                <h2 className="text-lg font-bold text-white tracking-tight">Active Infrastructure Telemetry</h2>
              </div>
              <button
                onClick={handleToggleWatchAll}
                className="text-xs font-semibold text-accent hover:underline flex items-center gap-1 cursor-pointer"
              >
                {watcherState === 'ACTIVE' ? 'Stop Watching All' : 'Watch All Services'}
              </button>
            </div>

            {services.length === 0 ? (
              <div className="glass-panel rounded-2xl p-10 border border-border-subtle text-center space-y-4">
                <div className="p-4 bg-surface rounded-2xl w-fit mx-auto text-gray-500">
                  <Server size={32} />
                </div>
                <div className="space-y-1">
                  <h3 className="font-bold text-base text-white">No services configured for {currentEnvironment}</h3>
                  <p className="text-xs text-gray-400 max-w-sm mx-auto leading-relaxed">
                    Connect your cloud accounts and configure monitors to start observing production telemetry.
                  </p>
                </div>
                {onOpenWizard && (
                  <button
                    onClick={onOpenWizard}
                    className="px-4 py-2 bg-accent hover:bg-accent-light text-gray-950 font-bold text-xs rounded-xl transition-all shadow cursor-pointer"
                  >
                    Open Configuration Wizard
                  </button>
                )}
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {services.map((svc: any, idx: number) => (
                  <ErrorBoundary key={idx} fallbackTitle={`Service Error (${svc.connector_id})`}>
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

        {/* Right Column (4 Cols): Ongoing & Past Autonomous Actions & SRE Thinking */}
        <div className="lg:col-span-4 space-y-6">
          {/* Ongoing & Past Autonomous SRE Actions */}
          <div className="glass-panel rounded-2xl p-5 border border-border-subtle flex flex-col min-h-[540px]">
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-border-subtle">
              <div className="flex items-center gap-2">
                <Activity size={16} className="text-accent" />
                <h3 className="font-bold text-sm text-white">Ongoing &amp; Past Actions</h3>
              </div>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-accent/15 text-accent border border-accent/25">
                {incidents.length} Records
              </span>
            </div>

            {/* Incidents Stream */}
            <div className="flex-1 overflow-y-auto space-y-3.5 pr-1 max-h-[580px]">
              {incidents.length === 0 ? (
                activityEvents.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-48 text-center text-gray-500 text-xs">
                    <Clock size={24} className="mb-2 opacity-40" />
                    <p>No autonomous actions recorded yet.</p>
                    <p className="text-[10px] text-gray-600 mt-1">
                      Lear will autonomously record detections, thinking, and failovers here.
                    </p>
                  </div>
                ) : (
                  activityEvents.map((item, idx) => (
                    <div
                      key={idx}
                      className="p-3 rounded-xl border text-xs leading-snug bg-surface/60 border-border-subtle text-gray-300"
                    >
                      <div className="flex items-center justify-between gap-2 mb-1 text-[10px]">
                        <span className="font-mono uppercase font-bold text-accent">{item.connector || 'SYSTEM'}</span>
                        <span className="text-gray-500 font-mono">
                          {item.timestamp ? new Date(item.timestamp).toLocaleTimeString() : ''}
                        </span>
                      </div>
                      <p className="font-medium text-gray-200 text-xs">{item.summary || item.event_type}</p>
                    </div>
                  ))
                )
              ) : (
                incidents.map((inc: any, idx: number) => {
                  const isResolved = inc.status === 'RESOLVED';
                  const isAwaiting = inc.requires_approval && !isResolved;
                  const isThinkingExpanded = expandedThinkingId === inc.incident_id;

                  return (
                    <div
                      key={idx}
                      className={`p-3.5 rounded-xl border text-xs leading-snug transition-all space-y-2.5 ${
                        isAwaiting
                          ? 'bg-amber-500/10 border-amber-500/30 text-amber-100 shadow-md shadow-amber-950/20'
                          : isResolved
                          ? 'bg-surface/70 border-emerald-500/25 text-gray-200'
                          : 'bg-rose-500/10 border-rose-500/30 text-rose-100 shadow-md shadow-rose-950/20'
                      }`}
                    >
                      {/* Tags & Timestamp */}
                      <div className="flex items-center justify-between gap-2 flex-wrap text-[10px]">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span
                            className={`font-mono font-bold uppercase px-1.5 py-0.5 rounded text-[9px] border ${
                              isResolved
                                ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
                                : isAwaiting
                                ? 'bg-amber-500/25 text-amber-300 border-amber-500/40 animate-pulse'
                                : 'bg-rose-500/25 text-rose-300 border-rose-500/40'
                            }`}
                          >
                            {inc.status}
                          </span>
                          {inc.tags?.map((t: string, t_idx: number) => (
                            <span
                              key={t_idx}
                              className="font-mono font-bold text-[9px] px-1.5 py-0.5 rounded bg-black/40 text-gray-300 border border-white/10"
                            >
                              [{t}]
                            </span>
                          ))}
                        </div>
                        <span className="text-gray-400 font-mono text-[9.5px]">
                          {inc.created_at ? inc.created_at.split(' ')[1] : ''}
                        </span>
                      </div>

                      {/* Title & Service */}
                      <div>
                        <h4 className="font-bold text-white text-xs leading-snug line-clamp-2">
                          {inc.title}
                        </h4>
                        <p className="text-[11px] text-gray-300/90 mt-1 line-clamp-2 leading-relaxed">
                          {inc.diagnosis || inc.error_summary}
                        </p>
                      </div>

                      {/* Expandable Agent's Thinking */}
                      {inc.agent_thinking && inc.agent_thinking.length > 0 && (
                        <div className="pt-1">
                          <button
                            onClick={() =>
                              setExpandedThinkingId(isThinkingExpanded ? null : inc.incident_id)
                            }
                            className="flex items-center gap-1 text-[10px] font-mono text-accent hover:underline cursor-pointer"
                          >
                            <Brain size={12} />
                            <span>Agent's Thinking ({inc.agent_thinking.length} phases)</span>
                            {isThinkingExpanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                          </button>

                          {isThinkingExpanded && (
                            <div className="mt-2 p-2.5 rounded-lg bg-black/50 border border-border-subtle font-mono text-[10px] space-y-1.5 text-gray-300">
                              {inc.agent_thinking.map((thought: string, phIdx: number) => (
                                <div key={phIdx} className="leading-relaxed">
                                  <span className="text-accent font-bold">Phase {phIdx + 1}:</span> {thought}
                                </div>
                              ))}
                              {inc.episodic_memory && (
                                <div className="pt-1.5 border-t border-white/10 text-purple-300">
                                  <span className="font-bold text-purple-400">🧠 Episodic Memory:</span> {inc.episodic_memory}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Action Bar */}
                      <div className="pt-2 border-t border-white/10 flex items-center justify-between gap-2">
                        <button
                          onClick={() =>
                            openChat({
                              incidentId: inc.incident_id,
                              title: inc.title,
                              errorSummary: inc.error_summary,
                              diagnosis: inc.diagnosis,
                              agentThinking: inc.agent_thinking,
                              tags: inc.tags,
                              severity: inc.severity,
                              requiresApproval: inc.requires_approval,
                            })
                          }
                          className="flex items-center gap-1 text-[10.5px] text-accent hover:text-white font-bold cursor-pointer"
                        >
                          <Sparkles size={11} />
                          <span>Resolve with Copilot &rarr;</span>
                        </button>

                        {isAwaiting && (
                          <button
                            onClick={() => handleApproveIncident(inc.incident_id)}
                            className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-[10px] font-bold cursor-pointer transition-all flex items-center gap-1 shadow"
                          >
                            <CheckCircle2 size={11} />
                            <span>Approve Fix</span>
                          </button>
                        )}
                      </div>
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
              onClick={() =>
                openChat({
                  title: 'Full Infrastructure Diagnostics',
                  initialPrompt: 'Perform full cluster health check and audit all pod statuses.',
                })
              }
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
                onClick={() =>
                  openChat({
                    title: 'CrashLoop Container Audit',
                    initialPrompt: 'Check for crash-looping containers and inspect backoff restart counts in lear-demo.',
                  })
                }
                className="text-left text-[11px] text-gray-400 hover:text-white transition-colors cursor-pointer flex items-center justify-between py-1"
              >
                <span>&bull; Check for crash-looping containers</span>
                <ArrowRight size={10} className="text-accent" />
              </button>
              <button
                onClick={() =>
                  openChat({
                    title: 'Audit Watcher Latencies',
                    initialPrompt: 'Audit active watcher stream latencies and verify event throughput.',
                  })
                }
                className="text-left text-[11px] text-gray-400 hover:text-white transition-colors cursor-pointer flex items-center justify-between py-1"
              >
                <span>&bull; Audit active watcher latencies</span>
                <ArrowRight size={10} className="text-accent" />
              </button>
              <button
                onClick={() =>
                  openChat({
                    title: 'Verify AWS STS Credentials',
                    initialPrompt: 'Verify AWS STS credentials and test IAM caller identity for EKS cluster.',
                  })
                }
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
