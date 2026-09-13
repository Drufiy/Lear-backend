import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Sparkles,
  X,
  Plus,
  Trash2,
  ChevronUp,
  ChevronDown,
  Eye,
  Sliders,
  Check,
  RotateCcw,
  LayoutGrid,
  Activity,
  LineChart as ChartIcon,
  BarChart3,
  CreditCard,
  Clock,
  ShieldCheck,
} from 'lucide-react';

export interface WidgetPosition {
  row: number;
  col: number;
  span: number;
}

export interface ConfigurableWidget {
  id: string;
  type: 'gauge' | 'line_chart' | 'bar_chart' | 'metric_card' | 'event_timeline' | 'status_grid';
  label: string;
  metric_keys?: string[];
  unit?: string;
  description?: string;
  refresh_interval?: number;
  position?: WidgetPosition;
  ai_generated?: boolean;
  rationale?: string;
}

interface WidgetConfiguratorProps {
  isOpen: boolean;
  onClose: () => void;
  connectorId: string;
  connectorName?: string;
  resourceId?: string;
  currentWidgets: ConfigurableWidget[];
  onSaveLayout: (newWidgets: ConfigurableWidget[]) => Promise<void>;
  onResetLayout: () => Promise<void>;
}

const WIDGET_TYPE_INFO: Record<
  string,
  { label: string; icon: React.ComponentType<{ size?: number; className?: string }>; defaultSpan: number; desc: string }
> = {
  gauge: { label: 'Radial Gauge', icon: Activity, defaultSpan: 1, desc: 'Circular dial for utilization percentages' },
  line_chart: { label: 'Line Chart', icon: ChartIcon, defaultSpan: 2, desc: 'Smooth continuous time-series trend' },
  bar_chart: { label: 'Bar Chart', icon: BarChart3, defaultSpan: 2, desc: 'Categorical distribution or severity count' },
  metric_card: { label: 'Metric KPI Card', icon: CreditCard, defaultSpan: 1, desc: 'Key performance metric with trend delta' },
  event_timeline: { label: 'Event Timeline', icon: Clock, defaultSpan: 2, desc: 'Chronological alarms and audit stream' },
  status_grid: { label: 'Health Status Grid', icon: ShieldCheck, defaultSpan: 3, desc: 'Comprehensive subsystem health checks' },
};

const SUGGESTED_PROMPTS = [
  'Focus on CPU & Memory pressure',
  'Executive summary with status & KPI cards',
  'Deep time-series trends for all I/O metrics',
  'Error rates & event incident timeline',
];

export const WidgetConfigurator: React.FC<WidgetConfiguratorProps> = ({
  isOpen,
  onClose,
  connectorId,
  connectorName,
  resourceId,
  currentWidgets,
  onSaveLayout,
  onResetLayout,
}) => {
  const [widgets, setWidgets] = useState<ConfigurableWidget[]>(() => {
    return currentWidgets.length > 0
      ? currentWidgets.map((w, idx) => ({
          ...w,
          id: w.id || `${connectorId}_widget_${idx}`,
          position: w.position || { row: 0, col: 0, span: w.type === 'status_grid' ? 3 : w.type === 'line_chart' || w.type === 'bar_chart' ? 2 : 1 },
        }))
      : [];
  });

  const [activeTab, setActiveTab] = useState<'editor' | 'preview'>('editor');
  const [prompt, setPrompt] = useState('');
  const [isSynthesizing, setIsSynthesizing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successNotice, setSuccessNotice] = useState<string | null>(null);

  // New widget draft state
  const [isAddingNew, setIsAddingNew] = useState(false);
  const [newType, setNewType] = useState<ConfigurableWidget['type']>('gauge');
  const [newLabel, setNewLabel] = useState('');
  const [newKeys, setNewKeys] = useState('');
  const [newUnit, setNewUnit] = useState('');
  const [newSpan, setNewSpan] = useState<number>(1);

  if (!isOpen) return null;

  // AI Synthesis Trigger
  const handleSynthesize = async (promptToUse?: string) => {
    const textPrompt = promptToUse || prompt;
    setIsSynthesizing(true);
    setErrorMessage(null);
    setSuccessNotice(null);

    try {
      const res = await fetch(`/api/connectors/${connectorId}/generate-widgets`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          resource_id: resourceId || '',
          prompt: textPrompt,
          save_to_yaml: false,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.message || err.detail || `Server error (${res.status})`);
      }

      const data = await res.json();
      if (Array.isArray(data.widgets) && data.widgets.length > 0) {
        setWidgets(data.widgets);
        setSuccessNotice(data.rationale || `Synthesized ${data.widgets.length} custom widgets.`);
      } else {
        throw new Error('No widgets synthesized from live telemetry.');
      }
    } catch (e: any) {
      setErrorMessage(e.message || 'Failed to synthesize widgets with AI');
    } finally {
      setIsSynthesizing(false);
    }
  };

  // Reorder Widgets
  const moveWidget = (idx: number, direction: 'up' | 'down') => {
    const targetIdx = direction === 'up' ? idx - 1 : idx + 1;
    if (targetIdx < 0 || targetIdx >= widgets.length) return;
    const updated = [...widgets];
    const [moved] = updated.splice(idx, 1);
    updated.splice(targetIdx, 0, moved);
    setWidgets(updated);
  };

  // Remove Widget
  const removeWidget = (idx: number) => {
    setWidgets(widgets.filter((_, i) => i !== idx));
  };

  // Update Widget Span
  const updateWidgetSpan = (idx: number, span: number) => {
    const updated = [...widgets];
    const item = { ...updated[idx] };
    item.position = { ...(item.position || { row: 0, col: 0, span: 1 }), span };
    updated[idx] = item;
    setWidgets(updated);
  };

  // Update Widget Label
  const updateWidgetLabel = (idx: number, label: string) => {
    const updated = [...widgets];
    updated[idx] = { ...updated[idx], label };
    setWidgets(updated);
  };

  // Add New Custom Widget
  const handleAddNewWidget = () => {
    if (!newLabel.trim()) return;
    const keysArray = newKeys.split(',').map(k => k.trim()).filter(Boolean);
    const newWidget: ConfigurableWidget = {
      id: `${connectorId}_custom_${Date.now()}`,
      type: newType,
      label: newLabel.trim(),
      metric_keys: keysArray,
      unit: newUnit.trim(),
      position: { row: 0, col: 0, span: newSpan },
      ai_generated: false,
    };
    setWidgets([...widgets, newWidget]);
    setNewLabel('');
    setNewKeys('');
    setNewUnit('');
    setIsAddingNew(false);
  };

  // Save to Backend
  const handleSave = async () => {
    setIsSaving(true);
    setErrorMessage(null);
    try {
      await onSaveLayout(widgets);
      onClose();
    } catch (e: any) {
      setErrorMessage(e.message || 'Failed to save widget layout');
    } finally {
      setIsSaving(false);
    }
  };

  // Reset to Defaults
  const handleReset = async () => {
    if (!window.confirm('Reset this service to default registry widgets?')) return;
    setIsResetting(true);
    setErrorMessage(null);
    try {
      await onResetLayout();
      onClose();
    } catch (e: any) {
      setErrorMessage(e.message || 'Failed to reset layout');
    } finally {
      setIsResetting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.96 }}
        className="glass-card w-full max-w-4xl max-h-[90vh] flex flex-col rounded-2xl border border-border-subtle shadow-2xl overflow-hidden bg-background/95"
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-border-subtle shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-accent/15 border border-accent/30 text-accent">
              <LayoutGrid size={22} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold text-white">
                  Widget Layout Configurator
                </h2>
                <span className="text-xs px-2.5 py-0.5 rounded-full bg-surface border border-border-subtle text-accent font-medium uppercase font-mono">
                  {connectorName || connectorId}
                </span>
                {resourceId && (
                  <span className="text-xs px-2 py-0.5 rounded bg-surface border border-border-subtle text-gray-400 font-mono">
                    {resourceId}
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-400 mt-0.5">
                Customize, synthesize with AI, or manually position telemetry widgets for this service.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* View Mode Tabs */}
            <div className="flex items-center p-1 rounded-xl bg-surface border border-border-subtle">
              <button
                onClick={() => setActiveTab('editor')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer ${
                  activeTab === 'editor' ? 'bg-accent/20 text-accent font-bold' : 'text-gray-400 hover:text-white'
                }`}
              >
                <Sliders size={13} />
                Editor ({widgets.length})
              </button>
              <button
                onClick={() => setActiveTab('preview')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer ${
                  activeTab === 'preview' ? 'bg-accent/20 text-accent font-bold' : 'text-gray-400 hover:text-white'
                }`}
              >
                <Eye size={13} />
                Visual Grid
              </button>
            </div>

            <button
              onClick={onClose}
              className="p-2 text-gray-400 hover:text-white rounded-lg hover:bg-white/5 transition-colors cursor-pointer ml-1"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* AI Synthesis Prompt Section */}
        <div className="p-6 border-b border-border-subtle bg-surface/40 shrink-0 space-y-3">
          <div className="flex items-center gap-2 text-xs font-semibold text-white">
            <Sparkles size={14} className="text-accent animate-pulse" />
            <span>AI Telemetry Layout Synthesizer</span>
          </div>

          <div className="flex gap-2">
            <div className="relative flex-1">
              <input
                type="text"
                value={prompt}
                onChange={e => setPrompt(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSynthesize()}
                placeholder="Describe your desired layout (e.g., 'Focus on CPU & memory spikes', 'High-level executive health')..."
                className="w-full px-4 py-2.5 bg-surface border border-border-subtle rounded-xl text-sm text-white placeholder-gray-500 focus:outline-none focus:border-accent"
              />
            </div>
            <button
              onClick={() => handleSynthesize()}
              disabled={isSynthesizing}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-accent hover:bg-accent/90 disabled:opacity-50 text-white text-xs font-semibold shadow-lg shadow-accent/20 transition-all cursor-pointer shrink-0"
            >
              <Sparkles size={14} className={isSynthesizing ? 'animate-spin' : ''} />
              {isSynthesizing ? 'Synthesizing...' : 'Synthesize with AI'}
            </button>
          </div>

          {/* Quick suggestions */}
          <div className="flex flex-wrap items-center gap-1.5 pt-1">
            <span className="text-[11px] text-gray-500 font-medium mr-1">Suggestions:</span>
            {SUGGESTED_PROMPTS.map((s, idx) => (
              <button
                key={idx}
                onClick={() => {
                  setPrompt(s);
                  handleSynthesize(s);
                }}
                className="text-[11px] px-2.5 py-1 rounded-lg bg-surface hover:bg-surface-elevated border border-border-subtle text-gray-300 hover:text-white transition-colors cursor-pointer"
              >
                {s}
              </button>
            ))}
          </div>

          {/* Banners */}
          {errorMessage && (
            <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-xs text-rose-300 flex items-center justify-between">
              <span>{errorMessage}</span>
              <button onClick={() => setErrorMessage(null)} className="text-rose-400 hover:text-white">
                <X size={14} />
              </button>
            </div>
          )}

          {successNotice && (
            <div className="p-3 rounded-xl bg-accent/10 border border-accent/30 text-xs text-accent flex items-center justify-between">
              <span className="flex items-center gap-2">
                <Check size={14} />
                {successNotice}
              </span>
              <button onClick={() => setSuccessNotice(null)} className="text-accent hover:text-white">
                <X size={14} />
              </button>
            </div>
          )}
        </div>

        {/* Main Content Area */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4 custom-scrollbar">
          {activeTab === 'editor' ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-wider text-gray-400">
                  Configured Widgets ({widgets.length})
                </span>
                <button
                  onClick={() => setIsAddingNew(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface hover:bg-surface-elevated border border-border-subtle text-xs font-medium text-white transition-colors cursor-pointer"
                >
                  <Plus size={13} />
                  Add Custom Widget
                </button>
              </div>

              {/* Add New Form */}
              <AnimatePresence>
                {isAddingNew && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="p-4 rounded-xl bg-surface border border-accent/40 space-y-3"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-white">Add New Widget Tile</span>
                      <button onClick={() => setIsAddingNew(false)} className="text-gray-400 hover:text-white">
                        <X size={14} />
                      </button>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      <div>
                        <label className="text-[11px] text-gray-400 block mb-1">Widget Type</label>
                        <select
                          value={newType}
                          onChange={e => {
                            const val = e.target.value as ConfigurableWidget['type'];
                            setNewType(val);
                            setNewSpan(WIDGET_TYPE_INFO[val]?.defaultSpan || 1);
                          }}
                          className="w-full px-3 py-2 bg-background border border-border-subtle rounded-lg text-xs text-white focus:outline-none focus:border-accent"
                        >
                          {Object.entries(WIDGET_TYPE_INFO).map(([k, v]) => (
                            <option key={k} value={k}>
                              {v.label}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div>
                        <label className="text-[11px] text-gray-400 block mb-1">Label</label>
                        <input
                          type="text"
                          value={newLabel}
                          onChange={e => setNewLabel(e.target.value)}
                          placeholder="e.g. Memory Consumption"
                          className="w-full px-3 py-2 bg-background border border-border-subtle rounded-lg text-xs text-white placeholder-gray-500 focus:outline-none focus:border-accent"
                        />
                      </div>

                      <div>
                        <label className="text-[11px] text-gray-400 block mb-1">Column Span</label>
                        <select
                          value={newSpan}
                          onChange={e => setNewSpan(Number(e.target.value))}
                          className="w-full px-3 py-2 bg-background border border-border-subtle rounded-lg text-xs text-white focus:outline-none focus:border-accent"
                        >
                          <option value={1}>Span 1 (33% Width)</option>
                          <option value={2}>Span 2 (66% Width)</option>
                          <option value={3}>Span 3 (100% Full Width)</option>
                        </select>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div>
                        <label className="text-[11px] text-gray-400 block mb-1">Metric Keys (comma-separated)</label>
                        <input
                          type="text"
                          value={newKeys}
                          onChange={e => setNewKeys(e.target.value)}
                          placeholder="e.g. memory, mem_pct, ram"
                          className="w-full px-3 py-2 bg-background border border-border-subtle rounded-lg text-xs text-white placeholder-gray-500 focus:outline-none focus:border-accent"
                        />
                      </div>
                      <div>
                        <label className="text-[11px] text-gray-400 block mb-1">Unit</label>
                        <input
                          type="text"
                          value={newUnit}
                          onChange={e => setNewUnit(e.target.value)}
                          placeholder="e.g. % or MB"
                          className="w-full px-3 py-2 bg-background border border-border-subtle rounded-lg text-xs text-white placeholder-gray-500 focus:outline-none focus:border-accent"
                        />
                      </div>
                    </div>

                    <div className="flex justify-end gap-2 pt-2">
                      <button
                        onClick={() => setIsAddingNew(false)}
                        className="px-3 py-1.5 rounded-lg bg-surface text-gray-300 hover:text-white text-xs"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleAddNewWidget}
                        disabled={!newLabel.trim()}
                        className="px-4 py-1.5 rounded-lg bg-accent text-white text-xs font-semibold disabled:opacity-50"
                      >
                        Add to Layout
                      </button>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Widget List */}
              {widgets.length === 0 ? (
                <div className="py-12 text-center text-xs text-gray-400 glass-panel rounded-xl">
                  No widgets configured. Use AI Synthesizer above or click "Add Custom Widget".
                </div>
              ) : (
                <div className="space-y-2.5">
                  {widgets.map((widget, idx) => {
                    const info = WIDGET_TYPE_INFO[widget.type] || WIDGET_TYPE_INFO.gauge;
                    const IconComponent = info.icon;
                    const span = widget.position?.span || 1;

                    return (
                      <div
                        key={widget.id || idx}
                        className="p-3.5 rounded-xl bg-surface border border-border-subtle hover:border-border transition-all flex flex-wrap items-center justify-between gap-3"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          {/* Reorder Buttons */}
                          <div className="flex flex-col gap-0.5">
                            <button
                              onClick={() => moveWidget(idx, 'up')}
                              disabled={idx === 0}
                              className="p-1 rounded hover:bg-white/10 text-gray-400 hover:text-white disabled:opacity-20 cursor-pointer"
                            >
                              <ChevronUp size={12} />
                            </button>
                            <button
                              onClick={() => moveWidget(idx, 'down')}
                              disabled={idx === widgets.length - 1}
                              className="p-1 rounded hover:bg-white/10 text-gray-400 hover:text-white disabled:opacity-20 cursor-pointer"
                            >
                              <ChevronDown size={12} />
                            </button>
                          </div>

                          {/* Icon & Type Badge */}
                          <div className="p-2 rounded-lg bg-white/5 border border-white/10 text-accent shrink-0">
                            <IconComponent size={16} />
                          </div>

                          {/* Widget Details */}
                          <div className="min-w-0 space-y-0.5">
                            <div className="flex items-center gap-2">
                              <input
                                type="text"
                                value={widget.label}
                                onChange={e => updateWidgetLabel(idx, e.target.value)}
                                className="bg-transparent text-sm font-semibold text-white focus:outline-none focus:bg-white/5 px-1 py-0.5 rounded border-b border-transparent focus:border-accent"
                              />
                              {widget.ai_generated && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent/15 text-accent font-medium shrink-0">
                                  AI
                                </span>
                              )}
                            </div>
                            <div className="flex flex-wrap items-center gap-2 text-[11px] text-gray-400">
                              <span className="capitalize">{info.label}</span>
                              <span>•</span>
                              <span>
                                Keys: {widget.metric_keys && widget.metric_keys.length > 0 ? widget.metric_keys.join(', ') : 'Default'}
                              </span>
                              {widget.unit && (
                                <>
                                  <span>•</span>
                                  <span>Unit: {widget.unit}</span>
                                </>
                              )}
                            </div>
                          </div>
                        </div>

                        {/* Controls */}
                        <div className="flex items-center gap-3 shrink-0">
                          {/* Span Select */}
                          <div className="flex items-center gap-1.5 text-xs text-gray-400">
                            <span className="text-[11px]">Width:</span>
                            <div className="flex items-center p-0.5 rounded-lg bg-background border border-border-subtle">
                              {[1, 2, 3].map(s => (
                                <button
                                  key={s}
                                  onClick={() => updateWidgetSpan(idx, s)}
                                  className={`px-2 py-0.5 rounded text-[11px] font-mono cursor-pointer transition-colors ${
                                    span === s ? 'bg-accent text-white font-bold' : 'text-gray-400 hover:text-white'
                                  }`}
                                >
                                  {s === 1 ? '1/3' : s === 2 ? '2/3' : '3/3'}
                                </button>
                              ))}
                            </div>
                          </div>

                          {/* Delete */}
                          <button
                            onClick={() => removeWidget(idx)}
                            className="p-1.5 rounded-lg text-gray-400 hover:text-rose-400 hover:bg-rose-500/10 transition-colors cursor-pointer"
                            title="Remove widget"
                          >
                            <Trash2 size={15} />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ) : (
            /* Visual Grid Preview */
            <div className="space-y-3">
              <div className="flex items-center justify-between text-xs text-gray-400">
                <span>3-Column Grid Preview (Standard Desktop Layout)</span>
                <span>{widgets.length} tiles active</span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 p-4 rounded-xl bg-surface/50 border border-border-subtle min-h-[300px]">
                {widgets.map((widget, idx) => {
                  const info = WIDGET_TYPE_INFO[widget.type] || WIDGET_TYPE_INFO.gauge;
                  const IconComponent = info.icon;
                  const span = widget.position?.span || 1;

                  const colSpanClass =
                    span === 3 ? 'lg:col-span-3' : span === 2 ? 'lg:col-span-2' : 'lg:col-span-1';

                  return (
                    <div
                      key={widget.id || idx}
                      className={`glass-panel p-4 rounded-xl border border-border-subtle flex flex-col justify-between ${colSpanClass} relative min-h-[120px]`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <IconComponent size={15} className="text-accent" />
                          <span className="text-xs font-semibold text-white">{widget.label}</span>
                        </div>
                        <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-surface border border-border-subtle text-gray-400">
                          {span === 3 ? 'Full Width' : span === 2 ? '2 Columns' : '1 Column'}
                        </span>
                      </div>

                      <div className="py-2 text-center">
                        <span className="text-lg font-bold text-gray-500 font-mono">
                          [{info.label}]
                        </span>
                      </div>

                      <div className="flex items-center justify-between text-[10px] text-gray-500">
                        <span>{widget.metric_keys?.join(', ') || 'metric'}</span>
                        <span>{widget.unit || ''}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="p-6 border-t border-border-subtle bg-surface/80 shrink-0 flex items-center justify-between">
          <button
            onClick={handleReset}
            disabled={isResetting}
            className="flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-medium text-gray-400 hover:text-white hover:bg-white/5 border border-border-subtle transition-colors cursor-pointer"
          >
            <RotateCcw size={13} className={isResetting ? 'animate-spin' : ''} />
            {isResetting ? 'Resetting...' : 'Reset to Defaults'}
          </button>

          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-xs font-medium text-gray-300 hover:text-white transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={isSaving || widgets.length === 0}
              className="flex items-center gap-2 px-6 py-2 rounded-xl bg-accent hover:bg-accent/90 disabled:opacity-50 text-white text-xs font-bold shadow-lg shadow-accent/20 transition-all cursor-pointer"
            >
              <Check size={14} className={isSaving ? 'animate-spin' : ''} />
              {isSaving ? 'Applying...' : 'Save & Apply Layout'}
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
};

export default WidgetConfigurator;
