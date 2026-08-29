import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Cloud, GitBranch, Database, MessageSquare, Shield, CheckCircle2, AlertCircle, Loader2, Play, Settings, UploadCloud } from 'lucide-react';

export default function Wizard({ onComplete }: { onComplete: (config: any) => void }) {
  const [activeTab, setActiveTab] = useState<'infra' | 'cicd' | 'notif' | 'security'>('infra');
  const [creds, setCreds] = useState<any>({});
  
  // Status tracking per service: idle | loading | success | error 
  const [statuses, setStatuses] = useState<Record<string, { state: string, msg?: string }>>({});

  const handleChange = (k: string, v: string) => setCreds((prev: any) => ({ ...prev, [k]: v }));

  const connectService = async (serviceId: string) => {
    setStatuses(prev => ({ ...prev, [serviceId]: { state: 'loading' } }));
    
    // We only send the credentials related to this service
    const payload: any = {};
    if (serviceId === 'aws') {
      payload.AWS_ACCESS_KEY_ID = creds.AWS_ACCESS_KEY_ID;
      payload.AWS_SECRET_ACCESS_KEY = creds.AWS_SECRET_ACCESS_KEY;
      payload.AWS_REGION = creds.AWS_REGION || 'us-east-1';
    } else if (serviceId === 'gcp') {
      payload.GCP_PROJECT_ID = creds.GCP_PROJECT_ID;
      payload.GCP_SERVICE_ACCOUNT_JSON = creds.GCP_SERVICE_ACCOUNT_JSON;
    } else if (serviceId === 'github') {
      payload.GITHUB_TOKEN = creds.GITHUB_TOKEN;
    } else if (serviceId === 'slack') {
      payload.SLACK_BOT_TOKEN = creds.SLACK_BOT_TOKEN;
    }

    try {
      const res = await fetch(`/api/connect/${serviceId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      
      if (data.success) {
        setStatuses(prev => ({ ...prev, [serviceId]: { state: 'success', msg: data.message } }));
      } else {
        setStatuses(prev => ({ ...prev, [serviceId]: { state: 'error', msg: data.message } }));
      }
    } catch (e: any) {
      setStatuses(prev => ({ ...prev, [serviceId]: { state: 'error', msg: "Network error reaching backend" } }));
    }
  };

  const getStatusUI = (serviceId: string) => {
    const s = statuses[serviceId];
    if (!s) return null;
    if (s.state === 'loading') return <Loader2 size={18} className="animate-spin text-accent" />;
    if (s.state === 'success') return <span className="flex items-center gap-1 text-accent text-sm"><CheckCircle2 size={16}/> Connected</span>;
    if (s.state === 'error') return <span className="flex items-center gap-1 text-red-500 text-sm" title={s.msg}><AlertCircle size={16}/> Failed</span>;
  };

  return (
    <div className="min-h-screen bg-background text-white flex flex-col items-center py-12 px-8 overflow-y-auto relative">
      <div className="absolute top-[-20%] left-[-10%] w-[50%] h-[50%] bg-accent/10 blur-[120px] rounded-full pointer-events-none" />
      <div className="absolute bottom-[-20%] right-[-10%] w-[40%] h-[40%] bg-blue-500/10 blur-[120px] rounded-full pointer-events-none" />
      
      <div className="w-full max-w-5xl relative z-10">
        <div className="text-center mb-10">
          <h1 className="text-4xl font-bold mb-4 tracking-tight">Welcome to Prash</h1>
          <p className="text-gray-400 text-lg max-w-2xl mx-auto">
            Configure your infrastructure, CI/CD, and notification channels. 
            Every connection is strictly verified against real cloud endpoints.
          </p>
        </div>

        <div className="flex gap-8">
          {/* Sidebar Nav */}
          <div className="w-64 shrink-0 space-y-2">
            {[
              { id: 'infra', label: 'Infrastructure', icon: Cloud },
              { id: 'cicd', label: 'CI/CD & Source', icon: GitBranch },
              { id: 'notif', label: 'Notifications', icon: MessageSquare },
              { id: 'security', label: 'Security & Projects', icon: Shield },
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all ${activeTab === tab.id ? 'bg-accent/10 text-accent font-semibold border border-accent/20' : 'text-gray-400 hover:bg-gray-900 hover:text-white'}`}
              >
                <tab.icon size={18} />
                {tab.label}
              </button>
            ))}
          </div>

          {/* Main Content Area */}
          <div className="flex-1 bg-gray-900/50 border border-gray-800 rounded-2xl p-8 min-h-[500px]">
            <AnimatePresence mode="wait">
              {activeTab === 'infra' && (
                <motion.div key="infra" initial={{opacity:0, x:20}} animate={{opacity:1, x:0}} exit={{opacity:0, x:-20}} className="space-y-8">
                  
                  {/* AWS EC2 Block */}
                  <div className="p-6 bg-gray-950 border border-gray-800 rounded-xl">
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-3">
                        <Cloud className="text-orange-400" size={24} />
                        <h3 className="font-semibold text-lg">AWS EC2</h3>
                      </div>
                      {getStatusUI('aws')}
                    </div>
                    <div className="grid grid-cols-2 gap-4 mb-4">
                      <input type="text" placeholder="Access Key ID" value={creds.AWS_ACCESS_KEY_ID || ''} onChange={e => handleChange('AWS_ACCESS_KEY_ID', e.target.value)} className="bg-gray-900 border border-gray-800 rounded-lg px-4 py-2 focus:border-accent outline-none" />
                      <input type="password" placeholder="Secret Access Key" value={creds.AWS_SECRET_ACCESS_KEY || ''} onChange={e => handleChange('AWS_SECRET_ACCESS_KEY', e.target.value)} className="bg-gray-900 border border-gray-800 rounded-lg px-4 py-2 focus:border-accent outline-none" />
                      <input type="text" placeholder="Region (e.g. us-east-1)" value={creds.AWS_REGION || ''} onChange={e => handleChange('AWS_REGION', e.target.value)} className="col-span-2 bg-gray-900 border border-gray-800 rounded-lg px-4 py-2 focus:border-accent outline-none" />
                    </div>
                    {statuses['aws']?.state === 'error' && (
                      <p className="text-red-400 text-sm mb-4">{statuses['aws'].msg}</p>
                    )}
                    <button onClick={() => connectService('aws')} className="w-full py-2 bg-gray-800 hover:bg-gray-700 text-white rounded-lg font-medium transition-colors">Verify & Connect AWS</button>
                  </div>

                  {/* GCP Block */}
                  <div className="p-6 bg-gray-950 border border-gray-800 rounded-xl">
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-3">
                        <Database className="text-blue-400" size={24} />
                        <h3 className="font-semibold text-lg">Google Cloud</h3>
                      </div>
                      {getStatusUI('gcp')}
                    </div>
                    <div className="grid grid-cols-1 gap-4 mb-4">
                      <input type="text" placeholder="Project ID" value={creds.GCP_PROJECT_ID || ''} onChange={e => handleChange('GCP_PROJECT_ID', e.target.value)} className="bg-gray-900 border border-gray-800 rounded-lg px-4 py-2 focus:border-accent outline-none" />
                      <textarea placeholder="Service Account JSON" rows={3} value={creds.GCP_SERVICE_ACCOUNT_JSON || ''} onChange={e => handleChange('GCP_SERVICE_ACCOUNT_JSON', e.target.value)} className="bg-gray-900 border border-gray-800 rounded-lg px-4 py-2 focus:border-accent outline-none font-mono text-xs"></textarea>
                    </div>
                    <button onClick={() => connectService('gcp')} className="w-full py-2 bg-gray-800 hover:bg-gray-700 text-white rounded-lg font-medium transition-colors">Verify & Connect GCP</button>
                  </div>

                </motion.div>
              )}

              {activeTab === 'cicd' && (
                <motion.div key="cicd" initial={{opacity:0, x:20}} animate={{opacity:1, x:0}} exit={{opacity:0, x:-20}} className="space-y-8">
                  {/* GitHub Block */}
                  <div className="p-6 bg-gray-950 border border-gray-800 rounded-xl">
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-3">
                        <GitBranch className="text-white" size={24} />
                        <h3 className="font-semibold text-lg">GitHub Actions</h3>
                      </div>
                      {getStatusUI('github')}
                    </div>
                    <div className="mb-4">
                      <input type="password" placeholder="Personal Access Token (ghp_...)" value={creds.GITHUB_TOKEN || ''} onChange={e => handleChange('GITHUB_TOKEN', e.target.value)} className="w-full bg-gray-900 border border-gray-800 rounded-lg px-4 py-2 focus:border-accent outline-none" />
                    </div>
                    {statuses['github']?.state === 'error' && (
                      <p className="text-red-400 text-sm mb-4">{statuses['github'].msg}</p>
                    )}
                    <button onClick={() => connectService('github')} className="w-full py-2 bg-gray-800 hover:bg-gray-700 text-white rounded-lg font-medium transition-colors">Verify & Connect GitHub</button>
                  </div>
                </motion.div>
              )}

              {activeTab === 'notif' && (
                <motion.div key="notif" initial={{opacity:0, x:20}} animate={{opacity:1, x:0}} exit={{opacity:0, x:-20}} className="space-y-8">
                  {/* Slack Block */}
                  <div className="p-6 bg-gray-950 border border-gray-800 rounded-xl">
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-3">
                        <MessageSquare className="text-pink-400" size={24} />
                        <h3 className="font-semibold text-lg">Slack</h3>
                      </div>
                      {getStatusUI('slack')}
                    </div>
                    <div className="mb-4">
                      <input type="password" placeholder="Bot User OAuth Token (xoxb-...)" value={creds.SLACK_BOT_TOKEN || ''} onChange={e => handleChange('SLACK_BOT_TOKEN', e.target.value)} className="w-full bg-gray-900 border border-gray-800 rounded-lg px-4 py-2 focus:border-accent outline-none" />
                    </div>
                    <button onClick={() => connectService('slack')} className="w-full py-2 bg-gray-800 hover:bg-gray-700 text-white rounded-lg font-medium transition-colors">Verify & Connect Slack</button>
                  </div>
                </motion.div>
              )}

              {activeTab === 'security' && (
                <motion.div key="security" initial={{opacity:0, x:20}} animate={{opacity:1, x:0}} exit={{opacity:0, x:-20}} className="space-y-6">
                  <h3 className="text-xl font-semibold mb-4">Security & Local Projects</h3>
                  
                  <div className="p-6 bg-gray-950 border border-gray-800 rounded-xl">
                    <h4 className="font-medium mb-2 flex items-center gap-2"><UploadCloud size={18}/> Auto-Import from .env</h4>
                    <p className="text-sm text-gray-400 mb-4">Prash can automatically scan your root .env file and build a prash.yaml project mapping for you securely.</p>
                    <button className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition-colors">Run Auto-Import</button>
                  </div>

                  <div className="p-6 bg-gray-950 border border-gray-800 rounded-xl">
                    <h4 className="font-medium mb-2 flex items-center gap-2"><Settings size={18}/> Agent LLM Provider</h4>
                    <div className="grid grid-cols-2 gap-4 mb-4">
                      <select className="bg-gray-900 border border-gray-800 rounded-lg px-4 py-2 outline-none">
                        <option>DeepSeek (Recommended)</option>
                        <option>OpenAI</option>
                      </select>
                      <input type="password" placeholder="API Key" className="bg-gray-900 border border-gray-800 rounded-lg px-4 py-2 focus:border-accent outline-none" />
                    </div>
                  </div>
                  
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>

        <div className="mt-8 flex justify-end">
          <button
            onClick={() => onComplete(creds)}
            className="flex items-center gap-2 px-8 py-3 rounded-full bg-accent text-black font-bold text-lg hover:bg-[#2da36c] transition-all shadow-[0_0_15px_rgba(57,188,129,0.3)] hover:scale-105"
          >
            <Play size={20} className="fill-black" /> Enter Dashboard
          </button>
        </div>
      </div>
    </div>
  );
}
