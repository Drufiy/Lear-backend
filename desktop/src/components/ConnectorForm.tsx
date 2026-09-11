import React, { useState } from 'react';
import {
  Cloud,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Eye,
  EyeOff,
  Trash2,
  RotateCw,
  HelpCircle,
  KeyRound
} from 'lucide-react';
import { useConnectorStatus } from '../hooks/useConnectorStatus';

export interface AuthField {
  key: string;
  label: string;
  type: string;
  required: boolean;
  default?: string;
  placeholder?: string;
  help_text?: string;
}

export interface ConnectorModel {
  id: string;
  name: string;
  category?: string;
  icon?: string;
  color: string;
  description: string;
  status: 'configured' | 'unconfigured' | string;
  auth_fields: AuthField[];
  masked_credentials?: Record<string, string>;
}

interface ConnectorFormProps {
  connector: ConnectorModel;
  onSuccess?: (connectorId: string, result: any) => void;
  onCancel?: () => void;
  onDisconnect?: (connectorId: string) => void;
  inline?: boolean;
}

export const ConnectorForm: React.FC<ConnectorFormProps> = ({
  connector,
  onSuccess,
  onCancel,
  onDisconnect,
  inline = false,
}) => {
  const {
    status,
    identity,
    maskedCredentials,
    loading,
    error,
    connect,
    disconnect,
    checkHealth,
  } = useConnectorStatus(connector.id, connector.status);

  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [showSecrets, setShowSecrets] = useState<Record<string, boolean>>({});
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);
  const [feedback, setFeedback] = useState<{ success: boolean; message: string } | null>(null);

  const handleInputChange = (key: string, value: string) => {
    setFormValues(prev => ({ ...prev, [key]: value }));
  };

  const toggleShowSecret = (key: string) => {
    setShowSecrets(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFeedback(null);

    // Collect values (fallback to defaults if specified and field empty)
    const payload: Record<string, string> = {};
    connector.auth_fields.forEach(field => {
      if (formValues[field.key]) {
        payload[field.key] = formValues[field.key];
      } else if (field.default && !maskedCredentials[field.key]) {
        payload[field.key] = field.default;
      }
    });

    const result = await connect(payload);
    if (result.success) {
      setFeedback({ success: true, message: result.message });
      setFormValues({});
      if (onSuccess) {
        onSuccess(connector.id, result);
      }
    } else {
      setFeedback({ success: false, message: result.message });
    }
  };

  const handleDisconnect = async () => {
    const res = await disconnect();
    setConfirmDisconnect(false);
    if (res.success) {
      setFeedback({ success: true, message: res.message });
      setFormValues({});
      if (onDisconnect) {
        onDisconnect(connector.id);
      }
    } else {
      setFeedback({ success: false, message: res.message });
    }
  };

  const isConfigured = status === 'connected';

  return (
    <div className={`flex flex-col justify-between ${inline ? 'p-6' : 'p-8'} glass-card rounded-2xl`}>
      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Header Bar */}
        <div className="flex items-center justify-between pb-4 border-b border-border-subtle">
          <div className="flex items-center gap-3">
            <div
              className="p-3 rounded-xl border border-white/10"
              style={{ backgroundColor: `${connector.color || '#FF3A89'}20` }}
            >
              <Cloud size={24} style={{ color: connector.color || '#FF3A89' }} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold text-white">{connector.name}</h2>
                {identity && (
                  <span className="text-xs font-mono px-2 py-0.5 rounded bg-surface border border-border-subtle text-accent">
                    {identity}
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-400 mt-0.5">{connector.description}</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {isConfigured && (
              <button
                type="button"
                onClick={() => checkHealth()}
                className="p-2 rounded-lg bg-surface hover:bg-surface-elevated border border-border-subtle text-gray-400 hover:text-white transition-colors cursor-pointer"
                title="Verify connection liveness"
              >
                <RotateCw size={14} className={loading ? 'animate-spin text-accent' : ''} />
              </button>
            )}

            <span
              className={`text-xs px-2.5 py-1 rounded-full font-medium border ${
                status === 'connected'
                  ? 'bg-accent/15 text-accent border-accent/30'
                  : status === 'expired'
                  ? 'bg-amber-400/15 text-amber-400 border-amber-400/30'
                  : 'bg-surface text-gray-400 border-border-subtle'
              }`}
            >
              {status === 'connected'
                ? '● Connected'
                : status === 'expired'
                ? '▲ Expired'
                : '○ Not Configured'}
            </span>
          </div>
        </div>

        {/* Dynamic Auth Fields Form */}
        <div className="space-y-4">
          {connector.auth_fields.map(field => {
            const isSecret = field.type === 'password' || field.key.toLowerCase().includes('secret') || field.key.toLowerCase().includes('token');
            const isVisible = showSecrets[field.key] || false;
            const hasMasked = Boolean(maskedCredentials[field.key]);

            return (
              <div key={field.key} className="space-y-1.5">
                <div className="flex justify-between items-center text-xs">
                  <label className="font-medium text-gray-300 flex items-center gap-1">
                    {field.label}
                    {field.required && !hasMasked && <span className="text-rose-400">*</span>}
                  </label>

                  {hasMasked && (
                    <span className="text-[11px] font-mono text-gray-400 flex items-center gap-1">
                      <KeyRound size={11} className="text-accent" />
                      Active: {maskedCredentials[field.key]}
                    </span>
                  )}
                </div>

                <div className="relative flex items-center">
                  <input
                    type={isSecret && !isVisible ? 'password' : 'text'}
                    placeholder={
                      hasMasked
                        ? '•••••••••••• (Leave blank to keep active credential)'
                        : field.placeholder || (field.default ? `Default: ${field.default}` : `Enter ${field.label}`)
                    }
                    value={formValues[field.key] || ''}
                    disabled={loading}
                    onChange={e => handleInputChange(field.key, e.target.value)}
                    className="w-full bg-surface border border-border-subtle focus:border-accent rounded-xl px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none transition-all font-mono pr-10 disabled:opacity-50"
                  />

                  {isSecret && (
                    <button
                      type="button"
                      onClick={() => toggleShowSecret(field.key)}
                      className="absolute right-3 text-gray-500 hover:text-white transition-colors cursor-pointer"
                      tabIndex={-1}
                    >
                      {isVisible ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                  )}
                </div>

                {field.help_text && (
                  <p className="text-[11px] text-gray-500 flex items-center gap-1">
                    <HelpCircle size={11} className="shrink-0" />
                    {field.help_text}
                  </p>
                )}
              </div>
            );
          })}
        </div>

        {/* Feedback Messages */}
        {(feedback || error) && (
          <div
            className={`p-3.5 rounded-xl text-xs flex items-start gap-2.5 border ${
              (feedback?.success ?? !error)
                ? 'bg-accent/10 border-accent/30 text-accent'
                : 'bg-rose-500/10 border-rose-500/30 text-rose-400'
            }`}
          >
            {(feedback?.success ?? !error) ? (
              <CheckCircle2 size={16} className="shrink-0 mt-0.5" />
            ) : (
              <AlertCircle size={16} className="shrink-0 mt-0.5" />
            )}
            <div className="flex-1">
              <span className="font-semibold block">
                {(feedback?.success ?? !error) ? 'Authenticated' : 'Connection Error'}
              </span>
              <span className="text-[11px] mt-0.5 block">
                {feedback?.message || error}
              </span>
            </div>
          </div>
        )}

        {/* Disconnect Confirmation Alert */}
        {confirmDisconnect && (
          <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 space-y-3">
            <div className="flex items-center gap-2 text-rose-300 text-xs font-semibold">
              <AlertCircle size={16} />
              Are you sure you want to disconnect {connector.name}?
            </div>
            <p className="text-xs text-gray-400">
              This will remove all saved credentials from the local configuration and stop any background monitoring watches for this service.
            </p>
            <div className="flex items-center gap-3 pt-1">
              <button
                type="button"
                onClick={handleDisconnect}
                disabled={loading}
                className="px-3.5 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold transition-all cursor-pointer"
              >
                {loading ? 'Disconnecting...' : 'Yes, Disconnect Service'}
              </button>
              <button
                type="button"
                onClick={() => setConfirmDisconnect(false)}
                className="px-3 py-1.5 rounded-lg bg-surface hover:bg-surface-elevated text-gray-300 text-xs transition-all cursor-pointer"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Bottom Actions Bar */}
        <div className="flex items-center justify-between pt-6 border-t border-border-subtle">
          <div className="flex items-center gap-2">
            {isConfigured && !confirmDisconnect && (
              <button
                type="button"
                onClick={() => setConfirmDisconnect(true)}
                className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-rose-400 hover:text-rose-300 hover:bg-rose-500/10 transition-colors text-xs font-medium cursor-pointer"
              >
                <Trash2 size={14} />
                Disconnect
              </button>
            )}
          </div>

          <div className="flex items-center gap-3">
            {onCancel && (
              <button
                type="button"
                onClick={onCancel}
                className="px-4 py-2 rounded-xl bg-surface hover:bg-surface-elevated text-gray-400 hover:text-white text-xs font-medium transition-all cursor-pointer"
              >
                Cancel
              </button>
            )}

            <button
              type="submit"
              disabled={loading}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-accent hover:bg-accent-light text-gray-950 font-bold text-xs transition-all shadow-lg cursor-pointer disabled:opacity-50"
            >
              {loading && <Loader2 size={15} className="animate-spin" />}
              {loading
                ? 'Validating Credentials...'
                : isConfigured
                ? 'Update & Re-verify'
                : 'Validate & Connect'}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
};

export default ConnectorForm;
