import { Cloud, Database, Globe, GitBranch, Shield, Box } from 'lucide-react';

export default function Integrations({ onReconfigure }: { onReconfigure?: () => void }) {
  const categories = [
    {
      title: "Infrastructure & Cloud",
      items: [
        { id: 'aws', name: 'AWS EC2', icon: Cloud, color: 'text-orange-400', status: 'connected' },
        { id: 'gcp', name: 'Google Cloud', icon: Database, color: 'text-blue-400', status: 'disconnected' },
        { id: 'azure', name: 'Microsoft Azure', icon: Cloud, color: 'text-blue-500', status: 'disconnected' },
        { id: 'vercel', name: 'Vercel', icon: Globe, color: 'text-white', status: 'disconnected' },
        { id: 'kubernetes', name: 'Kubernetes', icon: Box, color: 'text-blue-500', status: 'disconnected' },
      ]
    },
    {
      title: "CI/CD & Source Control",
      items: [
        { id: 'github', name: 'GitHub', icon: GitBranch, color: 'text-white', status: 'connected' },
        { id: 'gitlab', name: 'GitLab', icon: GitBranch, color: 'text-orange-500', status: 'disconnected' },
        { id: 'jenkins', name: 'Jenkins', icon: Box, color: 'text-red-400', status: 'disconnected' },
      ]
    },
    {
      title: "Security & Monitoring",
      items: [
        { id: 'datadog', name: 'Datadog', icon: Shield, color: 'text-purple-400', status: 'disconnected' },
        { id: 'snyk', name: 'Snyk', icon: Shield, color: 'text-purple-500', status: 'disconnected' },
      ]
    }
  ];

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-white mb-2">Integrations</h1>
        <p className="text-gray-400">Connect the tools Prash uses to monitor, diagnose, and fix your infrastructure.</p>
      </div>

      <div className="space-y-12">
        {categories.map((cat, i) => (
          <div key={i}>
            <h2 className="text-xl font-semibold text-white mb-6 flex items-center gap-3">
              <div className="w-1.5 h-6 bg-accent rounded-full" />
              {cat.title}
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {cat.items.map((item) => {
                const Icon = item.icon;
                return (
                  <div key={item.id} className="flex flex-col p-6 rounded-2xl border border-gray-800 bg-gray-900/30 hover:border-gray-600 transition-colors">
                    <div className="flex justify-between items-start mb-4">
                      <div className={`p-3 rounded-xl bg-gray-800/80 ${item.color}`}>
                        <Icon size={24} />
                      </div>
                      {item.status === 'connected' ? (
                        <span className="px-3 py-1 bg-accent/20 text-accent text-xs font-medium rounded-full">Connected</span>
                      ) : (
                        <span className="px-3 py-1 bg-gray-800 text-gray-400 text-xs font-medium rounded-full">Not Connected</span>
                      )}
                    </div>
                    <h3 className="text-lg font-medium text-white mb-1">{item.name}</h3>
                    <p className="text-sm text-gray-500 mb-6">Connect {item.name} to allow Prash to monitor its resources.</p>
                    
                    <button 
                      onClick={onReconfigure}
                      className={`w-full py-2.5 rounded-lg font-medium text-sm transition-colors ${
                      item.status === 'connected' 
                        ? 'bg-gray-800 text-white hover:bg-gray-700' 
                        : 'bg-accent/10 text-accent hover:bg-accent hover:text-background'
                    }`}>
                      {item.status === 'connected' ? 'Configure' : 'Connect'}
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
