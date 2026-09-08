import { useState, useEffect } from 'react';
import { FolderGit2, Plus, Trash2, Layers } from 'lucide-react';

interface ServiceItem {
  connector_id: string;
  resource_id?: string;
  display_name?: string;
}

interface Environment {
  name: string;
  services: ServiceItem[];
}

interface Project {
  id: string;
  name: string;
  created_at?: string;
  environments: Environment[];
}

export default function Projects() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [showModal, setShowModal] = useState(false);

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
      }
    } catch (e) {
      console.error('Error auto-importing:', e);
    } finally {
      setImporting(false);
    }
  };

  const handleCreateProject = async () => {
    if (!newProjectName.trim()) return;
    const projId = newProjectName.toLowerCase().replace(/\s+/g, '-');
    const newProj: Project = {
      id: projId,
      name: newProjectName.trim(),
      environments: [
        {
          name: 'Production',
          services: [{ connector_id: 'aws', resource_id: 'i-0abc123', display_name: 'Primary EC2' }],
        },
        {
          name: 'Staging',
          services: [{ connector_id: 'aws', resource_id: 'i-0staging', display_name: 'Staging Instance' }],
        },
      ],
    };

    try {
      const res = await fetch('/api/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project: newProj }),
      });
      if (res.ok) {
        setNewProjectName('');
        setShowModal(false);
        fetchProjects();
      }
    } catch (e) {
      console.error('Error creating project:', e);
    }
  };

  const handleDeleteProject = async (id: string) => {
    try {
      const res = await fetch(`/api/projects/${id}`, { method: 'DELETE' });
      if (res.ok) {
        setProjects(prev => prev.filter(p => p.id !== id));
      }
    } catch (e) {
      console.error('Error deleting project:', e);
    }
  };

  return (
    <div className="p-8 max-w-7xl mx-auto">
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
            onClick={() => setShowModal(true)}
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
            Lear can monitor multiple environments like Vercel. Auto-import detected services from your configuration or create a new stack.
          </p>
          <button
            onClick={handleAutoImport}
            disabled={importing}
            className="px-5 py-2.5 bg-accent hover:bg-accent-light text-gray-950 font-bold text-xs rounded-xl transition-all cursor-pointer"
          >
            Auto-Detect Services
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6">
          {projects.map(proj => (
            <div key={proj.id} className="glass-card rounded-2xl p-6">
              <div className="flex items-center justify-between pb-4 border-b border-border-subtle">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 rounded-xl bg-accent/15 border border-accent/20 text-accent">
                    <Layers size={20} />
                  </div>
                  <div>
                    <h2 className="text-lg font-bold text-white">{proj.name}</h2>
                    <span className="text-[11px] font-mono text-gray-400">ID: {proj.id}</span>
                  </div>
                </div>
                <button
                  onClick={() => handleDeleteProject(proj.id)}
                  className="p-2 rounded-lg text-gray-500 hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
                  title="Delete project"
                >
                  <Trash2 size={16} />
                </button>
              </div>

              {/* Environments list */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-5">
                {(proj.environments || []).map((env, i) => (
                  <div key={i} className="p-4 rounded-xl bg-surface/50 border border-border-subtle">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-xs font-bold text-gray-200">{env.name}</span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-accent/10 text-accent font-mono">
                        {env.services?.length || 0} services
                      </span>
                    </div>

                    <div className="space-y-1.5">
                      {(env.services || []).map((svc, idx) => (
                        <div
                          key={idx}
                          className="flex items-center justify-between text-xs p-2 rounded-lg bg-background/60 border border-border-subtle"
                        >
                          <div className="flex items-center gap-2">
                            <span className="w-1.5 h-1.5 rounded-full bg-accent" />
                            <span className="font-medium text-gray-300">
                              {svc.display_name || svc.connector_id}
                            </span>
                          </div>
                          {svc.resource_id && (
                            <span className="text-[10px] text-gray-500 font-mono">{svc.resource_id}</span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* New Project Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="glass-panel w-full max-w-md rounded-2xl p-6 border border-border-subtle">
            <h2 className="text-lg font-bold text-white mb-1">Create New Project</h2>
            <p className="text-xs text-gray-400 mb-4">
              Enter a project name to create a new multi-environment stack.
            </p>
            <input
              type="text"
              placeholder="e.g. My SaaS Stack"
              value={newProjectName}
              onChange={e => setNewProjectName(e.target.value)}
              className="w-full bg-surface border border-border-subtle focus:border-accent rounded-xl px-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none mb-5 font-sans"
              autoFocus
            />
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setShowModal(false)}
                className="px-4 py-2 text-xs font-semibold text-gray-400 hover:text-white"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateProject}
                className="px-5 py-2 bg-accent hover:bg-accent-light text-gray-950 font-bold text-xs rounded-xl"
              >
                Create Project
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
