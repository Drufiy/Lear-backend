import { useState } from 'react';
import { Plus, Sparkles, Server, Activity, AlertTriangle, ShieldCheck, Stethoscope } from 'lucide-react';
import { WatcherPanel } from './WatcherPanel';
import ServiceWidget from './ServiceWidget';
import ErrorBoundary from './ErrorBoundary';
import Chatbot from './Chatbot';
import useWatcher from '../hooks/useWatcher';

interface DashboardProps {
  activeProject?: any;
  activeEnvironment: string;
  onOpenWizard?: () => void;
}

export default function Dashboard({
  activeProject,
  activeEnvironment = 'Production',
  onOpenWizard,
}: DashboardProps) {
  const [chatOpen, setChatOpen] = useState(false);
  const [chatContext, setChatContext] = useState<{ connectorId?: string; resourceId?: string } | null>(null);

  const {
    isConnected,
    watcherState,
    activeWatches,
    activeWatchDetails,
    events,
    startWatch,
    stopWatch,
    pauseWatch,
    resumeWatch,
  } = useWatcher();

  // Extract services for the active environment
  const currentEnvObj = activeProject?.environments?.find(
    (e: any) => e.name.toLowerCase() === activeEnvironment.toLowerCase()
  ) || activeProject?.environments?.[0];

  const services = currentEnvObj?.services || [];

  const handleOpenChatForService = (connectorId: string, resourceId?: string) => {
    setChatContext({ connectorId, resourceId });
    setChatOpen(true);
  };

  const handleToggleWatchAll = () => {
    if (watcherState === 'ACTIVE') {
      services.forEach((s: any) => stopWatch(s.connector_id, s.resource_id));
    } else {
      services.forEach((s: any) => startWatch(s.connector_id, s.resource_id || 'default'));
    }
  };

  const isAlerting = watcherState === 'ALERTING';
  const healthyCount = services.length; // Simplified for now, real app might check actual individual states
  const healthScore = services.length === 0 ? 0 : (isAlerting ? 60 : 100);

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      {/* Top Header */}
      <div className="flex flex-wrap justify-between items-center gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <h1 className="text-3xl font-bold tracking-tight text-white">
              {activeProject?.name || 'Default Project'}
            </h1>
            <span className="text-xs font-mono px-2 py-0.5 rounded bg-surface-elevated border border-border-subtle text-accent">
              {activeEnvironment}
            </span>
          </div>
          <p className="text-sm text-gray-400">
            Live telemetry, AI diagnostics, and proactive watching for {services.length} services.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              setChatContext(null);
              setChatOpen(true);
            }}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-accent text-gray-950 font-bold text-xs hover:bg-accent-light transition-all shadow-lg cursor-pointer"
          >
            <Sparkles size={16} /> Open Lear Copilot
          </button>
        </div>
      </div>

      {/* Incident Banner */}
      {isAlerting && (
        <div className="bg-rose-500/20 border border-rose-500/50 rounded-2xl p-4 flex items-center justify-between gap-4 animate-pulse">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-rose-500/30 rounded-full text-rose-400">
              <AlertTriangle size={20} />
            </div>
            <div>
              <h3 className="text-sm font-bold text-rose-400">Critical Alert Detected</h3>
              <p className="text-xs text-rose-300/80">Watcher detected anomalies or failures in connected services.</p>
            </div>
          </div>
          <button className="px-4 py-2 bg-rose-500 text-white rounded-xl text-xs font-bold hover:bg-rose-600 transition-colors">
            View Incident Details
          </button>
        </div>
      )}

      {/* Overview Stats (Health Score) & Quick Diagnostics */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="glass-panel rounded-2xl p-5 border border-border-subtle flex items-center gap-4">
          <div className={`p-4 rounded-xl flex items-center justify-center ${isAlerting ? 'bg-amber-500/20 text-amber-500' : 'bg-emerald-500/20 text-emerald-500'}`}>
            <Activity size={24} />
          </div>
          <div>
            <p className="text-xs text-gray-400 font-medium">System Health Score</p>
            <div className="flex items-baseline gap-2">
              <h2 className="text-2xl font-bold text-white">{healthScore}%</h2>
              <span className={`text-xs font-semibold ${isAlerting ? 'text-amber-500' : 'text-emerald-500'}`}>
                {isAlerting ? 'Degraded' : 'Optimal'}
              </span>
            </div>
          </div>
        </div>
        
        <div className="glass-panel rounded-2xl p-5 border border-border-subtle flex flex-col justify-center">
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs text-gray-400 font-medium">Active Services</p>
            <ShieldCheck size={16} className="text-accent" />
          </div>
          <h2 className="text-2xl font-bold text-white">{healthyCount}</h2>
        </div>

        <div className="glass-panel rounded-2xl p-5 border border-border-subtle flex flex-col justify-center gap-2">
          <p className="text-xs text-gray-400 font-medium mb-1">Quick Diagnostics</p>
          <button className="flex items-center gap-2 px-3 py-2 bg-surface hover:bg-surface-elevated border border-border-subtle rounded-xl text-xs font-semibold text-gray-200 transition-colors w-full cursor-pointer">
            <Stethoscope size={14} className="text-accent" /> Run System Diagnostic
          </button>
        </div>
      </div>

      {/* 1. Watcher Live Control Panel */}
      <WatcherPanel
        state={watcherState}
        activeCount={activeWatches.length}
        eventCount={events.length}
        isConnected={isConnected}
        activeDetails={activeWatchDetails}
        onToggleWatch={handleToggleWatchAll}
        onPauseWatch={pauseWatch}
        onResumeWatch={resumeWatch}
        onStopWatch={stopWatch}
      />

      {/* 2. Services Metric Widgets */}
      {services.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center glass-panel rounded-2xl border border-dashed border-border-subtle">
          <div className="w-14 h-14 rounded-2xl bg-surface flex items-center justify-center mb-4 text-gray-400">
            <Server size={26} />
          </div>
          <h3 className="text-lg font-bold text-white mb-1">No Services Configured in {activeEnvironment}</h3>
          <p className="text-xs text-gray-400 max-w-md mb-6">
            Connect an AWS EC2 instance, Kubernetes cluster, or GitHub repository to view live telemetry and AI widgets.
          </p>
          {onOpenWizard && (
            <button
              onClick={onOpenWizard}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-accent hover:bg-accent-light text-gray-950 font-bold text-xs transition-all cursor-pointer shadow-lg"
            >
              <Plus size={16} /> Connect Infrastructure Service
            </button>
          )}
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

      {/* AI Copilot Drawer */}
      <Chatbot
        isOpen={chatOpen}
        onClose={() => setChatOpen(false)}
        serviceContext={chatContext}
      />
    </div>
  );
}
