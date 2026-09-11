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
import Chatbot from './components/Chatbot';
import { LearProvider, useLear } from './context/LearContext';

function AppContent() {
  const [isSetupComplete, setIsSetupComplete] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);

  const {
    activeTab,
    activeProject,
    activeEnvironment,
    refreshProjects,
    toasts,
    dismissToast,
    chatOpen,
    closeChat,
    chatContext,
  } = useLear();

  const checkConfig = async () => {
    try {
      const resConfig = await fetch('/api/config');
      if (resConfig.ok) {
        const data = await resConfig.json();
        const hasConfigured = data.services && Object.keys(data.services).length > 0;
        setIsSetupComplete(hasConfigured);
      }
    } catch (e) {
      console.error('Error checking setup status:', e);
      setIsSetupComplete(false);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    checkConfig();
  }, []);

  const handleSetupComplete = () => {
    setIsSetupComplete(true);
    checkConfig();
    refreshProjects();
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
          <Sidebar />

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

          {/* Global Lear Copilot Chatbot */}
          <Chatbot
            isOpen={chatOpen}
            onClose={closeChat}
            serviceContext={chatContext}
          />
        </div>
      )}
    </>
  );
}

function App() {
  return (
    <LearProvider>
      <AppContent />
    </LearProvider>
  );
}

export default App;
