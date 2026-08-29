import { useState, useEffect } from 'react';
import Dashboard from './components/Dashboard';
import Wizard from './components/Wizard';
import Sidebar from './components/Sidebar';
import Projects from './components/Projects';
import Integrations from './components/Integrations';
import Notifications from './components/Notifications';
import Settings from './components/Settings';

function App() {
  const [isSetupComplete, setIsSetupComplete] = useState<boolean | null>(null);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/config')
      .then(res => res.json())
      .then(data => {
        if (data.services && Object.keys(data.services).length > 0) {
          setIsSetupComplete(true);
        }
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const handleSetupComplete = (config: any) => {
    console.log("Setup complete with config:", config);
    setIsSetupComplete(true);
  };

  if (loading) {
    return <div className="min-h-screen bg-background flex items-center justify-center text-white">Loading...</div>;
  }

  return (
    <>
      {!isSetupComplete ? (
        <Wizard onComplete={handleSetupComplete} />
      ) : (
        <div className="flex h-screen w-full relative z-10 overflow-hidden">
          <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />
          
          <div className="flex-1 overflow-y-auto">
            {activeTab === 'dashboard' && <Dashboard />}
            {activeTab === 'projects' && <Projects />}
            {activeTab === 'integrations' && <Integrations onReconfigure={() => setIsSetupComplete(false)} />}
            {activeTab === 'notifications' && <Notifications />}
            {activeTab === 'settings' && <Settings onReconfigure={() => setIsSetupComplete(false)} />}
          </div>
        </div>
      )}
    </>
  );
}

export default App;
