import { useState, useEffect } from 'react';

export default function Projects() {
  const [projects, setProjects] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch('http://localhost:8000/api/config')
      .then(r => r.json())
      .then(d => {
        if (d.projects) setProjects(d.projects);
      })
      .catch(console.error);
  }, []);

  const handleAutoImport = async () => {
    setLoading(true);
    try {
      const res = await fetch('http://localhost:8000/api/projects/auto-import', { method: 'POST' });
      const data = await res.json();
      if (data.projects) {
        setProjects(data.projects);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-8">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white mb-2">Projects</h1>
          <p className="text-gray-400">Manage environments and connected infrastructure for each project.</p>
        </div>
        <button className="px-4 py-2 bg-accent text-background font-semibold rounded-lg hover:bg-[#2da36c] transition-colors">
          New Project
        </button>
      </div>

      {projects.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center border-2 border-dashed border-gray-800 rounded-2xl bg-gray-900/20">
          <div className="w-16 h-16 rounded-full bg-accent/10 flex items-center justify-center mb-4">
            <span className="text-2xl text-accent">📁</span>
          </div>
          <h3 className="text-xl font-medium text-white mb-2">No projects created yet</h3>
          <p className="text-gray-400 max-w-md">
            Prash can monitor multiple projects automatically. Create a project to assign specific AWS or GitHub credentials.
          </p>
          <button 
            onClick={handleAutoImport}
            disabled={loading}
            className="mt-6 px-6 py-3 border border-gray-700 hover:border-gray-500 rounded-lg text-white font-medium transition-colors disabled:opacity-50"
          >
            {loading ? 'Importing...' : 'Auto-import from .env'}
          </button>
        </div>
      ) : (
        <div className="space-y-6">
          {projects.map((proj) => (
            <div key={proj.id} className="p-6 rounded-2xl border border-gray-800 bg-gray-900/30">
              <h2 className="text-2xl font-semibold text-white mb-4">{proj.name}</h2>
              <div className="flex gap-2 flex-wrap">
                {proj.services.map((svc: string) => (
                  <span key={svc} className="px-3 py-1 bg-gray-800 text-gray-300 rounded-full text-sm font-medium">
                    {svc}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
