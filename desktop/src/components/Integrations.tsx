import { useState, useEffect } from 'react';
import { Cloud, ExternalLink, Loader2 } from 'lucide-react';

interface Connector {
  id: string;
  name: string;
  category: string;
  icon: string;
  color: string;
  description: string;
  status: 'configured' | 'unconfigured';
  docs_url?: string;
  auth_fields: any[];
}

export default function Integrations({ onConfigureConnector }: { onConfigureConnector?: (connectorId: string) => void }) {
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/connectors')
      .then(res => res.json())
      .then(data => setConnectors(data.connectors || []))
      .catch(err => console.error('Error loading connectors:', err))
      .finally(() => setLoading(false));
  }, []);

  const categories = Array.from(new Set(connectors.map(c => c.category)));

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-white mb-2">Connected Integrations</h1>
        <p className="text-sm text-gray-400">
          All 13 available providers supported by the Lear Intelligence Platform.
        </p>
      </div>

      {loading ? (
        <div className="flex justify-center py-20">
          <Loader2 className="w-8 h-8 animate-spin text-accent" />
        </div>
      ) : (
        <div className="space-y-10">
          {categories.map(cat => {
            const items = connectors.filter(c => c.category === cat);
            return (
              <div key={cat}>
                <h2 className="text-base font-bold text-white uppercase tracking-wider mb-4 flex items-center gap-2">
                  <span className="w-1.5 h-4 bg-accent rounded-full" />
                  {cat}
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {items.map(item => {
                    const isConfigured = item.status === 'configured';
                    return (
                      <div
                        key={item.id}
                        className="glass-card rounded-2xl p-6 flex flex-col justify-between"
                      >
                        <div>
                          <div className="flex justify-between items-start mb-4">
                            <div
                              className="p-3 rounded-xl border border-white/10"
                              style={{ backgroundColor: `${item.color}20` }}
                            >
                              <Cloud size={24} style={{ color: item.color }} />
                            </div>
                            <span
                              className={`px-3 py-1 text-xs font-semibold rounded-full border ${
                                isConfigured
                                  ? 'bg-accent/15 text-accent border-accent/30'
                                  : 'bg-surface text-gray-400 border-border-subtle'
                              }`}
                            >
                              {isConfigured ? '● Configured' : '○ Not Configured'}
                            </span>
                          </div>
                          <h3 className="font-bold text-base text-white">{item.name}</h3>
                          <p className="text-xs text-gray-400 mt-1 line-clamp-2">{item.description}</p>
                        </div>

                        <div className="flex items-center justify-between pt-4 mt-4 border-t border-border-subtle text-xs">
                          {item.docs_url ? (
                            <a
                              href={item.docs_url}
                              target="_blank"
                              rel="noreferrer"
                              className="flex items-center gap-1 text-gray-400 hover:text-white transition-colors"
                            >
                              Docs <ExternalLink size={12} />
                            </a>
                          ) : (
                            <span />
                          )}

                          {onConfigureConnector && (
                            <button
                              onClick={() => onConfigureConnector(item.id)}
                              className="px-3 py-1.5 rounded-lg bg-surface hover:bg-surface-elevated border border-border-subtle hover:border-accent/40 text-xs font-medium text-gray-200 transition-all cursor-pointer"
                            >
                              {isConfigured ? 'Reconfigure' : 'Connect'}
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
