import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import ModesUI from './ModesUI';
import PrashWindow from './PrashWindow';
import Chatbot from './Chatbot';
import { Cloud, GitBranch, Globe, Database, Activity, Search, Server, HardDrive, ArrowRight, X } from 'lucide-react';

const Speedometer = ({ value }: { value: number }) => {
  const rotation = -90 + (value / 100) * 180;
  return (
    <div className="relative w-32 h-16 overflow-hidden flex flex-col items-center">
      <div className="w-32 h-32 rounded-full border-[12px] border-gray-800 border-b-transparent border-r-transparent rotate-45 absolute top-0" />
      <div 
        className="w-32 h-32 rounded-full border-[12px] border-accent border-b-transparent border-r-transparent absolute top-0 transition-all duration-1000 ease-out"
        style={{ transform: `rotate(${rotation - 45}deg)` }}
      />
      <div className="absolute bottom-0 text-xl font-bold">{value.toFixed(1)}%</div>
      <div className="absolute bottom-[-16px] text-xs text-gray-500">CPU</div>
    </div>
  );
};

const AWSWidget = ({ isPill, onExpand }: { isPill: boolean, onExpand: () => void }) => {
  const [metrics, setMetrics] = useState<any>(null);

  useEffect(() => {
    if (isPill) return;
    fetch('/api/metrics/aws')
      .then(r => r.json())
      .then(data => setMetrics(data))
      .catch(() => {});
  }, [isPill]);

  if (isPill) {
    return (
      <button onClick={onExpand} className="flex items-center gap-2 px-4 py-2 bg-gray-900 border border-gray-800 rounded-full hover:bg-gray-800 transition-colors">
        <Cloud size={16} className="text-orange-400" />
        <span className="text-sm font-medium">AWS EC2</span>
        <div className="w-2 h-2 rounded-full bg-accent animate-pulse" />
      </button>
    );
  }

  return (
    <motion.div layoutId="aws-widget" className="bg-gray-900/40 border border-gray-800 rounded-2xl p-6 relative overflow-hidden">
      <div className="flex justify-between items-center mb-6">
        <div className="flex items-center gap-3">
          <div className="p-3 bg-gray-800/50 rounded-xl">
            <Cloud size={24} className="text-orange-400" />
          </div>
          <div>
            <h3 className="font-semibold text-lg">AWS EC2 Cluster</h3>
            <p className="text-sm text-gray-500">us-east-1</p>
          </div>
        </div>
        <div className="flex items-center gap-2 px-3 py-1 bg-accent/10 text-accent rounded-full text-sm font-medium">
          <div className="w-2 h-2 rounded-full bg-accent animate-pulse" />
          Healthy
        </div>
      </div>
      
      {metrics ? (
        <div className="flex items-center justify-between mt-4">
          <Speedometer value={metrics.cpu || 0} />
          <div className="flex-1 flex justify-center items-center px-4">
            <ArrowRight className="text-gray-700" />
          </div>
          <div className="flex flex-col items-center">
            <div className="w-16 h-16 rounded-full bg-gray-800 flex items-center justify-center relative">
              <HardDrive size={24} className="text-blue-400" />
              <svg className="absolute inset-0 w-full h-full transform -rotate-90">
                <circle cx="32" cy="32" r="30" fill="none" stroke="#1f2937" strokeWidth="4" />
                <circle cx="32" cy="32" r="30" fill="none" stroke="#60a5fa" strokeWidth="4" strokeDasharray="188" strokeDashoffset={188 - (188 * (metrics.disk_usage || 0)) / 100} className="transition-all duration-1000" />
              </svg>
            </div>
            <span className="mt-2 text-sm font-bold">{metrics.disk_usage?.toFixed(1) || 0}%</span>
            <span className="text-xs text-gray-500">Disk I/O</span>
          </div>
        </div>
      ) : (
        <div className="flex justify-center py-8">
          <Loader2 className="animate-spin text-gray-500" />
        </div>
      )}
    </motion.div>
  );
};

export default function Dashboard() {
  const [chatOpen, setChatOpen] = useState(false);
  const [services, setServices] = useState<any[]>([]);

  useEffect(() => {
    fetch('/api/status').then(r => r.json()).then(data => setServices(data.statuses || []));
  }, []);

  return (
    <div className="min-h-screen bg-background text-white p-8 relative">
      <div className="flex justify-between items-center mb-10">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Project Overview</h1>
          <p className="text-gray-400 mt-1">Monitoring {services.length} active services.</p>
        </div>
        <div className="flex gap-4">
          <button 
            onClick={() => setChatOpen(true)}
            className="flex items-center gap-2 bg-accent text-black px-5 py-2 rounded-full font-semibold hover:bg-[#2da36c] transition-colors"
          >
            <Activity size={18} /> Open Prash Copilot
          </button>
        </div>
      </div>

      {/* When chat is open, display pills */}
      <AnimatePresence>
        {chatOpen && (
          <motion.div 
            initial={{ opacity: 0, y: -20 }} 
            animate={{ opacity: 1, y: 0 }} 
            exit={{ opacity: 0, y: -20 }}
            className="flex flex-wrap gap-3 mb-8"
          >
            {services.map(s => {
              if (s.id === 'aws') return <AWSWidget key={s.id} isPill={true} onExpand={() => setChatOpen(false)} />;
              return (
                <button key={s.id} onClick={() => setChatOpen(false)} className="flex items-center gap-2 px-4 py-2 bg-gray-900 border border-gray-800 rounded-full hover:bg-gray-800">
                  <span className="text-sm font-medium">{s.name}</span>
                  <div className={`w-2 h-2 rounded-full ${s.status === 'error' ? 'bg-red-500' : 'bg-accent'}`} />
                </button>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>

      <div className={`grid grid-cols-1 ${chatOpen ? 'lg:grid-cols-1' : 'lg:grid-cols-3'} gap-8 transition-all duration-500`}>
        <div className="lg:col-span-2 space-y-6">
          <AnimatePresence>
            {!chatOpen && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, height: 0, overflow: 'hidden' }} className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {services.map(s => {
                  if (s.id === 'aws') return <AWSWidget key={s.id} isPill={false} onExpand={() => {}} />;
                  
                  const Icon = s.type === 'GCP' ? Database : s.type === 'GitHub' ? GitBranch : Globe;
                  return (
                    <div key={s.id} className="bg-gray-900/40 border border-gray-800 rounded-2xl p-6 flex flex-col justify-between">
                      <div className="flex items-center gap-4 mb-4">
                        <div className="p-3 bg-gray-800 rounded-xl"><Icon size={24} className="text-gray-300" /></div>
                        <div>
                          <h4 className="font-semibold text-lg">{s.name}</h4>
                          <p className="text-sm text-gray-500">{s.type}</p>
                        </div>
                      </div>
                      <div className="flex items-center justify-between mt-auto pt-4 border-t border-gray-800/50">
                        <span className={`text-sm font-medium capitalize flex items-center gap-2 ${s.status === 'error' ? 'text-red-500' : 'text-accent'}`}>
                          <div className={`w-2 h-2 rounded-full ${s.status === 'error' ? 'bg-red-500' : 'bg-accent animate-pulse'}`} />
                          {s.status}
                        </span>
                        <span className="text-xs text-gray-500">{s.ping}</span>
                      </div>
                    </div>
                  );
                })}
              </motion.div>
            )}
          </AnimatePresence>

          <div className="mt-8">
            <PrashWindow />
          </div>
        </div>

        {!chatOpen && (
          <div className="space-y-8">
            <ModesUI />
          </div>
        )}
      </div>

      <Chatbot isOpen={chatOpen} onClose={() => setChatOpen(false)} />
    </div>
  );
}
