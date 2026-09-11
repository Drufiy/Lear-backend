import { useEffect, useRef, useState } from 'react';
import { AlertCircle, CheckCircle2, Loader2 } from 'lucide-react';
import { useConnectorStatus } from '../hooks/useConnectorStatus';

export interface AuthField {
  key: string;
  label: string;
  type: string;
  required: boolean;
  default?: string;
  placeholder?: string;
  help_text?: string;
  value?: string;
  masked_value?: string;
  configured?: boolean;
  status?: string;
  options?: Array<string | { value: string; label: string }>;
}

export interface ConnectorDefinition {
  id: string;
  name: string;
  status: string;
  auth_fields: AuthField[];
}

interface ConnectorFormProps {
  connector: ConnectorDefinition;
  onStatusChange?: (connectorId: string, status: string) => void;
  onConnectSuccess?: (connectorId: string) => void | Promise<void>;
  initiallyEditing?: boolean;
  showManagementActions?: boolean;
  disabled?: boolean;
}

const identityText = (identity: unknown): string => {
  if (identity === null || identity === undefined) return '';
  if (typeof identity === 'string' || typeof identity === 'number' || typeof identity === 'boolean') return String(identity);
  if (Array.isArray(identity)) return identity.map(identityText).filter(Boolean).join(', ');
  if (typeof identity === 'object') {
    return Object.entries(identity as Record<string, unknown>)
      .map(([key, value]) => `${key.replace(/_/g, ' ')}: ${identityText(value)}`)
      .join(' · ');
  }
  return '';
};

const existingValue = (field: AuthField) => field.masked_value ?? field.value ?? field.default ?? '';
const hasMaskedValue = (field: AuthField) => Boolean(field.masked_value || field.configured || field.status === 'configured');

export default function ConnectorForm({
  connector,
  onStatusChange,
  onConnectSuccess,
  initiallyEditing,
  showManagementActions = true,
  disabled: externallyDisabled = false,
}: ConnectorFormProps) {
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState(initiallyEditing ?? connector.status === 'unconfigured');
  const [locallyDisconnected, setLocallyDisconnected] = useState(false);
  const firstFieldRef = useRef<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement | null>(null);
  const { state, identity, error, lastVerified, expired, connect, disconnect, check } = useConnectorStatus(connector.id, connector.status);
  const busy = state === 'CONNECTING' || externallyDisabled;
  const connected = state === 'CONNECTED' || state === 'WATCHING';
  const fieldConfigured = (field: AuthField) => !locallyDisconnected && hasMaskedValue(field);
  const configured = connected || (!locallyDisconnected && connector.auth_fields.some(hasMaskedValue));

  useEffect(() => {
    setCredentials(Object.fromEntries(connector.auth_fields.map(field => [field.key, existingValue(field)])));
    setEditing(initiallyEditing ?? connector.status === 'unconfigured');
    setLocallyDisconnected(false);
  }, [connector, initiallyEditing]);

  useEffect(() => {
    onStatusChange?.(connector.id, state);
  }, [connector.id, onStatusChange, state]);

  useEffect(() => {
    if (editing && !busy) firstFieldRef.current?.focus();
  }, [busy, editing]);

  const submitCredentials = Object.fromEntries(
    connector.auth_fields
      .filter(field => !fieldConfigured(field) || credentials[field.key] !== existingValue(field))
      .map(field => [field.key, credentials[field.key] ?? '']),
  );

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    if (await connect(submitCredentials)) {
      setEditing(false);
      await onConnectSuccess?.(connector.id);
    }
  };

  const handleDisconnect = async () => {
    if (await disconnect()) {
      setLocallyDisconnected(true);
      setCredentials(Object.fromEntries(connector.auth_fields.map(field => [field.key, field.default ?? ''])));
      setEditing(true);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="space-y-4">
        {connector.auth_fields.map(field => {
          const options = field.options ?? [];
          const value = credentials[field.key] ?? '';
          const disabled = busy || (configured && !editing);
          return (
            <div key={field.key} className="space-y-1.5">
              <label htmlFor={`${connector.id}-${field.key}`} className="text-xs font-medium text-gray-300 flex items-center gap-1">
                {field.label}
                {field.required && <span className="text-rose-400">*</span>}
              </label>
              {options.length > 0 ? (
                <select
                  id={`${connector.id}-${field.key}`}
                  ref={field === connector.auth_fields[0] ? firstFieldRef as React.Ref<HTMLSelectElement> : undefined}
                  required={field.required && !fieldConfigured(field)}
                  disabled={disabled}
                  value={value}
                  onChange={event => setCredentials(previous => ({ ...previous, [field.key]: event.target.value }))}
                  className="w-full bg-surface border border-border-subtle focus:border-accent rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none transition-all disabled:opacity-60"
                >
                  <option value="">Select {field.label}</option>
                  {options.map(option => {
                    const optionValue = typeof option === 'string' ? option : option.value;
                    const label = typeof option === 'string' ? option : option.label;
                    return <option key={optionValue} value={optionValue}>{label}</option>;
                  })}
                </select>
              ) : field.type === 'textarea' ? (
                <textarea
                  id={`${connector.id}-${field.key}`}
                  ref={field === connector.auth_fields[0] ? firstFieldRef as React.Ref<HTMLTextAreaElement> : undefined}
                  required={field.required && !fieldConfigured(field)}
                  disabled={disabled}
                  placeholder={field.placeholder || `Enter ${field.label}`}
                  value={value}
                  onFocus={() => {
                    if (editing && hasMaskedValue(field) && value === existingValue(field)) setCredentials(previous => ({ ...previous, [field.key]: '' }));
                  }}
                  onChange={event => setCredentials(previous => ({ ...previous, [field.key]: event.target.value }))}
                  className="w-full min-h-28 bg-surface border border-border-subtle focus:border-accent rounded-xl px-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none transition-all font-mono disabled:opacity-60"
                />
              ) : (
                <input
                  id={`${connector.id}-${field.key}`}
                  ref={field === connector.auth_fields[0] ? firstFieldRef as React.Ref<HTMLInputElement> : undefined}
                  type={field.type === 'password' || hasMaskedValue(field) ? 'password' : 'text'}
                  required={field.required && !fieldConfigured(field)}
                  disabled={disabled}
                  placeholder={field.placeholder || `Enter ${field.label}`}
                  value={value}
                  onFocus={() => {
                    if (editing && hasMaskedValue(field) && value === existingValue(field)) {
                      setCredentials(previous => ({ ...previous, [field.key]: '' }));
                    }
                  }}
                  onChange={event => setCredentials(previous => ({ ...previous, [field.key]: event.target.value }))}
                  className="w-full bg-surface border border-border-subtle focus:border-accent rounded-xl px-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none transition-all font-mono disabled:opacity-60"
                />
              )}
              {field.help_text && <p className="text-[11px] text-gray-500">{field.help_text}</p>}
            </div>
          );
        })}
      </div>

      {connected && (
        <div role="status" className="p-3.5 rounded-xl text-xs flex items-start gap-2 border bg-accent/10 border-accent/30 text-accent shadow-[0_0_18px_rgba(16,185,129,0.08)]">
          <CheckCircle2 size={16} className="shrink-0" />
          <div>
            <p className="font-semibold">Connected{identityText(identity) ? ` · ${identityText(identity)}` : ''}</p>
            {lastVerified && <p className="mt-1 text-gray-400">Last verified {lastVerified}</p>}
          </div>
        </div>
      )}

      {state === 'FAILED' && error && (
        <div role="alert" className="p-3.5 rounded-xl text-xs flex items-start gap-2 border bg-rose-500/10 border-rose-500/30 text-rose-400">
          <AlertCircle size={16} className="shrink-0" />
          <div>
            <p>{error}</p>
            {expired && <p className="mt-1 font-semibold">Credentials expired. Reconnect with updated credentials.</p>}
          </div>
        </div>
      )}

      <div className="flex items-center gap-3 pt-6 border-t border-border-subtle">
        {configured && !editing ? (
          <button type="button" onClick={() => setEditing(true)} disabled={busy} className="px-5 py-2.5 rounded-xl bg-accent hover:bg-accent-light text-gray-950 font-bold text-xs transition-all disabled:opacity-50">
            {expired || state === 'FAILED' ? 'Reconnect' : 'Update credentials'}
          </button>
        ) : (
          <button type="submit" disabled={busy} className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-accent hover:bg-accent-light text-gray-950 font-bold text-xs transition-all shadow-lg disabled:opacity-50">
            {busy && <Loader2 size={16} className="animate-spin" />}
            {busy ? 'Authenticating...' : configured ? 'Reconnect' : 'Validate & Save Credentials'}
          </button>
        )}
        {showManagementActions && configured && !connected && (
          <button type="button" onClick={() => void check()} disabled={busy} className="px-5 py-2.5 rounded-xl bg-surface hover:bg-surface-elevated border border-border-subtle text-xs font-semibold text-white transition-all disabled:opacity-50">
            Check connection
          </button>
        )}
        {showManagementActions && configured && (
          <button type="button" onClick={handleDisconnect} disabled={busy} className="px-5 py-2.5 rounded-xl bg-surface hover:bg-surface-elevated border border-border-subtle text-xs font-semibold text-rose-400 transition-all disabled:opacity-50">
            Disconnect
          </button>
        )}
      </div>
    </form>
  );
}
