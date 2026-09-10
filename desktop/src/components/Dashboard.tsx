import { useState } from 'react';
import { Plus, Sparkles, Server } from 'lucide-react';
import WatcherPanel from './WatcherPanel';
import ServiceWidget from './ServiceWidget';
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
    events,
    startWatch,
    stopWatch,
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

      {/* 1. Watcher Live Control Panel */}
      <WatcherPanel
        state={watcherState}
        activeCount={activeWatches.length}
        eventCount={events.length}
        isConnected={isConnected}
        onToggleWatch={services.length > 0 ? handleToggleWatchAll : undefined}
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
            <ServiceWidget
              key={`${svc.connector_id}-${svc.resource_id || index}`}
              connectorId={svc.connector_id}
              resourceId={svc.resource_id}
              displayName={svc.display_name}
              onOpenChat={handleOpenChatForService}
            />
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
