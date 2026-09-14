import React, { useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, Plus, Save, Trash2, X } from 'lucide-react';

export interface WidgetConfig {
  id: string;
  type: string;
  label: string;
  metric_keys: string[];
  unit?: string;
  description?: string;
  refresh_interval?: number;
  position?: { row: number; col: number; span: number };
  ai_generated?: boolean;
  rationale?: string;
}

export interface WidgetConfiguratorProps {
  connectorId: string;
  resourceId?: string;
  widgets: WidgetConfig[];
  availableMetrics?: string[];
  onClose: () => void;
  onSaved: (widgets: WidgetConfig[]) => void;
}

export const WIDGET_TYPES = [
  'gauge',
  'line_chart',
  'bar_chart',
  'metric_card',
  'event_timeline',
  'status_grid',
] as const;

export const WidgetConfigurator: React.FC<WidgetConfiguratorProps> = ({
  connectorId,
  resourceId = '',
  widgets,
  availableMetrics = [],
  onClose,
  onSaved,
}) => {
  const [draft, setDraft] = useState<WidgetConfig[]>(() => widgets.map(w => ({ ...w })));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const metricDatalistId = useMemo(() => `metrics-${connectorId}-${resourceId || 'all'}`, [connectorId, resourceId]);

  const updateWidget = (index: number, patch: Partial<WidgetConfig>) => {
    setDraft(prev => prev.map((w, i) => (i === index ? { ...w, ...patch } : w)));
  };

  const moveWidget = (index: number, direction: -1 | 1) => {
    setDraft(prev => {
      const target = index + direction;
      if (target < 0 || target >= prev.length) return prev;
      const next = [...prev];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };

  const removeWidget = (index: number) => {
    setDraft(prev => prev.filter((_, i) => i !== index));
  };

  const addWidget = () => {
    setDraft(prev => [
      ...prev,
      {
        id: `custom_${Date.now().toString(36)}`,
        type: 'metric_card',
        label: 'New widget',
        metric_keys: [],
        unit: '',
        ai_generated: false,
      },
    ]);
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`/api/connectors/${connectorId}/widgets`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resource_id: resourceId, widgets: draft }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        const rejected = Array.isArray(body?.detail?.rejected) ? body.detail.rejected.join('; ') : '';
        setError(rejected || body?.message || `Could not save layout (${res.status})`);
        return;
      }
      onSaved(body.widgets || draft);
    } catch (e: any) {
      setError(typeof e?.message === 'string' ? e.message : 'Network error saving layout');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-black/80 backdrop-blur-md">
      <div className="glass-card rounded-2xl border border-border-subtle p-6 w-full max-w-3xl max-h-[85vh] overflow-y-auto flex flex-col gap-5 shadow-2xl">
        <div className="flex justify-between items-center pb-4 border-b border-border-subtle">
          <div>
            <h3 className="text-lg font-bold text-white">Customize Widget Layout</h3>
            <p className="text-xs text-gray-400">
              Add, remove, or reorder widgets for {connectorId}
              {resourceId ? ` · ${resourceId}` : ''}. Changes are validated against connector capabilities.
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close configurator"
            className="p-2 rounded-lg bg-surface hover:bg-surface-elevated text-gray-400 hover:text-white transition-colors cursor-pointer"
          >
            <X size={18} />
          </button>
        </div>

        {error && (
          <div role="alert" className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/25 text-rose-300 text-xs">
            {error}
          </div>
        )}

        {availableMetrics.length > 0 && (
          <datalist id={metricDatalistId}>
            {availableMetrics.map(metric => (
              <option key={metric} value={metric} />
            ))}
          </datalist>
        )}

        <div className="space-y-3">
          {draft.length === 0 && (
            <p className="text-xs text-gray-400 italic py-6 text-center">
              No widgets yet. Add one to build a custom layout.
            </p>
          )}

          {draft.map((widget, index) => (
            <div key={widget.id} className="glass-panel rounded-xl p-4 border border-border-subtle space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 flex-1">
                  <label className="flex flex-col gap-1 text-[11px] text-gray-400">
                    Label
                    <input
                      value={widget.label}
                      onChange={e => updateWidget(index, { label: e.target.value })}
                      className="bg-surface border border-border-subtle rounded-lg px-2.5 py-1.5 text-xs text-white outline-none focus:border-accent"
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-[11px] text-gray-400">
                    Type
                    <select
                      value={widget.type}
                      onChange={e => updateWidget(index, { type: e.target.value })}
                      className="bg-surface border border-border-subtle rounded-lg px-2.5 py-1.5 text-xs text-white outline-none focus:border-accent"
                    >
                      {WIDGET_TYPES.map(type => (
                        <option key={type} value={type}>{type}</option>
                      ))}
                    </select>
                  </label>
                  <label className="flex flex-col gap-1 text-[11px] text-gray-400">
                    Metric keys (comma separated)
                    <input
                      list={availableMetrics.length > 0 ? metricDatalistId : undefined}
                      value={widget.metric_keys.join(', ')}
                      onChange={e =>
                        updateWidget(index, {
                          metric_keys: e.target.value.split(',').map(k => k.trim()).filter(Boolean),
                        })
                      }
                      placeholder="CPUUtilization, cpu"
                      className="bg-surface border border-border-subtle rounded-lg px-2.5 py-1.5 text-xs text-white outline-none focus:border-accent"
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-[11px] text-gray-400">
                    Unit
                    <input
                      value={widget.unit || ''}
                      onChange={e => updateWidget(index, { unit: e.target.value })}
                      placeholder="%"
                      className="bg-surface border border-border-subtle rounded-lg px-2.5 py-1.5 text-xs text-white outline-none focus:border-accent"
                    />
                  </label>
                </div>

                <div className="flex flex-col gap-1.5">
                  <button
                    onClick={() => moveWidget(index, -1)}
                    disabled={index === 0}
                    aria-label={`Move ${widget.label} up`}
                    className="p-1.5 rounded-lg bg-surface hover:bg-surface-elevated border border-border-subtle text-gray-400 hover:text-white disabled:opacity-40 cursor-pointer"
                  >
                    <ArrowUp size={14} />
                  </button>
                  <button
                    onClick={() => moveWidget(index, 1)}
                    disabled={index === draft.length - 1}
                    aria-label={`Move ${widget.label} down`}
                    className="p-1.5 rounded-lg bg-surface hover:bg-surface-elevated border border-border-subtle text-gray-400 hover:text-white disabled:opacity-40 cursor-pointer"
                  >
                    <ArrowDown size={14} />
                  </button>
                  <button
                    onClick={() => removeWidget(index)}
                    aria-label={`Remove ${widget.label}`}
                    className="p-1.5 rounded-lg bg-surface hover:bg-rose-500/15 border border-border-subtle hover:border-rose-500/30 text-gray-400 hover:text-rose-400 cursor-pointer"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>

        <button
          onClick={addWidget}
          className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl bg-surface hover:bg-surface-elevated border border-dashed border-border-subtle text-xs font-medium text-gray-300 transition-colors cursor-pointer"
        >
          <Plus size={14} />
          Add widget
        </button>

        <div className="flex justify-end gap-3 pt-2 border-t border-border-subtle">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl bg-surface hover:bg-surface-elevated text-gray-300 text-xs font-medium transition-colors cursor-pointer"
          >
            Cancel
          </button>
          <button
            onClick={save}
            disabled={saving || draft.length === 0}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-accent text-gray-950 font-bold text-xs hover:bg-accent-light transition-all disabled:opacity-50 cursor-pointer"
          >
            <Save size={14} />
            {saving ? 'Saving...' : 'Save layout'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default WidgetConfigurator;
