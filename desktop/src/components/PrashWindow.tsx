import { Sparkles, Terminal } from 'lucide-react';
import { useState, useEffect } from 'react';

export default function PrashWindow() {
  const [summary, setSummary] = useState('');
  const [typing, setTyping] = useState(true);
  
  const aiText = "All services are currently healthy. The AWS EC2 watcher reported a minor CPU spike on 'api-production' 5 minutes ago, but it has stabilized. No pending actions required.";

  useEffect(() => {
    let i = 0;
    const interval = setInterval(() => {
      setSummary(aiText.substring(0, i));
      i++;
      if (i > aiText.length) {
        clearInterval(interval);
        setTyping(false);
      }
    }, 20);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="bg-gradient-to-br from-gray-900 to-black border border-gray-800 rounded-2xl p-6 relative overflow-hidden h-full flex flex-col">
      <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-accent to-blue-500" />
      
      <div className="flex justify-between items-start mb-4">
        <h3 className="text-xl font-semibold flex items-center gap-2 text-accent">
          <Sparkles size={20} /> Prash AI
        </h3>
        <button className="p-2 bg-gray-800/50 rounded-lg hover:bg-gray-700 transition-colors text-gray-400 hover:text-white">
          <Terminal size={18} />
        </button>
      </div>
      
      <div className="flex-grow flex flex-col justify-center">
        <p className="text-lg text-gray-300 leading-relaxed font-light">
          {summary}
          {typing && <span className="inline-block w-2 h-5 bg-accent ml-1 animate-pulse" />}
        </p>
      </div>
    </div>
  );
}
