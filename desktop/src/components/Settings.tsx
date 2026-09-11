import { useState, useEffect } from 'react';
import { Shield, Cpu, Save } from 'lucide-react';

export default function Settings({ onReconfigure }: { onReconfigure?: () => void }) {
  const [model, setModel] = useState('deepseek-v4-flash');
  const [permissionMode, setPermissionMode] = useState('ask');
  const [availableModels, setAvailableModels] = useState<any[]>([
    { id: 'deepseek-v4-flash', name: 'DeepSeek Flash', desc: 'Ultra-fast intent resolution & diagnostics' },
    { id: 'kimi-k2.6', name: 'Kimi K2.6', desc: 'Deep technical reasoning & large log contexts' },
    { id: 'gemini-1.5-pro', name: 'Gemini Pro', desc: 'High capability multi-modal analysis' },
  ]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/settings')
      .then(res => res.json())
      .then(data => {
        if (data.model) setModel(data.model);
        if (data.permission_mode) setPermissionMode(data.permission_mode);
        if (data.available_models && Array.isArray(data.available_models)) {
          setAvailableModels(data.available_models);
        }
      })
      .catch(console.error);
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model, permission_mode: permissionMode }),
      });
      if (res.ok) {
        setSaved(true);
        setTimeout(() => setSaved(false), 3000);
      } else {
        setError('Failed to persist settings.');
      }
    } catch (e: any) {
      setError(e?.message || 'Error saving settings.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="p-8 max-w-4xl mx-auto space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-white mb-2">Platform Settings</h1>
        <p className="text-sm text-gray-400">
          Configure AI reasoning models, permission scopes, and local security policies for Lear.
        </p>
      </div>

      {/* Setup Wizard Link */}
      <div className="glass-card rounded-2xl p-6 flex items-center justify-between">
        <div>
          <h3 className="font-bold text-base text-white">Infrastructure Setup Wizard</h3>
          <p className="text-xs text-gray-400 mt-0.5">
            Re-run the step-by-step connection wizard to connect or update credentials.
          </p>
        </div>
        {onReconfigure && (
          <button
            onClick={onReconfigure}
            className="px-4 py-2 bg-accent hover:bg-accent-light text-gray-950 font-bold text-xs rounded-xl transition-all cursor-pointer shadow"
          >
            Launch Wizard
          </button>
        )}
      </div>

      {/* Model Provider Section */}
      <section className="glass-card rounded-2xl p-6 space-y-4">
        <h2 className="text-base font-bold text-white flex items-center gap-2">
          <Cpu size={18} className="text-accent" />
          AI Diagnosis & Model Provider
        </h2>
        <p className="text-xs text-gray-400">
          Select the model that powers Lear Copilot and root-cause analysis.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2">
          {availableModels.map(m => (
            <button
              key={m.id}
              onClick={() => setModel(m.id)}
              className={`p-4 rounded-xl text-left border transition-all cursor-pointer ${
                model === m.id
                  ? 'bg-accent/15 border-accent text-white'
                  : 'bg-surface border-border-subtle text-gray-400 hover:text-white'
              }`}
            >
              <span className="font-bold text-xs block text-white">{m.name}</span>
              <span className="text-[11px] text-gray-400 mt-1 block">{m.desc}</span>
            </button>
          ))}
        </div>
      </section>

      {/* Permission Mode Section */}
      <section className="glass-card rounded-2xl p-6 space-y-4">
        <h2 className="text-base font-bold text-white flex items-center gap-2">
          <Shield size={18} className="text-accent" />
          Permission & Execution Safety
        </h2>
        <p className="text-xs text-gray-400">
          Controls whether Lear can execute operational actions automatically or requires approval.
        </p>

        <div className="space-y-3 pt-2">
          {[
            { id: 'ask', label: 'Ask First (Recommended)', desc: 'Always request user confirmation before modifying cloud resources.' },
            { id: 'auto-safe', label: 'Auto-Safe Tier', desc: 'Execute read-only and safe diagnostics automatically; ask for write actions.' },
            { id: 'bypass', label: 'Bypass (Autonomous)', desc: 'Allow autonomous remediation for verified health degradation.' },
          ].map(p => (
            <label
              key={p.id}
              className={`flex items-start gap-3 p-3.5 rounded-xl border cursor-pointer transition-all ${
                permissionMode === p.id
                  ? 'bg-surface-elevated border-accent/40 text-white'
                  : 'bg-surface border-border-subtle text-gray-400 hover:text-white'
              }`}
            >
              <input
                type="radio"
                name="permission"
                checked={permissionMode === p.id}
                onChange={() => setPermissionMode(p.id)}
                className="mt-1 accent-[#ff3a89]"
              />
              <div>
                <span className="font-bold text-xs block text-white">{p.label}</span>
                <span className="text-[11px] text-gray-400 mt-0.5 block">{p.desc}</span>
              </div>
            </label>
          ))}
        </div>
      </section>

      {/* Save Button */}
      <div className="flex items-center justify-end gap-4">
        {error && <span className="text-xs text-rose-400 font-medium">{error}</span>}
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-6 py-2.5 bg-accent hover:bg-accent-light text-gray-950 font-bold text-xs rounded-xl shadow-lg transition-all cursor-pointer disabled:opacity-50"
        >
          {saving ? (
            <>
              <div className="w-3.5 h-3.5 rounded-full border-2 border-gray-950 border-t-transparent animate-spin" />
              <span>Saving...</span>
            </>
          ) : (
            <>
              <Save size={16} />
              <span>{saved ? 'Preferences Saved!' : 'Save Settings'}</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
}
