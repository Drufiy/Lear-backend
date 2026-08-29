import { useState } from 'react';
import { motion } from 'framer-motion';
import { Server, Monitor, Globe, ChevronRight, CheckCircle2 } from 'lucide-react';

export default function StepLocation({ onNext }: { onNext: (data: any) => void }) {
  const [selected, setSelected] = useState<string | null>(null);

  const options = [
    { id: 'local', title: 'Local Device', icon: Monitor, desc: 'Run Prash securely on this machine.' },
    { id: 'ssh', title: 'SSH Server', icon: Server, desc: 'Connect to an existing Linux server via SSH.' },
    { id: 'cloud', title: 'Cloud Server', icon: Globe, desc: 'Deploy Prash to AWS, GCP, or Azure.' }
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      className="flex flex-col items-center justify-center w-full max-w-2xl mx-auto"
    >
      <div className="text-center mb-12">
        <h1 className="text-4xl font-bold mb-4 tracking-tight">Where should the watcher run?</h1>
        <p className="text-gray-400 text-lg">Prash needs a home to constantly monitor your infrastructure.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 w-full mb-12">
        {options.map((opt) => {
          const Icon = opt.icon;
          const isSelected = selected === opt.id;
          return (
            <button
              key={opt.id}
              onClick={() => setSelected(opt.id)}
              className={`relative flex flex-col items-center p-6 rounded-2xl border-2 transition-all duration-300 text-left ${
                isSelected ? 'border-accent bg-accent/10 shadow-[0_0_20px_rgba(57,188,129,0.2)]' : 'border-gray-800 hover:border-gray-600 bg-gray-900/50'
              }`}
            >
              {isSelected && (
                <div className="absolute top-4 right-4 text-accent">
                  <CheckCircle2 size={20} />
                </div>
              )}
              <div className={`p-4 rounded-full mb-4 ${isSelected ? 'bg-accent/20 text-accent' : 'bg-gray-800 text-gray-400'}`}>
                <Icon size={32} />
              </div>
              <h3 className="text-xl font-semibold mb-2">{opt.title}</h3>
              <p className="text-gray-500 text-sm text-center">{opt.desc}</p>
            </button>
          );
        })}
      </div>

      <button
        disabled={!selected}
        onClick={() => onNext({ location: selected })}
        className="flex items-center gap-2 px-8 py-4 rounded-full bg-accent text-background font-semibold text-lg hover:bg-[#2da36c] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        Continue <ChevronRight size={20} />
      </button>
    </motion.div>
  );
}
