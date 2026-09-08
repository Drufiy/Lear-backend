import { useState, useEffect } from 'react';
import { Cloud, GitBranch, Activity, Shield, Layers, CheckCircle2, AlertCircle, Loader2, ArrowRight, Sparkles } from 'lucide-react';

interface AuthField {
  key: string;
  label: string;
  type: string;
  required: boolean;
  default?: string;
  placeholder?: string;
  help_text?: string;
}

interface Connector {
  id: string;
  name: string;
  category: string;
  icon: string;
  color: string;
  description: string;
  status: 'configured' | 'unconfigured';
  auth_fields: AuthField[];
}

const CATEGORY_META: Record<string, { label: string; icon: any }> = {
  infrastructure: { label: 'Infrastructure', icon: Cloud },
  cicd: { label: 'CI/CD & Pipelines', icon: GitBranch },
  monitoring: { label: 'Observability', icon: Activity },
  security: { label: 'Security & Scanning', icon: Shield },
  iac: { label: 'Infrastructure as Code', icon: Layers },
};

export default function Wizard({ onComplete }: { onComplete: (config?: any) => void }) {
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeCategory, setActiveCategory] = useState<string>('infrastructure');
  const [selectedConnectorId, setSelectedConnectorId] = useState<string>('aws');
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [authStatus, setAuthStatus] = useState<{ success?: boolean; message?: string } | null>(null);

  useEffect(() => {
    fetch('/api/connectors')
      .then(res => res.json())
      .then(data => {
        const list: Connector[] = data.connectors || [];
        setConnectors(list);
        if (list.length > 0) {
          setSelectedConnectorId(list[0].id);
        }
      })
      .catch(err => console.error('Error fetching connectors:', err))
      .finally(() => setLoading(false));
  }, []);

  const selectedConnector = connectors.find(c => c.id === selectedConnectorId);
  const categories = Array.from(new Set(connectors.map(c => c.category)));

  const handleInputChange = (key: string, value: string) => {
    setCredentials(prev => ({ ...prev, [key]: value }));
  };

  const handleConnect = async () => {
    if (!selectedConnector) return;
    setSubmitting(true);
    setAuthStatus(null);

    try {
      const res = await fetch(`/api/connectors/${selectedConnector.id}/connect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(credentials),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        setAuthStatus({ success: true, message: data.message || 'Connected successfully!' });
        // Update local status
        setConnectors(prev =>
          prev.map(c => (c.id === selectedConnector.id ? { ...c, status: 'configured' } : c))
        );
      } else {
        setAuthStatus({ success: false, message: data.message || 'Connection failed.' });
      }
    } catch (e: any) {
      setAuthStatus({ success: false, message: e.message || 'Network error reaching API bridge.' });
    } finally {
      setSubmitting(false);
    }
  };

  const handleFinish = async () => {
    try {
      await fetch('/api/projects/auto-import', { method: 'POST' });
    } catch (e) {
      console.error('Auto import error:', e);
    }
    onComplete();
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-background text-white flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-accent" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background text-white flex flex-col items-center py-12 px-8 relative overflow-y-auto">
      {/* Background Ambience */}
      <div className="absolute top-[-20%] left-[-10%] w-[50%] h-[50%] bg-accent/10 blur-[140px] rounded-full pointer-events-none" />
      <div className="absolute bottom-[-20%] right-[-10%] w-[40%] h-[40%] bg-cyan-500/10 blur-[140px] rounded-full pointer-events-none" />

      <div className="w-full max-w-5xl relative z-10">
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-accent/10 border border-accent/25 text-accent text-xs font-semibold mb-3">
            <Sparkles size={14} /> LEAR INTELLIGENCE PLATFORM
          </div>
          <h1 className="text-4xl font-bold tracking-tight text-white">Connect Your Infrastructure</h1>
          <p className="text-gray-400 text-sm max-w-xl mx-auto mt-2">
            Configure live credentials for any of your 13 backend services. Lear verifies credentials directly against real provider APIs.
          </p>
        </div>

        <div className="flex flex-col lg:flex-row gap-8">
          {/* Category & Connector Selection */}
          <div className="w-full lg:w-72 shrink-0 space-y-4">
            <div className="glass-panel rounded-xl p-2 space-y-1">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-400 px-3 py-1.5 block">
                Categories
              </span>
              {categories.map(cat => {
                const meta = CATEGORY_META[cat] || { label: cat, icon: Cloud };
                const Icon = meta.icon;
                const isCatActive = activeCategory === cat;
                return (
                  <button
                    key={cat}
                    onClick={() => {
                      setActiveCategory(cat);
                      const firstInCat = connectors.find(c => c.category === cat);
                      if (firstInCat) setSelectedConnectorId(firstInCat.id);
                    }}
                    className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                      isCatActive
                        ? 'bg-accent/15 text-accent border border-accent/25'
                        : 'text-gray-400 hover:text-white hover:bg-surface'
                    }`}
                  >
                    <Icon size={16} />
                    {meta.label}
                  </button>
                );
              })}
            </div>

            {/* Connectors in Category */}
            <div className="glass-panel rounded-xl p-2 space-y-1">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-400 px-3 py-1.5 block">
                Services
              </span>
              {connectors
                .filter(c => c.category === activeCategory)
                .map(c => {
                  const isSelected = selectedConnectorId === c.id;
                  return (
                    <button
                      key={c.id}
                      onClick={() => {
                        setSelectedConnectorId(c.id);
                        setAuthStatus(null);
                      }}
                      className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                        isSelected
                          ? 'bg-surface-elevated text-white border border-border-hover'
                          : 'text-gray-400 hover:text-white hover:bg-surface'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full" style={{ backgroundColor: c.color }} />
                        <span>{c.name}</span>
                      </div>
                      {c.status === 'configured' && (
                        <CheckCircle2 size={14} className="text-accent" />
                      )}
                    </button>
                  );
                })}
            </div>
          </div>

          {/* Dynamic Form Area */}
          <div className="flex-1 glass-card rounded-2xl p-8 flex flex-col justify-between">
            {selectedConnector ? (
              <div className="space-y-6">
                <div className="flex items-center justify-between pb-4 border-b border-border-subtle">
                  <div className="flex items-center gap-3">
                    <div
                      className="p-3 rounded-xl border border-white/10"
                      style={{ backgroundColor: `${selectedConnector.color}20` }}
                    >
                      <Cloud size={24} style={{ color: selectedConnector.color }} />
                    </div>
                    <div>
                      <h2 className="text-xl font-bold text-white">{selectedConnector.name}</h2>
                      <p className="text-xs text-gray-400">{selectedConnector.description}</p>
                    </div>
                  </div>
                  <span
                    className={`text-xs px-2.5 py-1 rounded-full font-medium ${
                      selectedConnector.status === 'configured'
                        ? 'bg-accent/15 text-accent border border-accent/30'
                        : 'bg-surface text-gray-400 border border-border-subtle'
                    }`}
                  >
                    {selectedConnector.status === 'configured' ? '● Configured' : '○ Not Configured'}
                  </span>
                </div>

                {/* Dynamic Auth Fields Form */}
                <div className="space-y-4">
                  {selectedConnector.auth_fields.map(field => (
                    <div key={field.key} className="space-y-1.5">
                      <label className="text-xs font-medium text-gray-300 flex items-center gap-1">
                        {field.label}
                        {field.required && <span className="text-rose-400">*</span>}
                      </label>
                      <input
                        type={field.type === 'password' ? 'password' : 'text'}
                        placeholder={field.placeholder || `Enter ${field.label}`}
                        value={credentials[field.key] || ''}
                        onChange={e => handleInputChange(field.key, e.target.value)}
                        className="w-full bg-surface border border-border-subtle focus:border-accent rounded-xl px-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none transition-all font-mono"
                      />
                      {field.help_text && (
                        <p className="text-[11px] text-gray-500">{field.help_text}</p>
                      )}
                    </div>
                  ))}
                </div>

                {/* Live Auth Feedback */}
                {authStatus && (
                  <div
                    className={`p-3.5 rounded-xl text-xs flex items-center gap-2 border ${
                      authStatus.success
                        ? 'bg-accent/10 border-accent/30 text-accent'
                        : 'bg-rose-500/10 border-rose-500/30 text-rose-400'
                    }`}
                  >
                    {authStatus.success ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
                    <span>{authStatus.message}</span>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex items-center justify-center py-20 text-gray-500">
                Select a service to configure credentials
              </div>
            )}

            {/* Bottom Actions */}
            <div className="flex items-center justify-between pt-6 border-t border-border-subtle mt-8">
              <button
                onClick={handleConnect}
                disabled={submitting}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-accent hover:bg-accent-light text-gray-950 font-bold text-xs transition-all shadow-lg cursor-pointer disabled:opacity-50"
              >
                {submitting ? <Loader2 size={16} className="animate-spin" /> : null}
                {submitting ? 'Authenticating...' : 'Validate & Save Credentials'}
              </button>

              <button
                onClick={handleFinish}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-surface hover:bg-surface-elevated border border-border-subtle hover:border-accent/40 text-xs font-semibold text-white transition-all cursor-pointer"
              >
                <span>Continue to Dashboard</span>
                <ArrowRight size={16} />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
