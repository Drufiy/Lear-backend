import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Cloud,
  ExternalLink,
  Loader2,
  Plus,
  RotateCw,
  Trash2,
  SlidersHorizontal,
  Clock,
  CheckCircle2,
  AlertCircle,
  Search,
  RefreshCw,
  X,
} from 'lucide-react';
import { motion } from 'framer-motion';
import ConnectorForm, { ConnectorModel } from './ConnectorForm';

interface IntegrationsProps {
  onConfigureConnector?: (connectorId: string) => void;
}

function formatTimestamp(isoString?: string | null): string {
  if (!isoString) return 'Never';
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    const now = new Date();
    const isToday = d.toDateString() === now.toDateString();
    const timeStr = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    return isToday ? `Today at ${timeStr}` : `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })} at ${timeStr}`;
  } catch {
    return isoString;
  }
}

export default function Integrations({ onConfigureConnector: _onConfigureConnector }: IntegrationsProps) {
  const [connectors, setConnectors] = useState<ConnectorModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [checkingIds, setCheckingIds] = useState<Set<string>>(new Set());
  const [disconnectingId, setDisconnectingId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'configured' | 'unconfigured'>('all');
  const [quickMessages, setQuickMessages] = useState<Record<string, { type: 'success' | 'error'; text: string }>>({});

  const loadConnectors = useCallback((isManual = false) => {
    if (isManual) setRefreshing(true);
    fetch('/api/connectors')
      .then(res => res.json())
      .then(data => setConnectors(data.connectors || []))
      .catch(err => console.error('Error loading connectors:', err))
      .finally(() => {
        setLoading(false);
        if (isManual) setRefreshing(false);
      });
  }, []);

  useEffect(() => {
    loadConnectors();
  }, [loadConnectors]);

  const handleToggleExpand = (connectorId: string) => {
    setExpandedId(prev => (prev === connectorId ? null : connectorId));
    setDisconnectingId(null);
  };

  const handleCheckHealth = async (connectorId: string) => {
    setCheckingIds(prev => new Set(prev).add(connectorId));
    setQuickMessages(prev => {
      const next = { ...prev };
      delete next[connectorId];
      return next;
    });

    try {
      const res = await fetch(`/api/connectors/${connectorId}/validate`);
      const data = await res.json();
      const verifiedAt = data.last_verified || new Date().toISOString();

      setConnectors(prev =>
        prev.map(c => {
          if (c.id === connectorId) {
            return {
              ...c,
              status: data.status === 'connected' ? 'configured' : (data.status === 'expired' ? 'expired' : c.status),
              identity: data.identity || c.identity,
              last_verified: data.valid ? verifiedAt : c.last_verified,
            };
          }
          return c;
        })
      );

      if (data.valid) {
        setQuickMessages(prev => ({
          ...prev,
          [connectorId]: { type: 'success', text: data.message || 'Active & Validated' },
        }));
      } else {
        setQuickMessages(prev => ({
          ...prev,
          [connectorId]: { type: 'error', text: data.message || 'Validation failed' },
        }));
      }
    } catch (e: any) {
      setQuickMessages(prev => ({
        ...prev,
        [connectorId]: { type: 'error', text: e.message || 'Health check error' },
      }));
    } finally {
      setCheckingIds(prev => {
        const next = new Set(prev);
        next.delete(connectorId);
        return next;
      });
      setTimeout(() => {
        setQuickMessages(prev => {
          const next = { ...prev };
          delete next[connectorId];
          return next;
        });
      }, 4000);
    }
  };

  const handleDisconnect = async (connectorId: string) => {
    try {
      const res = await fetch(`/api/connectors/${connectorId}/disconnect`, {
        method: 'POST',
      });
      const data = await res.json();
      if (res.ok && data.success) {
        setDisconnectingId(null);
        setConnectors(prev =>
          prev.map(c => {
            if (c.id === connectorId) {
              return {
                ...c,
                status: 'unconfigured',
                masked_credentials: {},
                identity: null,
                last_verified: null,
              };
            }
            return c;
          })
        );
        setQuickMessages(prev => ({
          ...prev,
          [connectorId]: { type: 'success', text: 'Disconnected successfully' },
        }));
      } else {
        setQuickMessages(prev => ({
          ...prev,
          [connectorId]: { type: 'error', text: data.message || 'Failed to disconnect' },
        }));
      }
    } catch (e: any) {
      setQuickMessages(prev => ({
        ...prev,
        [connectorId]: { type: 'error', text: e.message || 'Disconnect error' },
      }));
    } finally {
      setTimeout(() => {
        setQuickMessages(prev => {
          const next = { ...prev };
          delete next[connectorId];
          return next;
        });
      }, 4000);
    }
  };

  const handleConnectSuccess = (connectorId: string, result: any) => {
    setExpandedId(null);
    setQuickMessages(prev => ({
      ...prev,
      [connectorId]: { type: 'success', text: result.message || 'Connected successfully' },
    }));
    loadConnectors();
    setTimeout(() => {
      setQuickMessages(prev => {
        const next = { ...prev };
        delete next[connectorId];
        return next;
      });
    }, 4000);
  };

  const handleDisconnectSuccess = (connectorId: string) => {
    setExpandedId(null);
    setQuickMessages(prev => ({
      ...prev,
      [connectorId]: { type: 'success', text: 'Disconnected successfully' },
    }));
    loadConnectors();
    setTimeout(() => {
      setQuickMessages(prev => {
        const next = { ...prev };
        delete next[connectorId];
        return next;
      });
    }, 4000);
  };

  // Filter connectors
  const filteredConnectors = useMemo(() => {
    return connectors.filter(c => {
      const matchesSearch =
        searchQuery.trim() === '' ||
        c.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        c.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (c.category && c.category.toLowerCase().includes(searchQuery.toLowerCase())) ||
        (c.description && c.description.toLowerCase().includes(searchQuery.toLowerCase()));

      const isConfigured = c.status === 'configured' || c.status === 'connected';
      const matchesStatus =
        statusFilter === 'all' ||
        (statusFilter === 'configured' && isConfigured) ||
        (statusFilter === 'unconfigured' && !isConfigured);

      return matchesSearch && matchesStatus;
    });
  }, [connectors, searchQuery, statusFilter]);

  const categories = useMemo(() => {
    return Array.from(new Set(filteredConnectors.map(c => c.category || 'infrastructure')));
  }, [filteredConnectors]);

  const configuredCount = useMemo(() => {
    return connectors.filter(c => c.status === 'configured' || c.status === 'connected').length;
  }, [connectors]);

  const unconfiguredCount = connectors.length - configuredCount;

  return (
    <div className="p-8 max-w-7xl mx-auto relative space-y-8">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-border-subtle">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white mb-2 flex items-center gap-3">
            Connected Integrations
            <span className="text-xs font-mono px-2.5 py-1 rounded-full bg-surface border border-border-subtle text-accent">
              {configuredCount} / {connectors.length} Active
            </span>
          </h1>
          <p className="text-sm text-gray-400">
            Manage live authentication credentials, connection health, and background watches across all {connectors.length} supported services.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => loadConnectors(true)}
            disabled={refreshing}
            className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-surface hover:bg-surface-elevated border border-border-subtle text-xs font-medium text-gray-300 hover:text-white transition-all cursor-pointer disabled:opacity-50"
            title="Refresh connection status"
          >
            <RefreshCw size={13} className={refreshing ? 'animate-spin text-accent' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {/* Filter & Search Bar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
        {/* Status Filter Tabs */}
        <div className="flex items-center p-1 rounded-xl bg-surface border border-border-subtle w-full sm:w-auto">
          <button
            onClick={() => setStatusFilter('all')}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer ${
              statusFilter === 'all'
                ? 'bg-accent text-gray-950 font-bold shadow'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            All ({connectors.length})
          </button>
          <button
            onClick={() => setStatusFilter('configured')}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer ${
              statusFilter === 'configured'
                ? 'bg-accent text-gray-950 font-bold shadow'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            Configured ({configuredCount})
          </button>
          <button
            onClick={() => setStatusFilter('unconfigured')}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer ${
              statusFilter === 'unconfigured'
                ? 'bg-accent text-gray-950 font-bold shadow'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            Unconfigured ({unconfiguredCount})
          </button>
        </div>

        {/* Search Input */}
        <div className="relative w-full sm:w-72">
          <Search size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            placeholder="Search integrations..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className="w-full bg-surface border border-border-subtle rounded-xl pl-9 pr-8 py-2 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-accent transition-colors"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-white transition-colors cursor-pointer"
            >
              <X size={12} />
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center py-24 space-y-3">
          <Loader2 className="w-8 h-8 animate-spin text-accent" />
          <span className="text-xs font-mono text-gray-400">Loading service connectors...</span>
        </div>
      ) : filteredConnectors.length === 0 ? (
        <div className="glass-card rounded-2xl p-12 text-center space-y-4">
          <Cloud size={40} className="mx-auto text-gray-600" />
          <h3 className="text-base font-bold text-white">No integrations found</h3>
          <p className="text-xs text-gray-400 max-w-sm mx-auto">
            {searchQuery
              ? `No services match your search "${searchQuery}". Try a different keyword.`
              : 'No services match the selected filter.'}
          </p>
          {(searchQuery || statusFilter !== 'all') && (
            <button
              onClick={() => {
                setSearchQuery('');
                setStatusFilter('all');
              }}
              className="px-4 py-2 rounded-xl bg-surface hover:bg-surface-elevated text-xs font-medium text-white transition-colors cursor-pointer"
            >
              Clear Filters
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-10">
          {categories.map(cat => {
            const items = filteredConnectors.filter(c => (c.category || 'infrastructure') === cat);
            if (items.length === 0) return null;

            return (
              <div key={cat} className="space-y-4">
                <h2 className="text-xs font-bold text-gray-300 uppercase tracking-wider flex items-center gap-2">
                  <span className="w-1.5 h-4 bg-accent rounded-full" />
                  {cat}
                  <span className="text-[10px] text-gray-400 font-mono font-normal">({items.length})</span>
                </h2>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 items-start">
                  {items.map(item => {
                    const isConfigured = item.status === 'configured' || item.status === 'connected';
                    const isExpired = item.status === 'expired';
                    const isChecking = checkingIds.has(item.id);
                    const isExpanded = expandedId === item.id;
                    const isDisconnecting = disconnectingId === item.id;
                    const quickMsg = quickMessages[item.id];

                    // Phase B1 & C1: Render inline expanded form
                    if (isExpanded) {
                      return (
                        <motion.div
                          key={item.id}
                          layout
                          initial={{ opacity: 0, y: -10 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, y: -10 }}
                          className="md:col-span-2 lg:col-span-3 transition-all"
                        >
                          <div className="relative">
                            <button
                              onClick={() => setExpandedId(null)}
                              className="absolute top-4 right-4 z-20 p-2 rounded-lg bg-surface hover:bg-surface-elevated text-gray-400 hover:text-white transition-colors cursor-pointer"
                              title="Collapse form"
                            >
                              <X size={16} />
                            </button>
                            <ConnectorForm
                              connector={item}
                              inline
                              onSuccess={(cid, result) => handleConnectSuccess(cid, result)}
                              onDisconnect={(cid) => handleDisconnectSuccess(cid)}
                              onCancel={() => setExpandedId(null)}
                            />
                          </div>
                        </motion.div>
                      );
                    }

                    // Collapsed Card
                    return (
                      <motion.div
                        key={item.id}
                        layout
                        className="glass-card rounded-2xl p-6 flex flex-col justify-between min-h-[240px] hover:border-accent/30 transition-all group relative"
                      >
                        <div>
                          {/* Card Header */}
                          <div className="flex justify-between items-start mb-4">
                            <div
                              className="p-3 rounded-xl border border-white/10 transition-transform group-hover:scale-105"
                              style={{ backgroundColor: `${item.color || '#FF3A89'}20` }}
                            >
                              <Cloud size={24} style={{ color: item.color || '#FF3A89' }} />
                            </div>

                            {/* Status Badge */}
                            <span
                              className={`px-3 py-1 text-xs font-semibold rounded-full border flex items-center gap-1.5 transition-colors ${
                                isChecking
                                  ? 'bg-accent/15 text-accent border-accent/30'
                                  : isConfigured
                                  ? 'bg-accent/15 text-accent border-accent/30'
                                  : isExpired
                                  ? 'bg-amber-400/15 text-amber-400 border-amber-400/30'
                                  : 'bg-surface text-gray-400 border-border-subtle'
                              }`}
                            >
                              {isChecking ? (
                                <>
                                  <Loader2 size={11} className="animate-spin text-accent" />
                                  Verifying...
                                </>
                              ) : isConfigured ? (
                                '● Configured'
                              ) : isExpired ? (
                                '▲ Expired'
                              ) : (
                                '○ Not Configured'
                              )}
                            </span>
                          </div>

                          {/* Name & Identity */}
                          <div className="flex items-center gap-2 flex-wrap">
                            <h3 className="font-bold text-base text-white">{item.name}</h3>
                            {item.identity && (
                              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-surface border border-border-subtle text-accent truncate max-w-[170px]" title={item.identity}>
                                {item.identity}
                              </span>
                            )}
                          </div>

                          <p className="text-xs text-gray-400 mt-1 line-clamp-2 leading-relaxed">{item.description}</p>

                          {/* Phase C4: Last Verified Timestamp */}
                          <div className="flex items-center gap-1.5 text-[11px] text-gray-400 font-mono mt-3.5">
                            <Clock size={11} className={item.last_verified ? 'text-accent' : 'text-gray-600'} />
                            <span>
                              {item.last_verified ? `Verified: ${formatTimestamp(item.last_verified)}` : 'Not checked this session'}
                            </span>
                          </div>

                          {/* Quick transient status message */}
                          {quickMsg && (
                            <motion.div
                              initial={{ opacity: 0, y: 5 }}
                              animate={{ opacity: 1, y: 0 }}
                              className={`text-[11px] font-mono mt-2.5 p-2 rounded-lg border flex items-center gap-1.5 ${
                                quickMsg.type === 'success'
                                  ? 'bg-accent/10 border-accent/30 text-accent'
                                  : 'bg-rose-500/10 border-rose-500/30 text-rose-400'
                              }`}
                            >
                              {quickMsg.type === 'success' ? (
                                <CheckCircle2 size={13} className="shrink-0" />
                              ) : (
                                <AlertCircle size={13} className="shrink-0" />
                              )}
                              <span className="truncate">{quickMsg.text}</span>
                            </motion.div>
                          )}

                          {/* Phase C2: Inline Disconnect Confirmation Dialog */}
                          {isDisconnecting && (
                            <motion.div
                              initial={{ opacity: 0, scale: 0.96 }}
                              animate={{ opacity: 1, scale: 1 }}
                              className="mt-3 p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 space-y-2.5"
                            >
                              <p className="text-[11px] text-rose-300 font-medium leading-tight">
                                Disconnect {item.name}? This will remove credentials and stop watches.
                              </p>
                              <div className="flex items-center gap-2">
                                <button
                                  onClick={() => handleDisconnect(item.id)}
                                  className="px-2.5 py-1 rounded bg-rose-600 hover:bg-rose-500 text-white text-[11px] font-bold transition-colors cursor-pointer"
                                >
                                  Yes, Disconnect
                                </button>
                                <button
                                  onClick={() => setDisconnectingId(null)}
                                  className="px-2.5 py-1 rounded bg-surface hover:bg-surface-elevated text-gray-300 text-[11px] transition-colors cursor-pointer"
                                >
                                  Cancel
                                </button>
                              </div>
                            </motion.div>
                          )}
                        </div>

                        {/* Bottom Actions Bar */}
                        <div className="flex items-center justify-between pt-4 mt-4 border-t border-border-subtle text-xs gap-2">
                          <div className="flex items-center gap-2.5">
                            {item.docs_url ? (
                              <a
                                href={item.docs_url}
                                target="_blank"
                                rel="noreferrer"
                                className="flex items-center gap-1 text-gray-400 hover:text-white transition-colors"
                              >
                                Docs <ExternalLink size={11} />
                              </a>
                            ) : (
                              <span />
                            )}

                            {/* Phase C3: Manual Health Check Button */}
                            {isConfigured && !isDisconnecting && (
                              <button
                                onClick={() => handleCheckHealth(item.id)}
                                disabled={isChecking}
                                className="flex items-center gap-1 text-gray-400 hover:text-accent transition-colors cursor-pointer disabled:opacity-50"
                                title="Check connection health"
                              >
                                <RotateCw size={11} className={isChecking ? 'animate-spin text-accent' : ''} />
                                <span>Check</span>
                              </button>
                            )}
                          </div>

                          <div className="flex items-center gap-2">
                            {/* Phase C2: Disconnect trigger button */}
                            {isConfigured && !isDisconnecting && (
                              <button
                                onClick={() => setDisconnectingId(item.id)}
                                className="p-1.5 rounded-lg text-gray-500 hover:text-rose-400 hover:bg-rose-500/10 transition-colors cursor-pointer"
                                title={`Disconnect ${item.name}`}
                              >
                                <Trash2 size={13} />
                              </button>
                            )}

                            {/* Phase B1 & C1: Inline Expand trigger */}
                            <button
                              onClick={() => handleToggleExpand(item.id)}
                              className="px-3 py-1.5 rounded-lg bg-surface hover:bg-surface-elevated border border-border-subtle hover:border-accent/40 text-xs font-medium text-gray-200 transition-all cursor-pointer flex items-center gap-1.5 shadow-sm"
                            >
                              {isConfigured ? (
                                <>
                                  <SlidersHorizontal size={12} />
                                  Configure
                                </>
                              ) : (
                                <>
                                  <Plus size={13} />
                                  Connect
                                </>
                              )}
                            </button>
                          </div>
                        </div>
                      </motion.div>
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
