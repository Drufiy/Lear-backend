import { useState, useEffect, useCallback } from 'react';
import { Cloud, ExternalLink, Loader2, X, Plus } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import ConnectorForm, { ConnectorModel } from './ConnectorForm';

export default function Integrations({ onConfigureConnector }: { onConfigureConnector?: (connectorId: string) => void }) {
  const [connectors, setConnectors] = useState<ConnectorModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeConnector, setActiveConnector] = useState<ConnectorModel | null>(null);

  const loadConnectors = useCallback(() => {
    fetch('/api/connectors')
      .then(res => res.json())
      .then(data => setConnectors(data.connectors || []))
      .catch(err => console.error('Error loading connectors:', err))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadConnectors();
  }, [loadConnectors]);

  const handleConfigure = (connector: ConnectorModel) => {
    if (onConfigureConnector) {
      onConfigureConnector(connector.id);
    }
    setActiveConnector(connector);
  };

  const handleConnectSuccess = () => {
    loadConnectors();
  };

  const handleDisconnectSuccess = () => {
    loadConnectors();
  };

  const categories = Array.from(new Set(connectors.map(c => c.category || 'infrastructure')));

  return (
    <div className="p-8 max-w-7xl mx-auto relative">
      <div className="flex flex-wrap justify-between items-center gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white mb-2">Connected Integrations</h1>
          <p className="text-sm text-gray-400">
            Manage live authentication credentials and provider connections across all {connectors.length} supported services.
          </p>
        </div>
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

                          <button
                            onClick={() => handleConfigure(item)}
                            className="px-3.5 py-1.5 rounded-lg bg-surface hover:bg-surface-elevated border border-border-subtle hover:border-accent/40 text-xs font-medium text-gray-200 transition-all cursor-pointer flex items-center gap-1.5"
                          >
                            {isConfigured ? (
                              'Reconfigure'
                            ) : (
                              <>
                                <Plus size={13} />
                                Connect
                              </>
                            )}
                          </button>
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

      {/* Inline Connection Modal */}
      <AnimatePresence>
        {activeConnector && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-black/80 backdrop-blur-md">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-2xl relative"
            >
              <button
                onClick={() => setActiveConnector(null)}
                className="absolute top-4 right-4 z-20 p-2 rounded-lg bg-surface hover:bg-surface-elevated text-gray-400 hover:text-white transition-colors cursor-pointer"
              >
                <X size={18} />
              </button>
              <ConnectorForm
                connector={activeConnector}
                inline
                onSuccess={() => {
                  handleConnectSuccess();
                  setActiveConnector(null);
                }}
                onDisconnect={() => {
                  handleDisconnectSuccess();
                  setActiveConnector(null);
                }}
                onCancel={() => setActiveConnector(null)}
              />
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
