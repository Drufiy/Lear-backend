import { useState } from 'react';
import { motion } from 'framer-motion';
import { ChevronRight, CheckCircle2, Loader2, AlertCircle } from 'lucide-react';

export default function StepCredentials({ onComplete, config }: { onComplete: () => void, config: any }) {
  const [testing, setTesting] = useState(false);
  const [status, setStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [creds, setCreds] = useState<any>({});

  const handleChange = (k: string, v: string) => setCreds((prev: any) => ({ ...prev, [k]: v }));

  const testConnection = async () => {
    setTesting(true);
    setStatus('idle');
    try {
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(creds)
      });
      if (res.ok) {
        setStatus('success');
      } else {
        setStatus('error');
      }
    } catch(e) {
      setStatus('error');
    } finally {
      setTesting(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      className="flex flex-col items-center justify-center w-full max-w-2xl mx-auto"
    >
      <div className="text-center mb-12">
        <h1 className="text-4xl font-bold mb-4 tracking-tight">Configure Connections</h1>
        <p className="text-gray-400 text-lg">Provide access credentials for the services you selected.</p>
      </div>

      <div className="w-full bg-gray-900/50 border border-gray-800 rounded-2xl p-8 mb-8 space-y-6">
        {/* Placeholder for dynamic credential fields based on config.services */}
        {config.services?.includes('aws') && (
          <div className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-400">AWS Access Key ID</label>
              <input 
                type="text" 
                value={creds.AWS_ACCESS_KEY_ID || ''}
                onChange={(e) => handleChange('AWS_ACCESS_KEY_ID', e.target.value)}
                className="w-full bg-gray-950 border border-gray-800 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-accent transition-colors" 
                placeholder="AKIA..." 
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-400">AWS Secret Access Key</label>
              <input 
                type="password" 
                value={creds.AWS_SECRET_ACCESS_KEY || ''}
                onChange={(e) => handleChange('AWS_SECRET_ACCESS_KEY', e.target.value)}
                className="w-full bg-gray-950 border border-gray-800 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-accent transition-colors" 
                placeholder="secret..." 
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-400">AWS Region</label>
              <input 
                type="text" 
                value={creds.AWS_REGION || ''}
                onChange={(e) => handleChange('AWS_REGION', e.target.value)}
                className="w-full bg-gray-950 border border-gray-800 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-accent transition-colors" 
                placeholder="us-east-1" 
              />
            </div>
          </div>
        )}
        
        {config.services?.includes('github') && (
          <div className="space-y-2">
            <label className="text-sm font-medium text-gray-400">GitHub Personal Access Token</label>
            <input 
              type="password" 
              value={creds.GITHUB_TOKEN || ''}
              onChange={(e) => handleChange('GITHUB_TOKEN', e.target.value)}
              className="w-full bg-gray-950 border border-gray-800 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-accent transition-colors" 
              placeholder="ghp_..." 
            />
          </div>
        )}

        {config.services?.length === 0 && (
          <div className="text-center text-gray-500 py-8">
            No services selected. You can add them later in settings.
          </div>
        )}

        <div className="pt-6 border-t border-gray-800 flex justify-between items-center">
          <button 
            onClick={testConnection}
            disabled={testing || config.services?.length === 0}
            className="text-accent hover:text-[#2da36c] font-medium flex items-center gap-2 disabled:opacity-50"
          >
            {testing && <Loader2 size={16} className="animate-spin" />}
            Test Connections
          </button>
          
          {status === 'success' && (
            <span className="flex items-center gap-2 text-accent"><CheckCircle2 size={18} /> Verified</span>
          )}
          {status === 'error' && (
            <span className="flex items-center gap-2 text-red-500"><AlertCircle size={18} /> Failed</span>
          )}
        </div>
      </div>

      <button
        onClick={onComplete}
        className="flex items-center gap-2 px-8 py-4 rounded-full bg-accent text-background font-semibold text-lg hover:bg-[#2da36c] transition-colors"
      >
        Finish Setup <ChevronRight size={20} />
      </button>
    </motion.div>
  );
}
