import { useState } from 'react';
import { motion } from 'framer-motion';
import { ChevronRight, Database, Globe, Cloud, GitBranch } from 'lucide-react';

const integrations = [
  { id: 'aws', name: 'AWS EC2', icon: Cloud, color: 'text-orange-400' },
  { id: 'gcp', name: 'Google Cloud', icon: Database, color: 'text-blue-400' },
  { id: 'github', name: 'GitHub', icon: GitBranch, color: 'text-white' },
  { id: 'domain', name: 'Domain', icon: Globe, color: 'text-purple-400' }
];

export default function StepIntegration({ onNext }: { onNext: (data: any) => void }) {
  const [selected, setSelected] = useState<string[]>([]);

  const toggle = (id: string) => {
    setSelected(prev => prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      className="flex flex-col items-center justify-center w-full max-w-4xl mx-auto"
    >
      <div className="text-center mb-12">
        <h1 className="text-4xl font-bold mb-4 tracking-tight">Connect your infrastructure</h1>
        <p className="text-gray-400 text-lg">Select the infrastructure you want Prash to monitor.</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-6 w-full mb-12">
        {integrations.map((service) => {
          const Icon = service.icon;
          const isSelected = selected.includes(service.id);
          return (
            <button
              key={service.id}
              onClick={() => toggle(service.id)}
              className={`flex items-center gap-4 p-6 rounded-2xl border-2 transition-all duration-300 ${
                isSelected ? 'border-accent bg-accent/10 shadow-[0_0_20px_rgba(57,188,129,0.15)]' : 'border-gray-800 hover:border-gray-600 bg-gray-900/50'
              }`}
            >
              <div className={`p-3 rounded-xl bg-gray-800/80 ${service.color}`}>
                <Icon size={28} />
              </div>
              <span className="text-lg font-medium">{service.name}</span>
            </button>
          );
        })}
      </div>

      <div className="flex gap-4">
        <button
          onClick={() => onNext({ services: selected })}
          className="flex items-center gap-2 px-8 py-4 rounded-full bg-accent text-background font-semibold text-lg hover:bg-[#2da36c] transition-colors"
        >
          {selected.length === 0 ? 'Skip for now' : 'Continue'} <ChevronRight size={20} />
        </button>
      </div>
    </motion.div>
  );
}
