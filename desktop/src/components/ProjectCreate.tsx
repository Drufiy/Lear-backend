import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { X, ArrowRight, ArrowLeft, Layers, Trash2 } from 'lucide-react';
import { Project, Environment, ServiceItem } from '../context/LearContext';

interface ProjectCreateProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (project: Project) => void;
}

interface ConnectorItem {
  id: string;
  name: string;
  category: string;
  configured: boolean;
  color?: string;
}

interface DiscoveredResource {
  id: string;
  name: string;
  type: string;
  state: string;
}

export const ProjectCreate: React.FC<ProjectCreateProps> = ({ isOpen, onClose, onSuccess }) => {
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);

  // Step 1: Identity
  const [projectName, setProjectName] = useState('');
  const [projectId, setProjectId] = useState('');
  const [isCustomId, setIsCustomId] = useState(false);

  // Step 2: Environments
  const [selectedEnvs, setSelectedEnvs] = useState<string[]>(['Production', 'Staging']);
  const [customEnvInput, setCustomEnvInput] = useState('');

  // Step 3: Services attachment
  const [connectors, setConnectors] = useState<ConnectorItem[]>([]);
  const [services, setServices] = useState<Array<{ env: string; service: ServiceItem }>>([]);

  // Active service builder state
  const [selectedConnector, setSelectedConnector] = useState<string>('');
  const [discoveredResources, setDiscoveredResources] = useState<DiscoveredResource[]>([]);
  const [loadingResources, setLoadingResources] = useState(false);
  const [selectedResourceId, setSelectedResourceId] = useState<string>('');
  const [customResourceId, setCustomResourceId] = useState<string>('');
  const [serviceDisplayName, setServiceDisplayName] = useState<string>('');
  const [targetEnv, setTargetEnv] = useState<string>('Production');

  // Submitting
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Auto-slugify
  useEffect(() => {
    if (!isCustomId) {
      setProjectId(projectName.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''));
    }
  }, [projectName, isCustomId]);

  // Fetch configured connectors on mount
  useEffect(() => {
    if (isOpen) {
      fetch('/api/connectors')
        .then(res => res.json())
        .then(data => {
          const list: ConnectorItem[] = (data.connectors || []).filter((c: any) => c.configured);
          setConnectors(list);
          if (list.length > 0) {
            setSelectedConnector(list[0].id);
          }
        })
        .catch(console.error);
    }
  }, [isOpen]);

  // Fetch resources when connector changes
  useEffect(() => {
    if (selectedConnector) {
      setLoadingResources(true);
      setDiscoveredResources([]);
      setSelectedResourceId('');
      setCustomResourceId('');
      fetch(`/api/connectors/${selectedConnector}/resources`)
        .then(res => res.json())
        .then(data => {
          setDiscoveredResources(data.resources || []);
          if (data.resources && data.resources.length > 0) {
            setSelectedResourceId(data.resources[0].id);
            setServiceDisplayName(data.resources[0].name || data.resources[0].id);
          } else {
            setServiceDisplayName(connectors.find(c => c.id === selectedConnector)?.name || selectedConnector);
          }
        })
        .catch(console.error)
        .finally(() => setLoadingResources(false));
    }
  }, [selectedConnector, connectors]);

  const handleAddCustomEnv = () => {
    const trimmed = customEnvInput.trim();
    if (trimmed && !selectedEnvs.includes(trimmed)) {
      setSelectedEnvs(prev => [...prev, trimmed]);
      setCustomEnvInput('');
    }
  };

  const handleRemoveEnv = (envName: string) => {
    if (selectedEnvs.length <= 1) return; // Keep at least one environment
    setSelectedEnvs(prev => prev.filter(e => e !== envName));
    setServices(prev => prev.filter(s => s.env !== envName));
  };

  const handleAddServiceToProject = () => {
    const resourceId = customResourceId.trim() || selectedResourceId.trim();
    if (!selectedConnector) return;

    const newSvc: ServiceItem = {
      connector_id: selectedConnector,
      resource_id: resourceId || undefined,
      display_name: serviceDisplayName.trim() || resourceId || selectedConnector,
    };

    setServices(prev => [...prev, { env: targetEnv, service: newSvc }]);
    setCustomResourceId('');
    setServiceDisplayName('');
  };

  const handleRemoveServiceFromList = (index: number) => {
    setServices(prev => prev.filter((_, i) => i !== index));
  };

  const handleFinalSubmit = async () => {
    if (!projectId || !projectName.trim()) {
      setError('Project name and ID are required.');
      return;
    }

    setSubmitting(true);
    setError(null);

    const environmentsList: Environment[] = selectedEnvs.map(envName => ({
      name: envName,
      services: services.filter(s => s.env === envName).map(s => s.service),
    }));

    const newProject: Project = {
      id: projectId,
      name: projectName.trim(),
      created_at: new Date().toISOString(),
      environments: environmentsList,
    };

    try {
      const res = await fetch('/api/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project: newProject }),
      });

      if (!res.ok) {
        const errData = await res.json();
        const msg = typeof errData.message === 'string' && errData.message
          ? errData.message
          : (typeof errData.detail === 'string' && errData.detail ? errData.detail : 'Failed to create project');
        throw new Error(msg);
      }

      const data = await res.json();
      onSuccess(data.project || newProject);
      handleResetAndClose();
    } catch (e: any) {
      setError(e.message || 'Error creating project stack.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleResetAndClose = () => {
    setStep(1);
    setProjectName('');
    setProjectId('');
    setIsCustomId(false);
    setSelectedEnvs(['Production', 'Staging']);
    setServices([]);
    setError(null);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 overflow-y-auto">
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        className="glass-panel w-full max-w-2xl rounded-2xl border border-border-subtle overflow-hidden shadow-2xl my-8"
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-border-subtle bg-surface/40">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-accent/15 border border-accent/30 flex items-center justify-center text-accent">
              <Layers size={20} />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white">Create Infrastructure Project</h2>
              <p className="text-xs text-gray-400">Step {step} of 4 — {
                step === 1 ? 'Project Identity' :
                step === 2 ? 'Target Environments' :
                step === 3 ? 'Attach Services (Optional)' :
                'Review & Confirm'
              }</p>
            </div>
          </div>
          <button
            onClick={handleResetAndClose}
            className="p-2 text-gray-400 hover:text-white rounded-lg hover:bg-surface-elevated transition-colors cursor-pointer"
          >
            <X size={18} />
          </button>
        </div>

        {/* Progress Bar */}
        <div className="w-full bg-surface-elevated h-1">
          <div
            className="bg-accent h-1 transition-all duration-300"
            style={{ width: `${(step / 4) * 100}%` }}
          />
        </div>

        {/* Error message */}
        {error && (
          <div className="mx-6 mt-4 p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center justify-between">
            <span>{error}</span>
            <button onClick={() => setError(null)} className="text-rose-400 hover:text-white">
              <X size={14} />
            </button>
          </div>
        )}

        {/* Body Content */}
        <div className="p-6">
          {/* STEP 1: IDENTITY */}
          {step === 1 && (
            <div className="space-y-5">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-gray-300 mb-2">
                  Project / Stack Name
                </label>
                <input
                  type="text"
                  placeholder="e.g. Core Banking Platform, E-Commerce API"
                  value={projectName}
                  onChange={e => setProjectName(e.target.value)}
                  className="w-full bg-surface border border-border-subtle focus:border-accent rounded-xl px-4 py-3 text-sm text-white placeholder-gray-600 focus:outline-none transition-colors"
                  autoFocus
                />
                <p className="text-[11px] text-gray-500 mt-1.5">
                  A high-level group for multi-environment services monitored by Lear.
                </p>
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-semibold uppercase tracking-wider text-gray-300">
                    Project Slug ID
                  </label>
                  <button
                    type="button"
                    onClick={() => setIsCustomId(!isCustomId)}
                    className="text-[11px] text-accent hover:underline font-mono cursor-pointer"
                  >
                    {isCustomId ? 'Auto-generate from name' : 'Customize slug'}
                  </button>
                </div>
                <input
                  type="text"
                  placeholder="e.g. core-banking-platform"
                  value={projectId}
                  onChange={e => {
                    setIsCustomId(true);
                    setProjectId(e.target.value.toLowerCase().replace(/[^a-z0-9-_]/g, ''));
                  }}
                  readOnly={!isCustomId}
                  className={`w-full bg-surface border border-border-subtle rounded-xl px-4 py-2.5 text-xs font-mono text-gray-300 placeholder-gray-600 focus:outline-none ${
                    isCustomId ? 'focus:border-accent text-white' : 'opacity-75 cursor-not-allowed'
                  }`}
                />
              </div>
            </div>
          )}

          {/* STEP 2: ENVIRONMENTS */}
          {step === 2 && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-bold text-white mb-1">Define Environments</h3>
                <p className="text-xs text-gray-400 mb-4">
                  Choose the isolated stages your stack operates across (e.g. Production, Staging, QA).
                </p>

                <div className="flex flex-wrap gap-2.5 mb-4">
                  {selectedEnvs.map(env => (
                    <div
                      key={env}
                      className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-surface border border-accent/30 text-white text-xs font-medium"
                    >
                      <span className="w-2 h-2 rounded-full bg-accent" />
                      <span>{env}</span>
                      {selectedEnvs.length > 1 && (
                        <button
                          type="button"
                          onClick={() => handleRemoveEnv(env)}
                          className="text-gray-400 hover:text-rose-400 ml-1 p-0.5 cursor-pointer"
                        >
                          <X size={12} />
                        </button>
                      )}
                    </div>
                  ))}
                </div>

                <div className="flex gap-2">
                  <input
                    type="text"
                    placeholder="Add environment (e.g. Development, Sandbox)"
                    value={customEnvInput}
                    onChange={e => setCustomEnvInput(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        handleAddCustomEnv();
                      }
                    }}
                    className="flex-1 bg-surface border border-border-subtle focus:border-accent rounded-xl px-4 py-2 text-xs text-white placeholder-gray-600 focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={handleAddCustomEnv}
                    className="px-4 py-2 bg-surface-elevated hover:bg-surface border border-border-subtle text-xs font-semibold text-white rounded-xl transition-colors cursor-pointer"
                  >
                    Add
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* STEP 3: SERVICES ATTACHMENT */}
          {step === 3 && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-bold text-white mb-1">Attach Services</h3>
                <p className="text-xs text-gray-400 mb-4">
                  Link live connectors to environments. You can also attach or modify services later.
                </p>

                {connectors.length === 0 ? (
                  <div className="p-4 rounded-xl bg-surface/60 border border-border-subtle text-center text-xs text-gray-400">
                    No configured connectors detected. You can create the project now and connect services later.
                  </div>
                ) : (
                  <div className="p-4 rounded-xl bg-surface/50 border border-border-subtle space-y-4">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label className="block text-[11px] font-semibold text-gray-300 uppercase tracking-wider mb-1.5">
                          Connector Provider
                        </label>
                        <select
                          value={selectedConnector}
                          onChange={e => setSelectedConnector(e.target.value)}
                          className="w-full bg-background border border-border-subtle rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-accent cursor-pointer"
                        >
                          {connectors.map(c => (
                            <option key={c.id} value={c.id}>
                              {c.name} ({c.category})
                            </option>
                          ))}
                        </select>
                      </div>

                      <div>
                        <label className="block text-[11px] font-semibold text-gray-300 uppercase tracking-wider mb-1.5">
                          Target Environment
                        </label>
                        <select
                          value={targetEnv}
                          onChange={e => setTargetEnv(e.target.value)}
                          className="w-full bg-background border border-border-subtle rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-accent cursor-pointer"
                        >
                          {selectedEnvs.map(env => (
                            <option key={env} value={env}>
                              {env}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>

                    {/* Discovered resources dropdown or manual entry */}
                    <div>
                      <div className="flex items-center justify-between mb-1.5">
                        <label className="text-[11px] font-semibold text-gray-300 uppercase tracking-wider">
                          Resource Identifier
                        </label>
                        {loadingResources && (
                          <span className="text-[10px] text-accent animate-pulse">
                            Scanning real resources...
                          </span>
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
                          className="w-full bg-background border border-border-subtle rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-accent mb-2 font-mono cursor-pointer"
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
                          placeholder="Resource ID / Pod / Instance / Repo"
                          value={customResourceId}
                          onChange={e => {
                            setCustomResourceId(e.target.value);
                            if (!serviceDisplayName) setServiceDisplayName(e.target.value);
                          }}
                          className="w-full bg-background border border-border-subtle focus:border-accent rounded-xl px-3 py-2 text-xs text-white placeholder-gray-600 focus:outline-none mb-2 font-mono"
                        />
                      )}

                      <div className="flex gap-2">
                        <input
                          type="text"
                          placeholder="Display Name (optional)"
                          value={serviceDisplayName}
                          onChange={e => setServiceDisplayName(e.target.value)}
                          className="flex-1 bg-background border border-border-subtle focus:border-accent rounded-xl px-3 py-2 text-xs text-white placeholder-gray-600 focus:outline-none"
                        />
                        <button
                          type="button"
                          onClick={handleAddServiceToProject}
                          className="px-4 py-2 bg-accent hover:bg-accent-light text-gray-950 font-bold text-xs rounded-xl transition-all cursor-pointer shadow"
                        >
                          Attach to {targetEnv}
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {/* Attached Services List */}
                {services.length > 0 && (
                  <div className="mt-4 space-y-2">
                    <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider">
                      Attached Services ({services.length})
                    </span>
                    <div className="max-h-40 overflow-y-auto space-y-1.5 pr-1">
                      {services.map((item, idx) => (
                        <div
                          key={idx}
                          className="flex items-center justify-between p-2.5 rounded-xl bg-surface border border-border-subtle text-xs"
                        >
                          <div className="flex items-center gap-2">
                            <span className="px-2 py-0.5 rounded bg-surface-elevated text-[10px] text-accent font-mono">
                              {item.env}
                            </span>
                            <span className="font-semibold text-white">
                              {item.service.display_name || item.service.connector_id}
                            </span>
                            {item.service.resource_id && (
                              <span className="text-[11px] font-mono text-gray-500">
                                ({item.service.resource_id})
                              </span>
                            )}
                          </div>
                          <button
                            type="button"
                            onClick={() => handleRemoveServiceFromList(idx)}
                            className="text-gray-500 hover:text-rose-400 p-1 cursor-pointer"
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* STEP 4: REVIEW & CONFIRM */}
          {step === 4 && (
            <div className="space-y-4">
              <div className="p-4 rounded-xl bg-surface/50 border border-border-subtle space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-base font-bold text-white">{projectName}</h3>
                    <span className="text-xs font-mono text-gray-400">ID: {projectId}</span>
                  </div>
                  <span className="px-2.5 py-1 rounded-full bg-accent/15 border border-accent/30 text-accent font-mono text-[11px]">
                    {selectedEnvs.length} Environments
                  </span>
                </div>

                <div className="border-t border-border-subtle pt-3 space-y-2">
                  {selectedEnvs.map(env => {
                    const envServices = services.filter(s => s.env === env);
                    return (
                      <div key={env} className="p-2.5 rounded-lg bg-background/60 border border-border-subtle/60 text-xs">
                        <div className="flex items-center justify-between font-semibold text-gray-200 mb-1">
                          <span>{env}</span>
                          <span className="text-[10px] font-mono text-gray-400">{envServices.length} linked services</span>
                        </div>
                        {envServices.length === 0 ? (
                          <span className="text-[11px] text-gray-500 italic">No services linked</span>
                        ) : (
                          <div className="flex flex-wrap gap-1 mt-1">
                            {envServices.map((s, i) => (
                              <span key={i} className="px-2 py-0.5 rounded bg-surface text-[10px] text-gray-300 font-mono">
                                {s.service.display_name}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-between p-6 border-t border-border-subtle bg-surface/40">
          {step > 1 ? (
            <button
              type="button"
              onClick={() => setStep((step - 1) as any)}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-surface hover:bg-surface-elevated text-gray-300 font-semibold text-xs transition-colors cursor-pointer"
            >
              <ArrowLeft size={14} /> Back
            </button>
          ) : (
            <div />
          )}

          {step < 4 ? (
            <button
              type="button"
              disabled={step === 1 && !projectName.trim()}
              onClick={() => setStep((step + 1) as any)}
              className="flex items-center gap-1.5 px-5 py-2.5 rounded-xl bg-accent hover:bg-accent-light text-gray-950 font-bold text-xs transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed shadow-lg"
            >
              Next Step <ArrowRight size={14} />
            </button>
          ) : (
            <button
              type="button"
              disabled={submitting}
              onClick={handleFinalSubmit}
              className="flex items-center gap-1.5 px-6 py-2.5 rounded-xl bg-accent hover:bg-accent-light text-gray-950 font-bold text-xs transition-all cursor-pointer disabled:opacity-50 shadow-lg"
            >
              {submitting ? 'Creating Stack...' : 'Confirm & Create Project'}
            </button>
          )}
        </div>
      </motion.div>
    </div>
  );
};

export default ProjectCreate;
