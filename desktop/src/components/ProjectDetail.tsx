import React, { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import {
  ArrowLeft,
  Layers,
  Plus,
  Trash2,
  Activity,
  Server,
  Copy,
  Check,
  X,
  Sparkles,
  RefreshCw,
} from 'lucide-react';
import { Project, ServiceItem, useLear } from '../context/LearContext';

interface ProjectDetailProps {
  project: Project;
  onBack: () => void;
  onProjectUpdated: (updated: Project) => void;
  onSelectServiceForTelemetry?: (service: ServiceItem, env: string) => void;
}

interface ConnectorMeta {
  id: string;
  name: string;
  category: string;
  configured: boolean;
  color?: string;
  icon?: string;
}

interface DiscoveredResource {
  id: string;
  name: string;
  type: string;
  state: string;
}

interface ServiceStatusInfo {
  connector_id: string;
  resource_id: string;
  display_name: string;
  status: 'healthy' | 'warning' | 'error' | 'unknown';
  state_label: string;
  detail?: string;
  last_checked?: string;
}

interface EnvironmentStatusInfo {
  name: string;
  status: 'healthy' | 'warning' | 'error' | 'unknown';
  services: ServiceStatusInfo[];
}

interface ProjectStatusResponse {
  project_id: string;
  status: 'healthy' | 'warning' | 'error' | 'unknown';
  summary: {
    healthy: number;
    warning: number;
    error: number;
    unknown: number;
    total: number;
  };
  environments: EnvironmentStatusInfo[];
}

export const ProjectDetail: React.FC<ProjectDetailProps> = ({
  project,
  onBack,
  onProjectUpdated,
  onSelectServiceForTelemetry,
}) => {
  const { selectEnvironment, selectProject, setActiveTab, openChat } = useLear();

  const [activeEnv, setActiveEnv] = useState<string>(() => {
    return project.environments?.[0]?.name || 'Production';
  });

  const [projectStatus, setProjectStatus] = useState<ProjectStatusResponse | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Modals
  const [showAddServiceModal, setShowAddServiceModal] = useState(false);
  const [showAddEnvModal, setShowAddEnvModal] = useState(false);
  const [newEnvName, setNewEnvName] = useState('');

  // Add Service Form state
  const [connectors, setConnectors] = useState<ConnectorMeta[]>([]);
  const [selectedConnector, setSelectedConnector] = useState<string>('');
  const [discoveredResources, setDiscoveredResources] = useState<DiscoveredResource[]>([]);
  const [loadingResources, setLoadingResources] = useState(false);
  const [selectedResourceId, setSelectedResourceId] = useState<string>('');
  const [customResourceId, setCustomResourceId] = useState<string>('');
  const [serviceDisplayName, setServiceDisplayName] = useState<string>('');
  const [savingService, setSavingService] = useState(false);
  const [addServiceError, setAddServiceError] = useState<string | null>(null);

  // Fetch live health status
  const fetchStatus = useCallback(async () => {
    if (!project.id) return;
    try {
      setLoadingStatus(true);
      const res = await fetch(`/api/projects/${project.id}/status`);
      if (res.ok) {
        const data = await res.json();
        setProjectStatus(data);
      }
    } catch (e) {
      console.error('Error fetching project status:', e);
    } finally {
      setLoadingStatus(false);
    }
  }, [project.id]);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 20000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  // Load configured connectors when opening Add Service Modal
  useEffect(() => {
    if (showAddServiceModal) {
      fetch('/api/connectors')
        .then(res => res.json())
        .then(data => {
          const list: ConnectorMeta[] = (data.connectors || []).filter((c: any) => c.configured);
          setConnectors(list);
          if (list.length > 0) {
            setSelectedConnector(list[0].id);
          }
        })
        .catch(console.error);
    }
  }, [showAddServiceModal]);

  // Load resources for selected connector
  useEffect(() => {
    if (showAddServiceModal && selectedConnector) {
      setLoadingResources(true);
      setDiscoveredResources([]);
      setSelectedResourceId('');
      setCustomResourceId('');
      fetch(`/api/connectors/${selectedConnector}/resources`)
        .then(res => res.json())
        .then(data => {
          const resList: DiscoveredResource[] = data.resources || [];
          setDiscoveredResources(resList);
          if (resList.length > 0) {
            setSelectedResourceId(resList[0].id);
            setServiceDisplayName(resList[0].name || resList[0].id);
          } else {
            const meta = connectors.find(c => c.id === selectedConnector);
            setServiceDisplayName(meta?.name || selectedConnector);
          }
        })
        .catch(console.error)
        .finally(() => setLoadingResources(false));
    }
  }, [showAddServiceModal, selectedConnector, connectors]);

  // Copy resource ID helper
  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(text);
    setTimeout(() => setCopiedId(null), 2000);
  };

  // Add Service Submit
  const handleAddService = async () => {
    const resourceId = customResourceId.trim() || selectedResourceId.trim();
    if (!selectedConnector) {
      setAddServiceError('Please select a connector.');
      return;
    }

    setSavingService(true);
    setAddServiceError(null);

    const newService: ServiceItem = {
      connector_id: selectedConnector,
      resource_id: resourceId || undefined,
      display_name: serviceDisplayName.trim() || resourceId || selectedConnector,
    };

    const updatedEnvironments = project.environments.map(env => {
      if (env.name === activeEnv) {
        return {
          ...env,
          services: [...(env.services || []), newService],
        };
      }
      return env;
    });

    const updatedProject: Project = {
      ...project,
      environments: updatedEnvironments,
    };

    try {
      const res = await fetch(`/api/projects/${project.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project: updatedProject }),
      });

      if (!res.ok) {
        const err = await res.json();
        const msg = typeof err.message === 'string' && err.message
          ? err.message
          : (typeof err.detail === 'string' && err.detail ? err.detail : 'Failed to update project');
        throw new Error(msg);
      }

      const data = await res.json();
      onProjectUpdated(data.project || updatedProject);
      setShowAddServiceModal(false);
      setCustomResourceId('');
      setServiceDisplayName('');
      fetchStatus();
    } catch (e: any) {
      setAddServiceError(e.message || 'Error attaching service.');
    } finally {
      setSavingService(false);
    }
  };

  // Remove Service
  const handleRemoveService = async (serviceIndex: number) => {
    if (!confirm('Are you sure you want to remove this service from the environment?')) return;

    const updatedEnvironments = project.environments.map(env => {
      if (env.name === activeEnv) {
        return {
          ...env,
          services: (env.services || []).filter((_, idx) => idx !== serviceIndex),
        };
      }
      return env;
    });

    const updatedProject: Project = {
      ...project,
      environments: updatedEnvironments,
    };

    try {
      const res = await fetch(`/api/projects/${project.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project: updatedProject }),
      });

      if (res.ok) {
        const data = await res.json();
        onProjectUpdated(data.project || updatedProject);
        fetchStatus();
      }
    } catch (e) {
      console.error('Error removing service:', e);
    }
  };

  // Add Environment
  const handleAddEnvironment = async () => {
    const trimmed = newEnvName.trim();
    if (!trimmed) return;
    if (project.environments.some(e => e.name.toLowerCase() === trimmed.toLowerCase())) {
      alert('Environment name already exists.');
      return;
    }

    const updatedEnvironments = [
      ...project.environments,
      { name: trimmed, services: [] },
    ];

    const updatedProject: Project = {
      ...project,
      environments: updatedEnvironments,
    };

    try {
      const res = await fetch(`/api/projects/${project.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project: updatedProject }),
      });

      if (res.ok) {
        const data = await res.json();
        onProjectUpdated(data.project || updatedProject);
        setActiveEnv(trimmed);
        setShowAddEnvModal(false);
        setNewEnvName('');
      }
    } catch (e) {
      console.error('Error adding environment:', e);
    }
  };

  // Remove Environment
  const handleRemoveEnvironment = async (envName: string) => {
    if (project.environments.length <= 1) {
      alert('A project must contain at least one environment.');
      return;
    }
    if (!confirm(`Are you sure you want to remove environment '${envName}'?`)) return;

    const updatedEnvironments = project.environments.filter(e => e.name !== envName);
    const updatedProject: Project = {
      ...project,
      environments: updatedEnvironments,
    };

    try {
      const res = await fetch(`/api/projects/${project.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project: updatedProject }),
      });

      if (res.ok) {
        const data = await res.json();
        onProjectUpdated(data.project || updatedProject);
        setActiveEnv(updatedEnvironments[0].name);
        fetchStatus();
      }
    } catch (e) {
      console.error('Error removing environment:', e);
    }
  };

  // Active environment services
  const currentEnv = project.environments.find(e => e.name === activeEnv) || project.environments[0];
  const services = currentEnv?.services || [];

  // Match live status per service
  const currentEnvStatus = projectStatus?.environments?.find(e => e.name === activeEnv);
  const getServiceStatus = (svc: ServiceItem): ServiceStatusInfo | undefined => {
    return currentEnvStatus?.services?.find(
      s => s.connector_id === svc.connector_id && (s.resource_id === svc.resource_id || !svc.resource_id)
    );
  };

  const getStatusBadge = (status?: string) => {
    switch (status) {
      case 'healthy':
        return (
          <span className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-mono text-[11px]">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            Healthy
          </span>
        );
      case 'warning':
        return (
          <span className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-400 font-mono text-[11px]">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
            Degraded
          </span>
        );
      case 'error':
        return (
          <span className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-rose-500/10 border border-rose-500/20 text-rose-400 font-mono text-[11px]">
            <span className="w-1.5 h-1.5 rounded-full bg-rose-400 animate-ping" />
            Failed
          </span>
        );
      default:
        return (
          <span className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-surface-elevated border border-border-subtle text-gray-400 font-mono text-[11px]">
            <span className="w-1.5 h-1.5 rounded-full bg-gray-500" />
            Pending
          </span>
        );
    }
  };

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      {/* Top Breadcrumb & Actions */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="space-y-1">
          <button
            onClick={onBack}
            className="flex items-center gap-1.5 text-xs font-semibold text-gray-400 hover:text-accent transition-colors mb-2 cursor-pointer"
          >
            <ArrowLeft size={14} /> Back to Projects
          </button>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-accent/15 border border-accent/30 flex items-center justify-center text-accent">
              <Layers size={22} />
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h1 className="text-2xl font-bold tracking-tight text-white">{project.name}</h1>
                {getStatusBadge(projectStatus?.status)}
              </div>
              <div className="flex items-center gap-3 text-xs text-gray-400 mt-0.5">
                <span className="font-mono text-gray-500">ID: {project.id}</span>
                <span>•</span>
                <span>{project.environments.length} Environments</span>
                <span>•</span>
                <span>
                  {project.environments.reduce((acc, env) => acc + (env.services?.length || 0), 0)} Total Services
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={fetchStatus}
            disabled={loadingStatus}
            className="p-2 rounded-xl bg-surface border border-border-subtle hover:border-accent/30 text-gray-300 hover:text-white transition-colors cursor-pointer"
            title="Refresh Live Status"
          >
            <RefreshCw size={15} className={loadingStatus ? 'animate-spin text-accent' : ''} />
          </button>
          <button
            onClick={() => setShowAddServiceModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-accent hover:bg-accent-light text-gray-950 font-bold text-xs rounded-xl transition-all shadow-lg cursor-pointer"
          >
            <Plus size={16} /> Link Service
          </button>
        </div>
      </div>

      {/* Environment Tabs Bar */}
      <div className="border-b border-border-subtle flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 overflow-x-auto pb-[-1px]">
          {project.environments.map(env => {
            const isActive = env.name === activeEnv;
            const envStat = projectStatus?.environments?.find(e => e.name === env.name);
            return (
              <button
                key={env.name}
                onClick={() => {
                  setActiveEnv(env.name);
                  selectEnvironment(env.name);
                }}
                className={`flex items-center gap-2 px-4 py-3 text-xs font-semibold border-b-2 transition-all cursor-pointer ${
                  isActive
                    ? 'border-accent text-accent'
                    : 'border-transparent text-gray-400 hover:text-gray-200 hover:border-border-subtle'
                }`}
              >
                <span>{env.name}</span>
                <span
                  className={`text-[10px] px-2 py-0.5 rounded-full font-mono ${
                    isActive ? 'bg-accent/15 text-accent' : 'bg-surface-elevated text-gray-400'
                  }`}
                >
                  {env.services?.length || 0}
                </span>
                {envStat?.status === 'error' && (
                  <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-ping" />
                )}
              </button>
            );
          })}

          <button
            onClick={() => setShowAddEnvModal(true)}
            className="flex items-center gap-1.5 px-3 py-2 text-xs font-semibold text-gray-400 hover:text-accent transition-colors ml-2 cursor-pointer"
          >
            <Plus size={14} /> New Stage
          </button>
        </div>

        {project.environments.length > 1 && (
          <button
            onClick={() => handleRemoveEnvironment(activeEnv)}
            className="text-[11px] text-gray-500 hover:text-rose-400 transition-colors py-2 cursor-pointer"
          >
            Remove '{activeEnv}' stage
          </button>
        )}
      </div>

      {/* Services Grid for Active Environment */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-base font-bold text-white">
              {activeEnv} Services ({services.length})
            </h2>
            <p className="text-xs text-gray-400">
              Live infrastructure resources connected to the {activeEnv} environment.
            </p>
          </div>
        </div>

        {services.length === 0 ? (
          <div className="glass-panel p-10 rounded-2xl border border-dashed border-border-subtle text-center flex flex-col items-center justify-center">
            <div className="w-12 h-12 rounded-2xl bg-accent/10 border border-accent/20 flex items-center justify-center text-accent mb-3">
              <Server size={22} />
            </div>
            <h3 className="text-sm font-bold text-white mb-1">No Services Linked to {activeEnv}</h3>
            <p className="text-xs text-gray-400 max-w-sm mb-5">
              Connect a live cloud provider (AWS EC2, Kubernetes, GitHub, Vercel) to monitor metrics, alarms, and logs.
            </p>
            <button
              onClick={() => setShowAddServiceModal(true)}
              className="flex items-center gap-2 px-4 py-2 bg-accent hover:bg-accent-light text-gray-950 font-bold text-xs rounded-xl transition-all cursor-pointer shadow-lg"
            >
              <Plus size={15} /> Attach First Service
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {services.map((svc, index) => {
              const statusInfo = getServiceStatus(svc);
              return (
                <motion.div
                  key={`${svc.connector_id}-${svc.resource_id || index}`}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.04 }}
                  className="glass-card rounded-2xl p-5 border border-border-subtle flex flex-col justify-between hover:border-accent/30 transition-all group"
                >
                  <div>
                    {/* Top Row: Icon + Badge + Delete */}
                    <div className="flex items-start justify-between gap-3 mb-3">
                      <div className="flex items-center gap-2.5">
                        <div className="w-9 h-9 rounded-xl bg-surface-elevated border border-border-subtle flex items-center justify-center text-accent font-bold font-mono text-xs uppercase">
                          {svc.connector_id.slice(0, 3)}
                        </div>
                        <div>
                          <h3 className="text-sm font-bold text-white group-hover:text-accent transition-colors">
                            {svc.display_name || svc.connector_id}
                          </h3>
                          <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">
                            {svc.connector_id}
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center gap-1.5">
                        {getStatusBadge(statusInfo?.status)}
                        <button
                          onClick={() => handleRemoveService(index)}
                          className="p-1.5 text-gray-500 hover:text-rose-400 rounded-lg hover:bg-rose-500/10 transition-colors"
                          title="Remove service"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>

                    {/* Resource ID pill */}
                    {svc.resource_id ? (
                      <div className="flex items-center justify-between p-2 rounded-xl bg-background/60 border border-border-subtle/80 mb-3 text-xs">
                        <span className="font-mono text-gray-300 text-[11px] truncate">
                          {svc.resource_id}
                        </span>
                        <button
                          onClick={() => handleCopy(svc.resource_id!)}
                          className="text-gray-400 hover:text-accent transition-colors p-1"
                          title="Copy Resource ID"
                        >
                          {copiedId === svc.resource_id ? (
                            <Check size={12} className="text-accent" />
                          ) : (
                            <Copy size={12} />
                          )}
                        </button>
                      </div>
                    ) : (
                      <div className="p-2 rounded-xl bg-background/40 border border-border-subtle/40 mb-3 text-xs text-gray-500 italic">
                        Account-level connector
                      </div>
                    )}

                    {/* Status detail message if any */}
                    {statusInfo?.detail && (
                      <p className="text-[11px] text-gray-400 mb-4 line-clamp-2">
                        {typeof statusInfo.detail === 'string' ? statusInfo.detail : JSON.stringify(statusInfo.detail)}
                      </p>
                    )}
                  </div>

                  {/* Bottom Action Buttons */}
                  <div className="pt-3 border-t border-border-subtle flex items-center justify-between gap-2">
                    <button
                      onClick={() => {
                        if (onSelectServiceForTelemetry) {
                          onSelectServiceForTelemetry(svc, activeEnv);
                        }
                        selectProject(project.id);
                        selectEnvironment(activeEnv);
                        setActiveTab('dashboard');
                      }}
                      className="flex-1 flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg bg-surface hover:bg-surface-elevated text-[11px] font-semibold text-gray-200 border border-border-subtle transition-colors cursor-pointer"
                    >
                      <Activity size={12} className="text-accent" /> View Telemetry
                    </button>

                    <button
                      onClick={() => {
                        openChat({
                          connectorId: svc.connector_id,
                          resourceId: svc.resource_id,
                        });
                      }}
                      className="flex items-center justify-center gap-1 py-1.5 px-3 rounded-lg bg-accent/15 hover:bg-accent/25 text-[11px] font-bold text-accent border border-accent/30 transition-colors cursor-pointer"
                      title="Investigate with AI"
                    >
                      <Sparkles size={12} /> Copilot
                    </button>
                  </div>
                </motion.div>
              );
            })}
          </div>
        )}
      </div>

      {/* Add Service Modal */}
      {showAddServiceModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 overflow-y-auto">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="glass-panel w-full max-w-md rounded-2xl border border-border-subtle overflow-hidden shadow-2xl p-6 space-y-4"
          >
            <div className="flex items-center justify-between pb-3 border-b border-border-subtle">
              <h3 className="text-base font-bold text-white">
                Attach Service to {activeEnv}
              </h3>
              <button
                onClick={() => setShowAddServiceModal(false)}
                className="text-gray-400 hover:text-white p-1"
              >
                <X size={16} />
              </button>
            </div>

            {addServiceError && (
              <div className="p-2.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
                {addServiceError}
              </div>
            )}

            <div className="space-y-3">
              <div>
                <label className="block text-[11px] font-semibold uppercase tracking-wider text-gray-300 mb-1">
                  Connector Provider
                </label>
                {connectors.length === 0 ? (
                  <div className="text-xs text-amber-400 p-2 bg-amber-500/10 rounded-lg border border-amber-500/20">
                    No configured connectors available.
                  </div>
                ) : (
                  <select
                    value={selectedConnector}
                    onChange={e => setSelectedConnector(e.target.value)}
                    className="w-full bg-surface border border-border-subtle rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-accent"
                  >
                    {connectors.map(c => (
                      <option key={c.id} value={c.id}>
                        {c.name} ({c.category})
                      </option>
                    ))}
                  </select>
                )}
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-[11px] font-semibold uppercase tracking-wider text-gray-300">
                    Resource Identifier
                  </label>
                  {loadingResources && (
                    <span className="text-[10px] text-accent animate-pulse">Scanning...</span>
                  )}
                </div>

                {discoveredResources.length > 0 ? (
                  <select
                    value={selectedResourceId}
                    onChange={e => {
                      setSelectedResourceId(e.target.value);
                      const found = discoveredResources.find(r => r.id === e.target.value);
                      if (found) setServiceDisplayName(found.name || found.id);
                    }}
                    className="w-full bg-surface border border-border-subtle rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-accent mb-2 font-mono"
                  >
                    {discoveredResources.map(r => (
                      <option key={r.id} value={r.id}>
                        {r.name} ({r.id}) — {r.state}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="text"
                    placeholder="e.g. i-0abc12345, default/pod-name"
                    value={customResourceId}
                    onChange={e => {
                      setCustomResourceId(e.target.value);
                      if (!serviceDisplayName) setServiceDisplayName(e.target.value);
                    }}
                    className="w-full bg-surface border border-border-subtle focus:border-accent rounded-xl px-3 py-2 text-xs text-white placeholder-gray-600 focus:outline-none mb-2 font-mono"
                  />
                )}
              </div>

              <div>
                <label className="block text-[11px] font-semibold uppercase tracking-wider text-gray-300 mb-1">
                  Display Name
                </label>
                <input
                  type="text"
                  placeholder="e.g. Primary Production EC2"
                  value={serviceDisplayName}
                  onChange={e => setServiceDisplayName(e.target.value)}
                  className="w-full bg-surface border border-border-subtle focus:border-accent rounded-xl px-3 py-2 text-xs text-white placeholder-gray-600 focus:outline-none"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t border-border-subtle">
              <button
                type="button"
                onClick={() => setShowAddServiceModal(false)}
                className="px-4 py-2 text-xs text-gray-400 hover:text-white"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={savingService || !selectedConnector}
                onClick={handleAddService}
                className="px-5 py-2 bg-accent hover:bg-accent-light text-gray-950 font-bold text-xs rounded-xl transition-all disabled:opacity-50"
              >
                {savingService ? 'Linking...' : 'Link Service'}
              </button>
            </div>
          </motion.div>
        </div>
      )}

      {/* Add Environment Modal */}
      {showAddEnvModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="glass-panel w-full max-w-sm rounded-2xl border border-border-subtle p-6 space-y-4 shadow-2xl"
          >
            <h3 className="text-base font-bold text-white">Add Target Stage</h3>
            <p className="text-xs text-gray-400">
              Create an isolated environment stage for this project (e.g. Development, QA, Canary).
            </p>
            <input
              type="text"
              placeholder="e.g. Development"
              value={newEnvName}
              onChange={e => setNewEnvName(e.target.value)}
              className="w-full bg-surface border border-border-subtle focus:border-accent rounded-xl px-3 py-2.5 text-xs text-white placeholder-gray-600 focus:outline-none"
              autoFocus
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => {
                  setShowAddEnvModal(false);
                  setNewEnvName('');
                }}
                className="px-3.5 py-2 text-xs text-gray-400 hover:text-white"
              >
                Cancel
              </button>
              <button
                onClick={handleAddEnvironment}
                className="px-4 py-2 bg-accent hover:bg-accent-light text-gray-950 font-bold text-xs rounded-xl"
              >
                Add Stage
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </div>
  );
};

export default ProjectDetail;
