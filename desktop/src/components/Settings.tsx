import { useState, useEffect } from 'react';
import {
  Shield,
  Cpu,
  Save,
  Clock,
  Key,
  Bell,
  Info,
  CheckCircle2,
  AlertTriangle,
  Search,
  ExternalLink,
  Sparkles,
} from 'lucide-react';
import { useLear } from '../context/LearContext';

export interface ModelOption {
  id: string;
  name: string;
  desc: string;
  provider?: string;
}

export interface PermissionModeOption {
  id: string;
  label: string;
  desc: string;
}

export interface SystemVersionInfo {
  version: string;
  name: string;
  engine?: string;
  status: string;
  platform?: string;
  python_version?: string;
  connectors_total: number;
  connectors_configured: number;
}

export default function Settings({ onReconfigure }: { onReconfigure?: () => void }) {
  const { setActiveTab } = useLear();

  // Settings State
  const [model, setModel] = useState('deepseek-v4-flash');
  const [availableModels, setAvailableModels] = useState<ModelOption[]>([]);
  const [permissionMode, setPermissionMode] = useState('ask');
  const [availablePermissionModes, setAvailablePermissionModes] = useState<PermissionModeOption[]>([]);

  // Watcher Settings State
  const [pollInterval, setPollInterval] = useState(15);
  const [retentionDays, setRetentionDays] = useState(30);
  const [desktopNotifications, setDesktopNotifications] = useState(true);
  const [alertOnDegraded, setAlertOnDegraded] = useState(true);

  // Webhooks State
  const [slackWebhook, setSlackWebhook] = useState('');
  const [discordWebhook, setDiscordWebhook] = useState('');
  const [pagerdutyKey, setPagerdutyKey] = useState('');

  // Credentials & Config Overview State
  const [maskedEnv, setMaskedEnv] = useState<Record<string, string>>({});
  const [credentialQuery, setCredentialQuery] = useState('');

  // System Version & About State
  const [systemInfo, setSystemInfo] = useState<SystemVersionInfo | null>(null);

  // Loading & UI States
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch initial settings, config, and system info
  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const [resSettings, resConfig, resVersion] = await Promise.all([
          fetch('/api/settings').then(r => r.json()).catch(() => null),
          fetch('/api/config').then(r => r.json()).catch(() => null),
          fetch('/api/system/version').then(r => r.json()).catch(() => null),
        ]);

        if (resSettings) {
          if (resSettings.model) setModel(resSettings.model);
          if (Array.isArray(resSettings.available_models)) setAvailableModels(resSettings.available_models);
          if (resSettings.permission_mode) setPermissionMode(resSettings.permission_mode);
          if (Array.isArray(resSettings.available_permission_modes)) setAvailablePermissionModes(resSettings.available_permission_modes);
          if (typeof resSettings.poll_interval === 'number') setPollInterval(resSettings.poll_interval);
          if (typeof resSettings.retention_days === 'number') setRetentionDays(resSettings.retention_days);
          if (typeof resSettings.desktop_notifications === 'boolean') setDesktopNotifications(resSettings.desktop_notifications);
          if (typeof resSettings.alert_on_degraded === 'boolean') setAlertOnDegraded(resSettings.alert_on_degraded);
          if (resSettings.slack_webhook) setSlackWebhook(resSettings.slack_webhook);
          if (resSettings.discord_webhook) setDiscordWebhook(resSettings.discord_webhook);
          if (resSettings.pagerduty_key) setPagerdutyKey(resSettings.pagerduty_key);
        }

        if (resConfig && resConfig.raw) {
          setMaskedEnv(resConfig.raw);
        }

        if (resVersion) {
          setSystemInfo(resVersion);
        }
      } catch (err: any) {
        console.error('Failed to load settings data:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const payload = {
        model,
        permission_mode: permissionMode,
        poll_interval: Number(pollInterval),
        retention_days: Number(retentionDays),
        desktop_notifications: desktopNotifications,
        alert_on_degraded: alertOnDegraded,
        slack_webhook: slackWebhook,
        discord_webhook: discordWebhook,
        pagerduty_key: pagerdutyKey,
      };

      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        setSaved(true);
        setTimeout(() => setSaved(false), 3500);
      } else {
        const errData = await res.json().catch(() => ({}));
        setError(errData.message || errData.detail || 'Failed to persist settings.');
      }
    } catch (e: any) {
      setError(e?.message || 'Error saving settings.');
    } finally {
      setSaving(false);
    }
  };

  // Filter masked credentials by search query
  const filteredCredentials = Object.entries(maskedEnv).filter(([key, val]) => {
    if (!credentialQuery) return true;
    const q = credentialQuery.toLowerCase();
    return key.toLowerCase().includes(q) || val.toLowerCase().includes(q);
  });

  return (
    <div className="p-8 max-w-5xl mx-auto space-y-8 pb-24">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white mb-2 flex items-center gap-3">
            Platform Settings
          </h1>
          <p className="text-sm text-gray-400">
            Configure AI reasoning models, permission scopes, background watcher cadence, and alerting.
          </p>
        </div>

        {/* Global Save Button in Header */}
        <div className="flex items-center gap-3">
          {saved && (
            <span className="flex items-center gap-1.5 text-xs text-emerald-400 font-medium animate-fade-in">
              <CheckCircle2 size={14} />
              Preferences Saved
            </span>
          )}
          {error && (
            <span className="flex items-center gap-1.5 text-xs text-rose-400 font-medium">
              <AlertTriangle size={14} />
              {error}
            </span>
          )}
          <button
            onClick={handleSave}
            disabled={saving || loading}
            className="flex items-center gap-2 px-5 py-2.5 bg-accent hover:bg-accent-light text-gray-950 font-bold text-xs rounded-xl shadow-lg transition-all cursor-pointer disabled:opacity-50"
          >
            {saving ? (
              <>
                <div className="w-3.5 h-3.5 rounded-full border-2 border-gray-950 border-t-transparent animate-spin" />
                <span>Saving...</span>
              </>
            ) : (
              <>
                <Save size={15} />
                <span>{saved ? 'Saved!' : 'Save Settings'}</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Infrastructure Setup Wizard Card */}
      <div className="glass-card rounded-2xl p-6 flex items-center justify-between border border-border-subtle hover:border-border transition-all">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-accent/10 border border-accent/20 flex items-center justify-center text-accent">
            <Sparkles size={20} />
          </div>
          <div>
            <h3 className="font-bold text-sm text-white">Infrastructure Setup Wizard</h3>
            <p className="text-xs text-gray-400 mt-0.5">
              Launch the step-by-step interactive wizard to connect new cloud providers or update credentials.
            </p>
          </div>
        </div>
        {onReconfigure && (
          <button
            onClick={onReconfigure}
            className="px-4 py-2 bg-surface-elevated hover:bg-surface-elevated/80 border border-border text-white hover:text-accent font-bold text-xs rounded-xl transition-all cursor-pointer shadow flex items-center gap-2"
          >
            <span>Launch Wizard</span>
            <ExternalLink size={13} />
          </button>
        )}
      </div>

      {/* A2. Model Provider Section */}
      <section className="glass-card rounded-2xl p-6 space-y-4 border border-border-subtle">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <Cpu size={18} className="text-accent" />
            AI Diagnosis & Model Provider
          </h2>
          <span className="text-[11px] font-mono text-gray-400 bg-surface px-2.5 py-1 rounded-lg border border-border-subtle">
            Active: {model}
          </span>
        </div>
        <p className="text-xs text-gray-400">
          Select the large language model that powers Lear Copilot, automated incident root-cause diagnosis, and widget synthesis.
        </p>

        {loading && availableModels.length === 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2">
            {[1, 2, 3].map(i => (
              <div key={i} className="p-4 rounded-xl border border-border-subtle bg-surface animate-pulse h-24" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 pt-2">
            {availableModels.map(m => {
              const isSelected = model === m.id;
              return (
                <button
                  key={m.id}
                  onClick={() => setModel(m.id)}
                  className={`p-4 rounded-xl text-left border transition-all cursor-pointer flex flex-col justify-between ${
                    isSelected
                      ? 'bg-accent/15 border-accent text-white shadow-sm ring-1 ring-accent/30'
                      : 'bg-surface border-border-subtle text-gray-400 hover:text-white hover:border-border hover:bg-surface-elevated/40'
                  }`}
                >
                  <div>
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <span className="font-bold text-xs text-white">{m.name}</span>
                      {m.provider && (
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded-md bg-surface-elevated text-gray-300 border border-border-subtle">
                          {m.provider}
                        </span>
                      )}
                    </div>
                    <span className="text-[11px] text-gray-400 leading-relaxed block">{m.desc}</span>
                  </div>
                  <div className="mt-3 flex items-center justify-between text-[10px]">
                    <span className="font-mono text-gray-500">{m.id}</span>
                    {isSelected && (
                      <span className="text-accent font-bold flex items-center gap-1">
                        ● Active
                      </span>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </section>

      {/* Permission Mode Section */}
      <section className="glass-card rounded-2xl p-6 space-y-4 border border-border-subtle">
        <h2 className="text-base font-bold text-white flex items-center gap-2">
          <Shield size={18} className="text-accent" />
          Permission & Execution Safety
        </h2>
        <p className="text-xs text-gray-400">
          Controls whether Lear can execute operational actions automatically or requires explicit confirmation for cloud resources.
        </p>

        <div className="space-y-3 pt-2">
          {(availablePermissionModes.length > 0
            ? availablePermissionModes
            : [
                { id: 'ask', label: 'Ask First (Recommended)', desc: 'Always request user confirmation before modifying cloud resources.' },
                { id: 'auto-safe', label: 'Auto-Safe Tier', desc: 'Execute read-only and safe diagnostics automatically; ask for write actions.' },
                { id: 'bypass', label: 'Bypass (Autonomous)', desc: 'Allow autonomous remediation for verified health degradation.' },
              ]
          ).map(p => {
            const isSelected = permissionMode === p.id;
            return (
              <label
                key={p.id}
                className={`flex items-start gap-3.5 p-3.5 rounded-xl border cursor-pointer transition-all ${
                  isSelected
                    ? 'bg-surface-elevated border-accent/50 text-white ring-1 ring-accent/20'
                    : 'bg-surface border-border-subtle text-gray-400 hover:text-white hover:border-border hover:bg-surface-elevated/30'
                }`}
              >
                <input
                  type="radio"
                  name="permission"
                  checked={isSelected}
                  onChange={() => setPermissionMode(p.id)}
                  className="mt-1 accent-[#ff3a89]"
                />
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-xs text-white">{p.label}</span>
                    {p.id === 'ask' && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent/20 text-accent font-semibold">
                        Default
                      </span>
                    )}
                  </div>
                  <span className="text-[11px] text-gray-400 mt-0.5 block">{p.desc}</span>
                </div>
              </label>
            );
          })}
        </div>
      </section>

      {/* A3. Watcher Settings Section */}
      <section className="glass-card rounded-2xl p-6 space-y-6 border border-border-subtle">
        <h2 className="text-base font-bold text-white flex items-center gap-2">
          <Clock size={18} className="text-accent" />
          Watcher & Monitoring Cadence
        </h2>
        <p className="text-xs text-gray-400">
          Configure real-time background watcher polling intervals, event retention periods, and alert thresholds.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2">
          {/* Poll Interval Selector */}
          <div className="space-y-2">
            <label className="text-xs font-bold text-gray-300 block">
              Background Polling Cadence
            </label>
            <p className="text-[11px] text-gray-400 mb-2">
              Frequency for background health checks and state polling on watched targets.
            </p>
            <div className="grid grid-cols-5 gap-2">
              {[5, 10, 15, 30, 60].map(sec => (
                <button
                  key={sec}
                  type="button"
                  onClick={() => setPollInterval(sec)}
                  className={`py-2 text-xs font-bold rounded-lg border transition-all cursor-pointer ${
                    pollInterval === sec
                      ? 'bg-accent text-gray-950 border-accent shadow-sm'
                      : 'bg-surface border-border-subtle text-gray-400 hover:text-white hover:border-border'
                  }`}
                >
                  {sec}s
                </button>
              ))}
            </div>
          </div>

          {/* Retention Period Selector */}
          <div className="space-y-2">
            <label className="text-xs font-bold text-gray-300 block">
              Event Retention History
            </label>
            <p className="text-[11px] text-gray-400 mb-2">
              How long audit log events and operational telemetry remain stored locally.
            </p>
            <div className="grid grid-cols-4 gap-2">
              {[7, 14, 30, 90].map(days => (
                <button
                  key={days}
                  type="button"
                  onClick={() => setRetentionDays(days)}
                  className={`py-2 text-xs font-bold rounded-lg border transition-all cursor-pointer ${
                    retentionDays === days
                      ? 'bg-accent text-gray-950 border-accent shadow-sm'
                      : 'bg-surface border-border-subtle text-gray-400 hover:text-white hover:border-border'
                  }`}
                >
                  {days}d
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Notification Toggles */}
        <div className="pt-2 border-t border-border-subtle space-y-3">
          <div className="flex items-center justify-between p-3.5 rounded-xl bg-surface border border-border-subtle">
            <div>
              <span className="font-bold text-xs text-white block">Desktop OS Notifications</span>
              <span className="text-[11px] text-gray-400 mt-0.5 block">
                Deliver native desktop banner alerts when monitored service health changes.
              </span>
            </div>
            <button
              type="button"
              onClick={() => setDesktopNotifications(!desktopNotifications)}
              className={`w-11 h-6 rounded-full transition-colors relative cursor-pointer ${
                desktopNotifications ? 'bg-accent' : 'bg-gray-700'
              }`}
            >
              <div
                className={`w-4 h-4 rounded-full bg-gray-950 absolute top-1 transition-transform ${
                  desktopNotifications ? 'left-6' : 'left-1'
                }`}
              />
            </button>
          </div>

          <div className="flex items-center justify-between p-3.5 rounded-xl bg-surface border border-border-subtle">
            <div>
              <span className="font-bold text-xs text-white block">Alert on Degraded / Error States Only</span>
              <span className="text-[11px] text-gray-400 mt-0.5 block">
                Suppress notifications for routine operational updates; only notify when intervention is required.
              </span>
            </div>
            <button
              type="button"
              onClick={() => setAlertOnDegraded(!alertOnDegraded)}
              className={`w-11 h-6 rounded-full transition-colors relative cursor-pointer ${
                alertOnDegraded ? 'bg-accent' : 'bg-gray-700'
              }`}
            >
              <div
                className={`w-4 h-4 rounded-full bg-gray-950 absolute top-1 transition-transform ${
                  alertOnDegraded ? 'left-6' : 'left-1'
                }`}
              />
            </button>
          </div>
        </div>
      </section>

      {/* Alerting & Webhook Channels */}
      <section className="glass-card rounded-2xl p-6 space-y-4 border border-border-subtle">
        <h2 className="text-base font-bold text-white flex items-center gap-2">
          <Bell size={18} className="text-accent" />
          Alerting & Incident Forwarding
        </h2>
        <p className="text-xs text-gray-400">
          Forward critical incidents and automated remediation summaries to external notification channels.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
          <div className="space-y-1.5">
            <label className="text-xs font-bold text-gray-300 block">Slack Webhook URL</label>
            <input
              type="password"
              value={slackWebhook}
              onChange={e => setSlackWebhook(e.target.value)}
              placeholder="https://hooks.slack.com/services/..."
              className="w-full bg-surface border border-border-subtle rounded-xl px-3 py-2 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-accent font-mono"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-bold text-gray-300 block">Discord Webhook URL</label>
            <input
              type="password"
              value={discordWebhook}
              onChange={e => setDiscordWebhook(e.target.value)}
              placeholder="https://discord.com/api/webhooks/..."
              className="w-full bg-surface border border-border-subtle rounded-xl px-3 py-2 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-accent font-mono"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-bold text-gray-300 block">PagerDuty Routing Key</label>
            <input
              type="password"
              value={pagerdutyKey}
              onChange={e => setPagerdutyKey(e.target.value)}
              placeholder="pd-routing-key..."
              className="w-full bg-surface border border-border-subtle rounded-xl px-3 py-2 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-accent font-mono"
            />
          </div>
        </div>
      </section>

      {/* A4. Credential Overview Section */}
      <section className="glass-card rounded-2xl p-6 space-y-4 border border-border-subtle">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-bold text-white flex items-center gap-2">
              <Key size={18} className="text-accent" />
              Credential & Environment Overview
            </h2>
            <p className="text-xs text-gray-400 mt-0.5">
              Inspecting stored configuration tokens from local <code className="font-mono text-gray-300">.env</code>. Secrets are masked to protect credentials.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <div className="relative">
              <Search size={14} className="absolute left-3 top-2.5 text-gray-500" />
              <input
                type="text"
                value={credentialQuery}
                onChange={e => setCredentialQuery(e.target.value)}
                placeholder="Search variables..."
                className="bg-surface border border-border-subtle rounded-lg pl-8 pr-3 py-1.5 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-accent"
              />
            </div>
            <button
              onClick={() => setActiveTab('integrations')}
              className="px-3 py-1.5 bg-surface-elevated hover:bg-surface-elevated/80 border border-border text-xs text-gray-300 hover:text-white rounded-lg transition-all cursor-pointer whitespace-nowrap"
            >
              Manage Integrations
            </button>
          </div>
        </div>

        {/* Masked Credentials List */}
        {Object.keys(maskedEnv).length === 0 ? (
          <div className="p-6 rounded-xl bg-surface border border-border-subtle text-center">
            <p className="text-xs text-gray-400">No credentials configured in .env yet.</p>
            <button
              onClick={() => setActiveTab('integrations')}
              className="mt-2 text-xs font-bold text-accent hover:underline cursor-pointer"
            >
              Connect your first provider →
            </button>
          </div>
        ) : filteredCredentials.length === 0 ? (
          <div className="p-4 rounded-xl bg-surface border border-border-subtle text-center text-xs text-gray-400">
            No variables match "{credentialQuery}"
          </div>
        ) : (
          <div className="rounded-xl border border-border-subtle overflow-hidden bg-surface">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-surface-elevated/50 border-b border-border-subtle text-gray-400 font-semibold">
                  <th className="py-2.5 px-4">Environment Key</th>
                  <th className="py-2.5 px-4">Masked Value</th>
                  <th className="py-2.5 px-4 text-right">Source</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle font-mono text-[11px]">
                {filteredCredentials.map(([key, val]) => (
                  <tr key={key} className="hover:bg-surface-elevated/30 transition-colors">
                    <td className="py-2.5 px-4 font-bold text-gray-200">{key}</td>
                    <td className="py-2.5 px-4 text-accent font-semibold">{val || '••••••••'}</td>
                    <td className="py-2.5 px-4 text-right">
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-sans font-medium bg-surface-elevated text-gray-300 border border-border-subtle">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                        .env file
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* A5. About Section */}
      <section className="glass-card rounded-2xl p-6 space-y-4 border border-border-subtle">
        <h2 className="text-base font-bold text-white flex items-center gap-2">
          <Info size={18} className="text-accent" />
          About Lear Platform
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 pt-2">
          <div className="p-4 rounded-xl bg-surface border border-border-subtle">
            <span className="text-[11px] text-gray-400 block mb-1">Application Version</span>
            <span className="text-base font-bold text-white font-mono">
              v{systemInfo?.version || '2.4.0'}
            </span>
            <span className="text-[10px] text-emerald-400 block mt-1">● Up to date</span>
          </div>

          <div className="p-4 rounded-xl bg-surface border border-border-subtle">
            <span className="text-[11px] text-gray-400 block mb-1">Connector Coverage</span>
            <span className="text-base font-bold text-white font-mono">
              {systemInfo?.connectors_configured ?? 0} / {systemInfo?.connectors_total ?? 13}
            </span>
            <span className="text-[10px] text-gray-400 block mt-1">Configured providers</span>
          </div>

          <div className="p-4 rounded-xl bg-surface border border-border-subtle">
            <span className="text-[11px] text-gray-400 block mb-1">Runtime Environment</span>
            <span className="text-base font-bold text-white font-mono">
              Python {systemInfo?.python_version || '3.12+'}
            </span>
            <span className="text-[10px] text-gray-400 block mt-1 capitalize font-mono">
              OS: {systemInfo?.platform || 'Desktop'}
            </span>
          </div>

          <div className="p-4 rounded-xl bg-surface border border-border-subtle">
            <span className="text-[11px] text-gray-400 block mb-1">Core Architecture</span>
            <span className="text-sm font-bold text-white block truncate">
              {systemInfo?.engine || 'FastAPI + Prash Core'}
            </span>
            <span className="text-[10px] text-accent block mt-1">Zero Synthetic Data</span>
          </div>
        </div>
      </section>

      {/* Floating Save Footer */}
      <div className="fixed bottom-6 right-8 z-30 flex items-center gap-3 bg-surface-elevated/90 backdrop-blur-md border border-border px-5 py-3 rounded-2xl shadow-2xl">
        {saved && (
          <span className="flex items-center gap-1.5 text-xs text-emerald-400 font-medium">
            <CheckCircle2 size={14} />
            Preferences Saved!
          </span>
        )}
        {error && (
          <span className="flex items-center gap-1.5 text-xs text-rose-400 font-medium">
            <AlertTriangle size={14} />
            {error}
          </span>
        )}
        <button
          onClick={handleSave}
          disabled={saving || loading}
          className="flex items-center gap-2 px-6 py-2.5 bg-accent hover:bg-accent-light text-gray-950 font-bold text-xs rounded-xl shadow transition-all cursor-pointer disabled:opacity-50"
        >
          {saving ? (
            <>
              <div className="w-3.5 h-3.5 rounded-full border-2 border-gray-950 border-t-transparent animate-spin" />
              <span>Saving...</span>
            </>
          ) : (
            <>
              <Save size={15} />
              <span>{saved ? 'Saved!' : 'Save All Settings'}</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
}
