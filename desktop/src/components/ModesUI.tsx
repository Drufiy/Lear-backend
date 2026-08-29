import { Activity, ShieldCheck, Settings } from 'lucide-react';
import { useState } from 'react';

export default function ModesUI() {
  const [mode, setMode] = useState('strict');

  const modes = [
    { id: 'strict', name: 'Strict Mode', desc: 'Watch, alert, and ask for permission before applying fixes.', icon: ShieldCheck },
    { id: 'advanced', name: 'Advanced Mode', desc: 'Agent automatically applies safe fixes without asking.', icon: Activity },
    { id: 'custom', name: 'Custom Mode', desc: 'Define your own alerting and fixing rules.', icon: Settings },
  ];

  return (
    <div className="bg-gray-900/50 border border-gray-800 rounded-2xl p-6 h-full flex flex-col">
      <h3 className="text-xl font-semibold mb-6 flex items-center gap-2">
        <Settings className="text-accent" /> Project Modes
      </h3>
      <div className="space-y-4 flex-grow">
        {modes.map((m) => {
          const Icon = m.icon;
          const isSelected = mode === m.id;
          return (
            <button
              key={m.id}
              onClick={() => setMode(m.id)}
              className={`w-full text-left p-4 rounded-xl border transition-all ${
                isSelected ? 'border-accent bg-accent/10 shadow-[0_0_15px_rgba(57,188,129,0.1)]' : 'border-gray-800 hover:border-gray-700 bg-gray-950/50'
              }`}
            >
              <div className="flex items-center gap-3 mb-1">
                <Icon size={18} className={isSelected ? 'text-accent' : 'text-gray-400'} />
                <span className={`font-medium ${isSelected ? 'text-accent' : 'text-gray-300'}`}>{m.name}</span>
              </div>
              <p className="text-sm text-gray-500 pl-7">{m.desc}</p>
            </button>
          );
        })}
      </div>
    </div>
  );
}
