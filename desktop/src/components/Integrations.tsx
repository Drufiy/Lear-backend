import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import {
  Activity,
  AlertCircle,
  BarChart2,
  Bell,
  Boxes,
  CheckCircle2,
  CircleHelp,
  Clock3,
  Cloud,
  CloudLightning,
  ExternalLink,
  GitBranch,
  GitCommit,
  Layers,
  Loader2,
  Lock,
  Plug,
  RefreshCw,
  Server,
  Settings2,
  Shield,
  ShieldCheck,
  Triangle,
  Unplug,
  X,
  type LucideIcon,
} from 'lucide-react';
import ConnectorForm, { type AuthField } from './ConnectorForm';

interface Connector {
  id: string;
  name: string;
  category: string;
  icon: string;
  color: string;
  description: string;
  status: string;
  docs_url?: string;
  auth_fields: AuthField[];
  last_verified?: string | null;
  last_checked?: string | null;
  error?: string | null;
  identity?: unknown;
}

interface IntegrationsProps {
  onConfigureConnector?: (connectorId: string) => void;
}

type ActionState = 'checking' | 'disconnecting' | null;
type DisplayState = 'unconfigured' | 'configured' | 'healthy' | 'connecting' | 'error';

export const registryIcons: Record<string, LucideIcon> = {
  cloud: Cloud,
  server: Server,
  'cloud-lightning': CloudLightning,
  boxes: Boxes,
  triangle: Triangle,
  'git-branch': GitBranch,
  'git-commit': GitCommit,
  activity: Activity,
  'bar-chart-2': BarChart2,
  bell: Bell,
  shield: Shield,
  lock: Lock,
  layers: Layers,
};

const healthyStatuses = new Set(['connected', 'healthy', 'watching']);
const errorStatuses = new Set(['error', 'failed', 'expired']);
const configuredStatuses = new Set(['configured', 'unverified']);

const statusDetails: Record<DisplayState, { label: string; icon: LucideIcon; className: string }> = {
  unconfigured: { label: 'Not connected', icon: Unplug, className: 'border-border-subtle bg-surface text-gray-300' },
  configured: { label: 'Configured, not verified', icon: Clock3, className: 'border-amber-500/30 bg-amber-500/10 text-amber-300' },
  healthy: { label: 'Connected', icon: CheckCircle2, className: 'border-accent/30 bg-accent/10 text-accent' },
  connecting: { label: 'Connecting', icon: Loader2, className: 'border-cyan-500/30 bg-cyan-500/10 text-cyan-300' },
  error: { label: 'Connection error', icon: AlertCircle, className: 'border-rose-500/30 bg-rose-500/10 text-rose-300' },
};

const displayState = (status: string, action: ActionState, localStatus?: string): DisplayState => {
  if (action || localStatus === 'CONNECTING') return 'connecting';
  const normalized = status.toLowerCase();
  if (normalized === 'connecting') return 'connecting';
  if (healthyStatuses.has(normalized)) return 'healthy';
  if (errorStatuses.has(normalized)) return 'error';
  if (configuredStatuses.has(normalized)) return 'configured';
  return 'unconfigured';
};

const formatVerified = (value: string) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
};

const identitySummary = (identity: unknown): string => {
  if (!identity || typeof identity !== 'object' || Array.isArray(identity)) return '';
  return Object.entries(identity as Record<string, unknown>)
    .slice(0, 6)
    .map(([key, value]) => {
      const label = key.replace(/_/g, ' ').replace(/\b\w/g, character => character.toUpperCase());
      if (value === null || value === undefined) return '';
      if (Array.isArray(value)) return `${label}: ${value.slice(0, 4).map(String).join(', ')}`;
      if (typeof value === 'object') return `${label}: ${Object.values(value as Record<string, unknown>).slice(0, 4).map(String).join(', ')}`;
      return `${label}: ${String(value)}`;
    })
    .filter(Boolean)
    .join(' · ');
};

function RegistryIcon({ name, color }: { name: string; color: string }) {
  const Icon = registryIcons[name] ?? CircleHelp;
  const resolved = registryIcons[name] ? name : 'circle-help';
  return (
    <span data-testid="connector-icon" data-icon-name={name} data-icon-resolved={resolved} className="inline-flex" style={{ color }} role="img" aria-label={`${name || 'unknown'} connector icon`}>
      <Icon size={24} aria-hidden="true" />
    </span>
  );
}

export default function Integrations({ onConfigureConnector: _onConfigureConnector }: IntegrationsProps) {
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [actions, setActions] = useState<Record<string, ActionState>>({});
  const [actionErrors, setActionErrors] = useState<Record<string, string>>({});
  const [localStatuses, setLocalStatuses] = useState<Record<string, string>>({});
  const [disconnectTarget, setDisconnectTarget] = useState<Connector | null>(null);
  const configureTriggers = useRef<Record<string, HTMLButtonElement | null>>({});

  const loadConnectors = useCallback(async (showLoading = false) => {
    if (showLoading) setLoading(true);
    setFetchError(null);
    try {
      const response = await fetch('/api/connectors');
      if (!response.ok) throw new Error(`Request failed (${response.status})`);
      const data: unknown = await response.json();
      if (!data || typeof data !== 'object' || !Array.isArray((data as { connectors?: unknown }).connectors)) {
        throw new Error('Malformed connector list response.');
      }
      setConnectors((data as { connectors: Connector[] }).connectors);
      setLocalStatuses({});
    } catch (error) {
      setFetchError(error instanceof Error ? error.message : 'Unable to load integrations.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadConnectors();
    const timer = window.setInterval(() => void loadConnectors(), 60_000);
    return () => window.clearInterval(timer);
  }, [loadConnectors]);

  const categories = useMemo(() => Array.from(new Set(connectors.map(connector => connector.category))), [connectors]);
  const connectedCount = connectors.filter(connector => healthyStatuses.has(connector.status.toLowerCase())).length;
  const handleLocalStatus = useCallback((id: string, status: string) => {
    setLocalStatuses(previous => {
      if (status === 'CONNECTING') return previous[id] === status ? previous : { ...previous, [id]: status };
      if (!(id in previous)) return previous;
      const next = { ...previous };
      delete next[id];
      return next;
    });
  }, []);

  const collapseAndRestoreFocus = (connectorId: string) => {
    setExpandedId(null);
    window.requestAnimationFrame(() => configureTriggers.current[connectorId]?.focus());
  };

  const runAction = async (connector: Connector, action: Exclude<ActionState, null>) => {
    if (actions[connector.id] || localStatuses[connector.id] === 'CONNECTING') return;
    setActions(previous => ({ ...previous, [connector.id]: action }));
    setActionErrors(previous => ({ ...previous, [connector.id]: '' }));
    try {
      const endpoint = action === 'checking' ? 'check' : 'disconnect';
      const response = await fetch(`/api/connectors/${encodeURIComponent(connector.id)}/${endpoint}`, {
        method: action === 'checking' ? 'POST' : 'DELETE',
      });
      const data = await response.json().catch(() => ({})) as { success?: boolean; error?: string; message?: string };
      if (!response.ok || !data.success) throw new Error(data.error || data.message || `${action === 'checking' ? 'Connection check' : 'Disconnect'} failed (${response.status})`);
      if (action === 'disconnecting') setExpandedId(null);
      await loadConnectors();
      setDisconnectTarget(null);
    } catch (error) {
      setActionErrors(previous => ({ ...previous, [connector.id]: error instanceof Error ? error.message : 'The request failed.' }));
      await loadConnectors();
    } finally {
      setActions(previous => ({ ...previous, [connector.id]: null }));
    }
  };

  if (loading) return (
    <div className="mx-auto max-w-7xl p-6 lg:p-8" aria-busy="true" aria-label="Loading integrations">
      <div className="mb-8 h-16 w-72 animate-pulse rounded-xl bg-surface-elevated" />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">{[0, 1, 2, 3, 4, 5].map(item => <div key={item} data-testid="integration-skeleton" className="h-56 animate-pulse rounded-2xl border border-border-subtle bg-surface" />)}</div>
    </div>
  );

  if (fetchError) return (
    <div className="mx-auto flex min-h-[60vh] max-w-xl items-center p-6">
      <div role="alert" className="w-full rounded-2xl border border-rose-500/30 bg-rose-500/10 p-6 text-rose-200">
        <AlertCircle className="mb-3" aria-hidden="true" /><h1 className="text-xl font-bold text-white">Integrations could not be loaded</h1><p className="mt-2 text-sm">{fetchError}</p>
        <button type="button" onClick={() => void loadConnectors(true)} className="mt-5 min-h-11 rounded-xl border border-rose-400/40 px-4 text-sm font-semibold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">Retry</button>
      </div>
    </div>
  );

  return (
    <Dialog.Root open={Boolean(disconnectTarget)} onOpenChange={open => { if (!open && !disconnectTarget?.id) return; if (!open && !actions[disconnectTarget?.id ?? '']) setDisconnectTarget(null); }}>
      <div className="mx-auto max-w-7xl p-6 lg:p-8">
        <header className="mb-8 flex flex-col gap-4 border-b border-border-subtle pb-6 sm:flex-row sm:items-end sm:justify-between">
          <div><p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-accent">Service connections</p><h1 className="text-3xl font-bold tracking-tight text-white">Integrations</h1><p className="mt-2 text-sm text-gray-400" aria-live="polite">{connectors.length} available · {connectedCount} connected</p></div>
          <div className="flex items-center gap-2 text-xs text-gray-400"><ShieldCheck size={16} className="text-accent" aria-hidden="true" /> Credentials are verified by each provider</div>
        </header>

        {connectors.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-border-hover bg-surface/50 px-6 py-16 text-center"><Plug className="mx-auto text-gray-500" aria-hidden="true" /><h2 className="mt-4 text-lg font-semibold text-white">No integrations available</h2><p className="mx-auto mt-2 max-w-md text-sm text-gray-400">Connector registry entries will appear here when they are available from the API.</p></div>
        ) : (
          <div className="space-y-9">
            {categories.map(category => {
              const categoryConnectors = connectors.filter(connector => connector.category === category);
              const categoryId = `category-${categoryConnectors[0]?.id}`;
              return (
                <section key={category} aria-labelledby={categoryId}>
                  <div className="mb-4 flex items-center gap-3"><h2 id={categoryId} className="text-base font-semibold text-white">{category}</h2><span className="text-xs text-gray-500">{categoryConnectors.length}</span><span className="h-px flex-1 bg-border-subtle" /></div>
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                    {categoryConnectors.map(connector => {
                      const action = actions[connector.id] ?? null;
                      const state = displayState(connector.status, action, localStatuses[connector.id]);
                      const meta = statusDetails[state];
                      const StatusIcon = meta.icon;
                      const expanded = expandedId === connector.id;
                      const connecting = state === 'connecting';
                      const reconnect = state === 'error';
                      const identity = state === 'healthy' ? identitySummary(connector.identity) : '';
                      return (
                        <article key={connector.id} data-testid="connector-card" data-connector-id={connector.id} data-connector-color={connector.color} className={`rounded-2xl border bg-surface/70 p-5 ${state === 'healthy' ? 'border-accent/35' : state === 'error' ? 'border-rose-500/35' : 'border-border-subtle'} ${expanded ? 'md:col-span-2 xl:col-span-3' : ''}`}>
                          <div className="flex items-start justify-between gap-4"><div className="flex min-w-0 items-start gap-3"><div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-white/10" style={{ backgroundColor: `${connector.color}20` }}><RegistryIcon name={connector.icon} color={connector.color} /></div><div className="min-w-0"><h3 className="font-semibold text-white">{connector.name}</h3><p className="mt-1 text-sm leading-5 text-gray-400">{connector.description}</p></div></div><span className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${meta.className}`}><StatusIcon size={13} className={connecting ? 'animate-spin' : ''} aria-hidden="true" />{meta.label}</span></div>
                          <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">{connector.name}: {meta.label}</p>
                          {(connector.error || actionErrors[connector.id]) && <p role="alert" className="mt-4 flex items-start gap-2 rounded-xl border border-rose-500/25 bg-rose-500/10 p-3 text-xs text-rose-300"><AlertCircle size={15} className="shrink-0" aria-hidden="true" />{actionErrors[connector.id] || connector.error}</p>}
                          {identity && <p className="mt-4 text-xs text-gray-300"><span className="font-semibold text-gray-200">Identity:</span> {identity}</p>}
                          {connector.last_verified && <p className="mt-2 text-xs text-gray-500">Last verified {formatVerified(connector.last_verified)}</p>}
                          <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-border-subtle pt-4">
                            {connector.docs_url && <a href={connector.docs_url} target="_blank" rel="noreferrer" className="mr-auto inline-flex min-h-11 items-center gap-1.5 rounded-lg px-2 text-xs font-medium text-gray-400 hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">Docs <ExternalLink size={13} aria-hidden="true" /></a>}
                            {state === 'unconfigured' ? <button ref={node => { configureTriggers.current[connector.id] = node; }} type="button" disabled={connecting} aria-expanded={expanded} aria-controls={`form-${connector.id}`} onClick={() => setExpandedId(expanded ? null : connector.id)} className="min-h-11 rounded-xl bg-accent px-4 text-xs font-bold text-gray-950 hover:bg-accent-light disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">Connect</button> : <>
                              <button type="button" disabled={connecting} onClick={() => void runAction(connector, 'checking')} className="inline-flex min-h-11 items-center gap-1.5 rounded-xl border border-border-subtle px-3 text-xs font-semibold text-white hover:bg-surface-elevated disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"><RefreshCw size={14} className={action === 'checking' ? 'animate-spin' : ''} aria-hidden="true" /> Check connection</button>
                              <button ref={node => { configureTriggers.current[connector.id] = node; }} type="button" aria-expanded={expanded} aria-controls={`form-${connector.id}`} disabled={connecting} onClick={() => setExpandedId(expanded ? null : connector.id)} className="inline-flex min-h-11 items-center gap-1.5 rounded-xl border border-border-subtle px-3 text-xs font-semibold text-white hover:bg-surface-elevated disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"><Settings2 size={14} aria-hidden="true" /> {reconnect ? 'Reconnect' : 'Configure'}</button>
                              <Dialog.Trigger asChild><button type="button" disabled={connecting} onClick={() => setDisconnectTarget(connector)} className="min-h-11 rounded-xl border border-rose-500/25 px-3 text-xs font-semibold text-rose-300 hover:bg-rose-500/10 disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">Disconnect</button></Dialog.Trigger>
                            </>}
                          </div>
                          {expanded && <div id={`form-${connector.id}`} className="mt-5 border-t border-border-subtle pt-5"><ConnectorForm connector={connector} initiallyEditing showManagementActions={false} disabled={connecting && localStatuses[connector.id] !== 'CONNECTING'} onStatusChange={handleLocalStatus} onConnectSuccess={async id => { await loadConnectors(); collapseAndRestoreFocus(id); }} /></div>}
                        </article>
                      );
                    })}
                  </div>
                </section>
              );
            })}
          </div>
        )}
      </div>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/70" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(92vw,28rem)] -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-border-subtle bg-surface-elevated p-6 shadow-2xl" onEscapeKeyDown={event => { if (disconnectTarget && actions[disconnectTarget.id]) event.preventDefault(); }}>
          <Dialog.Title className="text-lg font-bold text-white">Disconnect {disconnectTarget?.name}?</Dialog.Title>
          <Dialog.Description className="mt-2 text-sm leading-6 text-gray-400">Stored credentials will be removed and active watches will stop. This action can be reversed by connecting again.</Dialog.Description>
          <div className="mt-6 flex justify-end gap-3">
            <Dialog.Close asChild><button type="button" disabled={Boolean(disconnectTarget && actions[disconnectTarget.id])} className="min-h-11 rounded-xl border border-border-subtle px-4 text-sm font-semibold text-white disabled:opacity-50">Cancel</button></Dialog.Close>
            <button type="button" disabled={Boolean(disconnectTarget && actions[disconnectTarget.id])} onClick={() => disconnectTarget && void runAction(disconnectTarget, 'disconnecting')} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-rose-600 px-4 text-sm font-bold text-white hover:bg-rose-500 disabled:opacity-50">{disconnectTarget && actions[disconnectTarget.id] === 'disconnecting' && <Loader2 size={16} className="animate-spin" aria-hidden="true" />}Disconnect</button>
          </div>
          <Dialog.Close asChild><button type="button" disabled={Boolean(disconnectTarget && actions[disconnectTarget.id])} className="absolute right-4 top-4 rounded-lg p-2 text-gray-400 hover:text-white disabled:opacity-50" aria-label="Close disconnect dialog"><X size={18} aria-hidden="true" /></button></Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
