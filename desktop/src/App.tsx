import { useState, useEffect } from 'react';
import Dashboard from './components/Dashboard';
import Wizard from './components/Wizard';
import Sidebar from './components/Sidebar';
import Projects from './components/Projects';
import Integrations from './components/Integrations';
import ActivityLog from './components/ActivityLog';
import Notifications from './components/Notifications';
import Settings from './components/Settings';
import NotificationToast from './components/NotificationToast';
import useNotifications from './hooks/useNotifications';

function App() {
  const [isSetupComplete, setIsSetupComplete] = useState<boolean | null>(null);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [loading, setLoading] = useState(true);
  const [projects, setProjects] = useState<any[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<string>('default');
  const [activeEnvironment, setActiveEnvironment] = useState<string>('Production');

  const { toasts, unreadCount, dismissToast } = useNotifications();

  const loadData = async () => {
    try {
      // 1. Check configuration
      const resConfig = await fetch('/api/config');
      if (resConfig.ok) {
        const data = await resConfig.json();
        const hasConfigured = data.services && Object.keys(data.services).length > 0;
        setIsSetupComplete(hasConfigured);
      }

      // 2. Fetch projects
      const resProjects = await fetch('/api/projects');
      if (resProjects.ok) {
        const pData = await resProjects.json();
        const list = pData.projects || [];
        setProjects(list);
        if (list.length > 0 && !list.find((p: any) => p.id === activeProjectId)) {
          setActiveProjectId(list[0].id);
        }
      }
    } catch (e) {
      console.error('Error loading app initial state:', e);
      setIsSetupComplete(false);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const activeProject = projects.find(p => p.id === activeProjectId) || projects[0];
  const activeEnvObj = activeProject?.environments?.find(
    (e: any) => e.name.toLowerCase() === activeEnvironment.toLowerCase()
  ) || activeProject?.environments?.[0];
  const activeServices = activeEnvObj?.services || [];

  const handleSetupComplete = () => {
    setIsSetupComplete(true);
    loadData();
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center text-white space-y-3">
        <div className="w-8 h-8 rounded-full border-2 border-accent border-t-transparent animate-spin" />
        <span className="text-xs font-mono text-gray-400">Initializing Lear Intelligence Engine...</span>
      </div>
    );
  }

  return (
    <>
      {!isSetupComplete ? (
        <Wizard onComplete={handleSetupComplete} />
      ) : (
        <div className="flex h-screen w-full relative z-10 overflow-hidden bg-background">
          <Sidebar
            activeTab={activeTab}
            setActiveTab={setActiveTab}
            activeProject={activeProject}
            projects={projects}
            onSelectProject={(p) => setActiveProjectId(p.id)}
            activeEnvironment={activeEnvironment}
            setActiveEnvironment={setActiveEnvironment}
            services={activeServices}
            unreadNotificationsCount={unreadCount}
          />

          <main className="flex-1 overflow-y-auto">
            {activeTab === 'dashboard' && (
              <Dashboard
                activeProject={activeProject}
                activeEnvironment={activeEnvironment}
                onOpenWizard={() => setIsSetupComplete(false)}
              />
            )}
            {activeTab === 'projects' && <Projects />}
            {activeTab === 'integrations' && (
              <Integrations onConfigureConnector={() => setIsSetupComplete(false)} />
            )}
            {activeTab === 'activity' && <ActivityLog />}
            {activeTab === 'notifications' && <Notifications />}
            {activeTab === 'settings' && (
              <Settings onReconfigure={() => setIsSetupComplete(false)} />
            )}
          </main>

          {/* Global Slide-In Alerts / Toasts */}
          <NotificationToast toasts={toasts} onDismiss={dismissToast} />
        </div>
      )}
    </>
  );
}

export default App;
