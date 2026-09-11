import React, { useState, useEffect } from 'react';
import { FolderGit2, Plus, Trash2, Layers, ArrowRight } from 'lucide-react';
import { useLear, Project } from '../context/LearContext';
import ProjectDetail from './ProjectDetail';
import ProjectCreate from './ProjectCreate';

export default function Projects() {
  const context = useLear();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);

  // Sync with context's selectedProjectIdForDetail
  useEffect(() => {
    if (context.selectedProjectIdForDetail) {
      setSelectedProjectId(context.selectedProjectIdForDetail);
    }
  }, [context.selectedProjectIdForDetail]);

  // Sync with LearContext openCreateProjectModal
  useEffect(() => {
    if (context.openCreateProjectModal) {
      setShowCreateModal(true);
      context.setOpenCreateProjectModal(false);
    }
  }, [context.openCreateProjectModal]);

  const fetchProjects = async () => {
    try {
      const res = await fetch('/api/projects');
      if (res.ok) {
        const data = await res.json();
        setProjects(data.projects || []);
      }
    } catch (e) {
      console.error('Error fetching projects:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProjects();
  }, []);

  const handleAutoImport = async () => {
    setImporting(true);
    try {
      const res = await fetch('/api/projects/auto-import', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setProjects(data.projects || []);
        context.refreshProjects();
      }
    } catch (e) {
      console.error('Error auto-importing:', e);
    } finally {
      setImporting(false);
    }
  };

  const handleDeleteProject = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (!confirm(`Are you sure you want to delete project '${id}'?`)) return;
    try {
      const res = await fetch(`/api/projects/${id}`, { method: 'DELETE' });
      if (res.ok) {
        setProjects(prev => prev.filter(p => p.id !== id));
        if (selectedProjectId === id) {
          setSelectedProjectId(null);
          context.clearProjectDetail();
        }
        context.refreshProjects();
      }
    } catch (e) {
      console.error('Error deleting project:', e);
    }
  };

  // If a project is selected for detail view, render ProjectDetail
  const activeDetailProject = projects.find(
    p => p.id === (selectedProjectId || context.selectedProjectIdForDetail)
  );

  if (activeDetailProject) {
    return (
      <ProjectDetail
        project={activeDetailProject}
        onBack={() => {
          setSelectedProjectId(null);
          context.clearProjectDetail();
        }}
        onProjectUpdated={updated => {
          setProjects(prev => prev.map(p => (p.id === updated.id ? updated : p)));
          context.refreshProjects();
        }}
      />
    );
  }

  return (
    <div className="p-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-wrap justify-between items-center gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white mb-1">Projects & Stacks</h1>
          <p className="text-sm text-gray-400">
            Organize multi-environment infrastructure stacks monitored by Lear.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleAutoImport}
            disabled={importing}
            className="px-4 py-2 bg-surface hover:bg-surface-elevated border border-border-subtle hover:border-accent/30 text-xs font-semibold rounded-xl text-gray-200 transition-all cursor-pointer"
          >
            {importing ? 'Scanning .env...' : 'Auto-Import from .env'}
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-accent hover:bg-accent-light text-gray-950 font-bold text-xs rounded-xl transition-all shadow-lg cursor-pointer"
          >
            <Plus size={16} /> New Project
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-20">
          <div className="w-8 h-8 rounded-full border-2 border-accent border-t-transparent animate-spin" />
        </div>
      ) : projects.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center border border-dashed border-border-subtle rounded-2xl glass-panel">
          <div className="w-14 h-14 rounded-2xl bg-accent/10 border border-accent/20 flex items-center justify-center mb-4 text-accent">
            <FolderGit2 size={26} />
          </div>
          <h3 className="text-lg font-bold text-white mb-1">No Projects Found</h3>
          <p className="text-xs text-gray-400 max-w-md mb-6">
            Lear organizes infrastructure into multi-environment stacks. Auto-import detected services from your configuration or create a new custom stack.
          </p>
          <div className="flex gap-3">
            <button
              onClick={handleAutoImport}
              disabled={importing}
              className="px-5 py-2.5 bg-surface hover:bg-surface-elevated border border-border-subtle text-white font-semibold text-xs rounded-xl transition-all cursor-pointer"
            >
              {importing ? 'Scanning...' : 'Auto-Detect Services'}
            </button>
            <button
              onClick={() => setShowCreateModal(true)}
              className="px-5 py-2.5 bg-accent hover:bg-accent-light text-gray-950 font-bold text-xs rounded-xl transition-all cursor-pointer shadow-lg"
            >
              Create New Project
            </button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6">
          {projects.map(proj => {
            const totalServices = (proj.environments || []).reduce(
              (acc, e) => acc + (e.services?.length || 0),
              0
            );

            return (
              <div
                key={proj.id}
                onClick={() => setSelectedProjectId(proj.id)}
                className="glass-card rounded-2xl p-6 hover:border-accent/30 transition-all cursor-pointer group"
              >
                {/* Project Header Row */}
                <div className="flex items-center justify-between pb-4 border-b border-border-subtle">
                  <div className="flex items-center gap-3.5">
                    <div className="p-3 rounded-xl bg-accent/15 border border-accent/20 text-accent group-hover:scale-105 transition-transform">
                      <Layers size={22} />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h2 className="text-lg font-bold text-white group-hover:text-accent transition-colors">
                          {proj.name}
                        </h2>
                        <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-surface-elevated text-gray-400 border border-border-subtle">
                          {proj.id}
                        </span>
                      </div>
                      <span className="text-xs text-gray-400">
                        {proj.environments?.length || 0} stages • {totalServices} linked resources
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    <button
                      onClick={e => handleDeleteProject(e, proj.id)}
                      className="p-2 rounded-lg text-gray-500 hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
                      title="Delete project"
                    >
                      <Trash2 size={16} />
                    </button>
                    <button
                      onClick={() => setSelectedProjectId(proj.id)}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-surface group-hover:bg-accent group-hover:text-gray-950 text-gray-300 font-bold text-xs border border-border-subtle transition-all shadow"
                    >
                      <span>View Stack</span>
                      <ArrowRight size={14} />
                    </button>
                  </div>
                </div>

                {/* Environments Grid Preview */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-5">
                  {(proj.environments || []).map((env, i) => (
                    <div key={i} className="p-4 rounded-xl bg-surface/50 border border-border-subtle/80">
                      <div className="flex items-center justify-between mb-2.5">
                        <span className="text-xs font-bold text-gray-200">{env.name}</span>
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-accent/10 text-accent font-mono">
                          {env.services?.length || 0} services
                        </span>
                      </div>

                      <div className="space-y-1.5">
                        {(env.services || []).length === 0 ? (
                          <div className="py-2.5 text-center text-[11px] text-gray-500 font-mono">
                            No services linked
                          </div>
                        ) : (
                          (env.services || []).slice(0, 3).map((svc, idx) => (
                            <div
                              key={idx}
                              className="flex items-center justify-between text-xs p-2 rounded-lg bg-background/60 border border-border-subtle/60"
                            >
                              <div className="flex items-center gap-2">
                                <span className="w-1.5 h-1.5 rounded-full bg-accent" />
                                <span className="font-medium text-gray-300 truncate max-w-[140px]">
                                  {svc.display_name || svc.connector_id}
                                </span>
                              </div>
                              {svc.resource_id && (
                                <span className="text-[10px] text-gray-500 font-mono truncate max-w-[90px]">
                                  {svc.resource_id}
                                </span>
                              )}
                            </div>
                          ))
                        )}
                        {(env.services || []).length > 3 && (
                          <div className="text-[10px] text-gray-500 font-mono text-center pt-1">
                            +{(env.services || []).length - 3} more services
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Multi-step Project Creation Modal */}
      <ProjectCreate
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onSuccess={newProject => {
          setProjects(prev => [...prev, newProject]);
          context.refreshProjects();
          setSelectedProjectId(newProject.id);
        }}
      />
    </div>
  );
}
