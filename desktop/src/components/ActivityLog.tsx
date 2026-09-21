import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  Activity,
  Clock,
  Search,
  AlertCircle,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  X,
  MessageSquare,
  Terminal,
  Layers,
  ArrowRight,
  SlidersHorizontal,
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import useWatcher from '../hooks/useWatcher';
import { useLear } from '../context/LearContext';

export interface ActivityEvent {
  id: string;
  timestamp: string;
  connector?: string;
  event_type: string;
  severity?: 'info' | 'warning' | 'error' | 'critical' | string;
  summary: string;
  details?: any;
  action?: string;
  status?: string;
  watch_id?: string;
  [key: string]: any;
}

interface ConnectorItem {
  id: string;
  name: string;
  color?: string;
  status: string;
}

function formatTime(isoString: string): string {
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return isoString;
  }
}

function getSeverityBadge(severity?: string) {
  const s = (severity || 'info').toLowerCase();
  if (s === 'error' || s === 'critical' || s === 'failed') {
    return {
      badgeClass: 'bg-rose-500/15 border-rose-500/30 text-rose-400',
      iconClass: 'text-rose-400',
      icon: AlertCircle,
      label: 'ERROR',
    };
  }
  if (s === 'warning' || s === 'degraded') {
    return {
      badgeClass: 'bg-amber-400/15 border-amber-400/30 text-amber-400',
      iconClass: 'text-amber-400',
      icon: AlertTriangle,
      label: 'WARN',
    };
  }
  return {
    badgeClass: 'bg-accent/15 border-accent/30 text-accent',
    iconClass: 'text-accent',
    icon: Activity,
    label: 'INFO',
  };
}

export default function ActivityLog() {
  const { setActiveTab, openChat } = useLear();
  const { events: liveEvents } = useWatcher();

  // Server state & pagination
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);

  // Filters & search
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [selectedConnector, setSelectedConnector] = useState('all');
  const [selectedType, setSelectedType] = useState('all');
  const [selectedSeverity, setSelectedSeverity] = useState('all');
  const [selectedTimeRange, setSelectedTimeRange] = useState('all');

  // Connectors list for dynamic dropdown
  const [connectors, setConnectors] = useState<ConnectorItem[]>([]);
  const [expandedEventId, setExpandedEventId] = useState<string | null>(null);

  // Debounce search query (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(searchQuery);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Load configured connectors list for dynamic filter
  useEffect(() => {
    fetch('/api/connectors')
      .then(res => res.json())
      .then(data => {
        if (data && data.connectors) {
          setConnectors(data.connectors);
        }
      })
      .catch(err => console.error('Error loading connectors for filters:', err));
  }, []);

  // Fetch activity events from backend
  const fetchEvents = useCallback(
    async (reset = false, newOffset = 0) => {
      if (reset) {
        setLoading(true);
      } else {
        setLoadingMore(true);
      }

      try {
        const params = new URLSearchParams();
        params.set('limit', '30');
        params.set('offset', String(newOffset));

        if (debouncedQuery.trim()) {
          params.set('q', debouncedQuery.trim());
        }
        if (selectedConnector !== 'all') {
          params.set('connector', selectedConnector);
        }
        if (selectedType !== 'all') {
          params.set('type', selectedType);
        }
        if (selectedSeverity !== 'all') {
          params.set('severity', selectedSeverity);
        }
        if (selectedTimeRange !== 'all') {
          params.set('time_range', selectedTimeRange);
        }

        const res = await fetch(`/api/activity?${params.toString()}`);
        if (res.ok) {
          const data = await res.json();
          const incomingEvents: ActivityEvent[] = data.events || [];

          if (reset) {
            setEvents(incomingEvents);
            setOffset(0);
          } else {
            setEvents(prev => {
              const existingIds = new Set(prev.map(e => e.id));
              const deduplicated = incomingEvents.filter(e => !existingIds.has(e.id));
              return [...prev, ...deduplicated];
            });
            setOffset(newOffset);
          }

          setTotal(data.total ?? incomingEvents.length);
          setHasMore(data.has_more ?? (newOffset + incomingEvents.length < (data.total ?? 0)));
        }
      } catch (e) {
        console.error('Error fetching activity log:', e);
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [debouncedQuery, selectedConnector, selectedType, selectedSeverity, selectedTimeRange]
  );

  // Refetch when filters or debounced search changes
  useEffect(() => {
    fetchEvents(true, 0);
  }, [fetchEvents]);

  // Merge live watcher events dynamically
  const liveEventsRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    if (!liveEvents || liveEvents.length === 0) return;

    // Filter incoming live events matching active filter criteria
    const newItems: ActivityEvent[] = [];
    for (const le of liveEvents) {
      const id = String(le.id || `${le.watch_id}:${le.timestamp}`);
      if (!liveEventsRef.current.has(id)) {
        liveEventsRef.current.add(id);

        const matchesConnector =
          selectedConnector === 'all' ||
          (le.connector && le.connector.toLowerCase() === selectedConnector.toLowerCase());

        const matchesQuery =
          !debouncedQuery ||
          (le.summary && le.summary.toLowerCase().includes(debouncedQuery.toLowerCase())) ||
          (le.event_type && le.event_type.toLowerCase().includes(debouncedQuery.toLowerCase()));

        if (matchesConnector && matchesQuery) {
          newItems.push({
            id,
            timestamp: le.timestamp,
            connector: le.connector,
            event_type: le.event_type,
            severity: le.severity || (le.event_type.includes('ERROR') ? 'error' : 'info'),
            summary: le.summary || le.event_type,
            details: le,
          });
        }
      }
    }

    if (newItems.length > 0) {
      setEvents(prev => {
        const existingIds = new Set(prev.map(e => e.id));
        const deduplicated = newItems.filter(e => !existingIds.has(e.id));
        return [...deduplicated, ...prev];
      });
      setTotal(t => t + newItems.length);
    }
  }, [liveEvents, selectedConnector, debouncedQuery]);

  // Handle Load More pagination
  const handleLoadMore = () => {
    if (loadingMore || !hasMore) return;
    const nextOffset = offset + 30;
    fetchEvents(false, nextOffset);
  };

  // Reset all filters
  const handleResetFilters = () => {
    setSearchQuery('');
    setDebouncedQuery('');
    setSelectedConnector('all');
    setSelectedType('all');
    setSelectedSeverity('all');
    setSelectedTimeRange('all');
  };

  const isFiltered =
    debouncedQuery !== '' ||
    selectedConnector !== 'all' ||
    selectedType !== 'all' ||
    selectedSeverity !== 'all' ||
    selectedTimeRange !== 'all';

  // Group events by day header (Phase B2)
  const groupedEvents = useMemo(() => {
    const groups: { [key: string]: ActivityEvent[] } = {};
    const now = new Date();
    const todayStr = now.toDateString();
    const yesterday = new Date();
    yesterday.setDate(now.getDate() - 1);
    const yesterdayStr = yesterday.toDateString();

    for (const ev of events) {
      const d = new Date(ev.timestamp);
      let label: string;
      if (isNaN(d.getTime())) {
        label = 'RECENT ACTIVITY';
      } else if (d.toDateString() === todayStr) {
        label = 'TODAY';
      } else if (d.toDateString() === yesterdayStr) {
        label = 'YESTERDAY';
      } else {
        label = d.toLocaleDateString([], {
          weekday: 'short',
          month: 'short',
          day: 'numeric',
          year: 'numeric',
        }).toUpperCase();
      }

      if (!groups[label]) {
        groups[label] = [];
      }
      groups[label].push(ev);
    }
    return groups;
  }, [events]);

  const groupKeys = Object.keys(groupedEvents);

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      {/* Header Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-border-subtle">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white mb-1.5 flex items-center gap-3">
            Activity & Audit Log
            <span className="text-xs font-mono px-2.5 py-1 rounded-full bg-surface border border-border-subtle text-accent">
              {total} Total Events
            </span>
          </h1>
          <p className="text-sm text-gray-400">
            Chronological audit trail aggregating live watcher events, Lear SRE executions, and background health checks.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => fetchEvents(true, 0)}
            disabled={loading}
            className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-surface hover:bg-surface-elevated border border-border-subtle text-xs font-medium text-gray-300 hover:text-white transition-all cursor-pointer disabled:opacity-50"
            title="Refresh event stream"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin text-accent' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {/* Dynamic Filter & Search Toolbar (Phase B4 & B5) */}
      <div className="glass-panel rounded-2xl p-5 border border-border-subtle space-y-4">
        <div className="flex flex-col lg:flex-row items-center justify-between gap-4">
          {/* Debounced Search Box (Phase B5) */}
          <div className="relative w-full lg:w-96">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-400" size={15} />
            <input
              type="text"
              placeholder="Search event summaries, actions, keywords..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="w-full bg-surface border border-border-subtle rounded-xl pl-10 pr-9 py-2.5 text-xs text-white placeholder-gray-500 focus:border-accent outline-none transition-colors"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-white transition-colors cursor-pointer"
              >
                <X size={13} />
              </button>
            )}
          </div>

          {/* Filter Dropdowns (Phase B4) */}
          <div className="flex flex-wrap items-center gap-3 w-full lg:w-auto justify-start lg:justify-end">
            {/* Service Filter */}
            <div className="flex items-center gap-1.5 bg-surface border border-border-subtle rounded-xl px-3 py-1.5 text-xs text-gray-300">
              <Layers size={13} className="text-accent shrink-0" />
              <select
                value={selectedConnector}
                onChange={e => setSelectedConnector(e.target.value)}
                className="bg-transparent border-none text-xs text-white focus:outline-none cursor-pointer capitalize pr-2"
              >
                <option value="all" className="bg-surface text-white">All Services</option>
                {connectors.map(c => (
                  <option key={c.id} value={c.id} className="bg-surface text-white">
                    {c.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Event Type Filter */}
            <div className="flex items-center gap-1.5 bg-surface border border-border-subtle rounded-xl px-3 py-1.5 text-xs text-gray-300">
              <Terminal size={13} className="text-accent shrink-0" />
              <select
                value={selectedType}
                onChange={e => setSelectedType(e.target.value)}
                className="bg-transparent border-none text-xs text-white focus:outline-none cursor-pointer pr-2"
              >
                <option value="all" className="bg-surface text-white">All Types</option>
                <option value="action_executed" className="bg-surface text-white">Actions Executed</option>
                <option value="watch_cycle" className="bg-surface text-white">Watch Cycles</option>
                <option value="state_change" className="bg-surface text-white">State Changes</option>
                <option value="health_check" className="bg-surface text-white">Health Checks</option>
                <option value="alert" className="bg-surface text-white">Alerts</option>
              </select>
            </div>

            {/* Severity Filter */}
            <div className="flex items-center gap-1.5 bg-surface border border-border-subtle rounded-xl px-3 py-1.5 text-xs text-gray-300">
              <AlertCircle size={13} className="text-accent shrink-0" />
              <select
                value={selectedSeverity}
                onChange={e => setSelectedSeverity(e.target.value)}
                className="bg-transparent border-none text-xs text-white focus:outline-none cursor-pointer pr-2"
              >
                <option value="all" className="bg-surface text-white">All Severities</option>
                <option value="info" className="bg-surface text-white">Info</option>
                <option value="warning" className="bg-surface text-white">Warning</option>
                <option value="error" className="bg-surface text-white">Error</option>
              </select>
            </div>

            {/* Time Range Filter */}
            <div className="flex items-center gap-1.5 bg-surface border border-border-subtle rounded-xl px-3 py-1.5 text-xs text-gray-300">
              <Clock size={13} className="text-accent shrink-0" />
              <select
                value={selectedTimeRange}
                onChange={e => setSelectedTimeRange(e.target.value)}
                className="bg-transparent border-none text-xs text-white focus:outline-none cursor-pointer pr-2"
              >
                <option value="all" className="bg-surface text-white">All Time</option>
                <option value="1h" className="bg-surface text-white">Last 1 Hour</option>
                <option value="24h" className="bg-surface text-white">Last 24 Hours</option>
                <option value="7d" className="bg-surface text-white">Last 7 Days</option>
                <option value="30d" className="bg-surface text-white">Last 30 Days</option>
              </select>
            </div>

            {/* Clear Filters Button */}
            {isFiltered && (
              <button
                onClick={handleResetFilters}
                className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-surface hover:bg-surface-elevated text-xs font-medium text-rose-400 border border-rose-500/20 hover:border-rose-500/40 transition-colors cursor-pointer"
              >
                <X size={12} /> Clear Filters
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Main Event Feed Section */}
      <div className="space-y-8">
        {loading ? (
          <div className="glass-panel rounded-2xl p-16 flex flex-col items-center justify-center space-y-3 text-center">
            <div className="w-8 h-8 rounded-full border-2 border-accent border-t-transparent animate-spin" />
            <span className="text-xs font-mono text-gray-400">Loading audit history & events...</span>
          </div>
        ) : events.length === 0 ? (
          <div className="glass-panel rounded-2xl p-16 flex flex-col items-center justify-center text-center space-y-3">
            <Clock size={36} className="text-gray-600 mb-1" />
            <h3 className="text-base font-bold text-white">No activity events found</h3>
            <p className="text-xs text-gray-400 max-w-sm">
              {isFiltered
                ? 'No events match your current filter settings. Try adjusting search terms or clearing filters.'
                : 'No activity events recorded yet. Start watching a service to stream events in real time.'}
            </p>
            {isFiltered && (
              <button
                onClick={handleResetFilters}
                className="px-4 py-2 rounded-xl bg-surface hover:bg-surface-elevated text-xs font-medium text-white transition-colors cursor-pointer mt-2"
              >
                Clear All Filters
              </button>
            )}
          </div>
        ) : (
          <div className="space-y-8">
            {groupKeys.map(dayLabel => {
              const dayEvents = groupedEvents[dayLabel];
              return (
                <div key={dayLabel} className="space-y-3">
                  {/* Day Header (Phase B2) */}
                  <div className="flex items-center gap-3">
                    <span className="text-xs font-bold font-mono tracking-wider text-accent uppercase">
                      {dayLabel}
                    </span>
                    <div className="h-px flex-1 bg-border-subtle" />
                    <span className="text-[10px] font-mono text-gray-500">
                      {dayEvents.length} {dayEvents.length === 1 ? 'event' : 'events'}
                    </span>
                  </div>

                  {/* Events in this Day */}
                  <div className="space-y-2.5">
                    {dayEvents.map(ev => {
                      const sev = getSeverityBadge(ev.severity);
                      const SevIcon = sev.icon;
                      const isExpanded = expandedEventId === ev.id;
                      const hasConnector = Boolean(ev.connector && ev.connector !== 'system');

                      return (
                        <motion.div
                          key={ev.id}
                          layout
                          className={`rounded-2xl border transition-all glass-card ${
                            isExpanded
                              ? 'border-accent/40 bg-surface-elevated/80 shadow-lg'
                              : 'border-border-subtle hover:border-border-hover bg-surface/50'
                          }`}
                        >
                          {/* Event Summary Row */}
                          <div
                            onClick={() => setExpandedEventId(isExpanded ? null : ev.id)}
                            className="p-4.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 cursor-pointer select-none"
                          >
                            <div className="flex items-start gap-3.5 flex-1 min-w-0">
                              {/* Severity Icon Badge */}
                              <div className={`p-2.5 rounded-xl border shrink-0 mt-0.5 ${sev.badgeClass}`}>
                                <SevIcon size={16} />
                              </div>

                              <div className="min-w-0 flex-1">
                                <div className="flex items-center gap-2 flex-wrap">
                                  <span className="font-semibold text-sm text-white truncate">
                                    {ev.summary}
                                  </span>

                                  {/* Connector Badge */}
                                  {ev.connector && (
                                    <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-surface border border-border-subtle text-gray-300 font-semibold">
                                      {ev.connector}
                                    </span>
                                  )}

                                  {/* Severity Pill */}
                                  <span className={`text-[9px] font-mono font-bold px-1.5 py-0.5 rounded border uppercase ${sev.badgeClass}`}>
                                    {sev.label}
                                  </span>
                                </div>

                                <div className="flex items-center gap-3 text-[11px] text-gray-400 font-mono mt-1">
                                  <span>Type: {ev.event_type}</span>
                                  {ev.action && (
                                    <span className="text-gray-500">• Action: {ev.action}</span>
                                  )}
                                  {ev.status && (
                                    <span className="text-gray-500">• Status: {ev.status}</span>
                                  )}
                                </div>
                              </div>
                            </div>

                            {/* Right Side: Timestamp & Expand Icon */}
                            <div className="flex items-center gap-3 shrink-0 self-end sm:self-center">
                              <span className="text-xs text-gray-400 font-mono">
                                {formatTime(ev.timestamp)}
                              </span>
                              <div className="p-1 rounded-lg text-gray-400 hover:text-white transition-colors">
                                {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                              </div>
                            </div>
                          </div>

                          {/* Expanded Event Details (Phase B7) */}
                          <AnimatePresence>
                            {isExpanded && (
                              <motion.div
                                initial={{ opacity: 0, height: 0 }}
                                animate={{ opacity: 1, height: 'auto' }}
                                exit={{ opacity: 0, height: 0 }}
                                className="px-5 pb-5 pt-1 border-t border-border-subtle/70 space-y-4"
                              >
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs pt-3">
                                  <div className="space-y-1.5">
                                    <span className="text-[11px] text-gray-500 uppercase font-mono">Event ID</span>
                                    <p className="font-mono text-gray-300 bg-surface px-3 py-1.5 rounded-lg border border-border-subtle text-[11px] truncate">
                                      {ev.id}
                                    </p>
                                  </div>
                                  <div className="space-y-1.5">
                                    <span className="text-[11px] text-gray-500 uppercase font-mono">Full Timestamp</span>
                                    <p className="font-mono text-gray-300 bg-surface px-3 py-1.5 rounded-lg border border-border-subtle text-[11px]">
                                      {ev.timestamp}
                                    </p>
                                  </div>
                                </div>

                                {/* Raw Details / Payload Viewer */}
                                {ev.details && (
                                  <div className="space-y-1.5">
                                    <span className="text-[11px] text-gray-500 uppercase font-mono">Event Details & Metadata</span>
                                    <pre className="p-3.5 rounded-xl bg-surface border border-border-subtle font-mono text-[11px] text-gray-300 overflow-x-auto max-h-56 leading-relaxed">
                                      {JSON.stringify(ev.details, null, 2)}
                                    </pre>
                                  </div>
                                )}

                                {/* Service Navigation Actions (Phase B7) */}
                                <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
                                  <div className="text-[11px] text-gray-500 font-mono flex items-center gap-1.5">
                                    <SlidersHorizontal size={12} />
                                    <span>Source: {ev.connector || 'system'}</span>
                                  </div>

                                  <div className="flex items-center gap-2">
                                    {hasConnector && (
                                      <button
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          setActiveTab('dashboard');
                                        }}
                                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface hover:bg-surface-elevated text-xs text-white border border-border-subtle hover:border-accent/30 transition-all cursor-pointer"
                                      >
                                        <span>View in Dashboard</span>
                                        <ArrowRight size={12} />
                                      </button>
                                    )}

                                    <button
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        openChat({ connectorId: hasConnector ? ev.connector : undefined });
                                      }}
                                      className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-accent hover:bg-accent-light text-xs font-bold text-gray-950 transition-all shadow cursor-pointer"
                                    >
                                      <MessageSquare size={13} />
                                      <span>Investigate with Lear</span>
                                    </button>
                                  </div>
                                </div>
                              </motion.div>
                            )}
                          </AnimatePresence>
                        </motion.div>
                      );
                    })}
                  </div>
                </div>
              );
            })}

            {/* Infinite Scroll / Load More Footer (Phase B6) */}
            {hasMore && (
              <div className="flex flex-col items-center justify-center pt-4 pb-8 space-y-2">
                <button
                  onClick={handleLoadMore}
                  disabled={loadingMore}
                  className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-surface hover:bg-surface-elevated border border-border-subtle hover:border-accent/40 text-xs font-bold text-white transition-all shadow-md cursor-pointer disabled:opacity-50"
                >
                  {loadingMore && <RefreshCw size={13} className="animate-spin text-accent" />}
                  {loadingMore ? 'Loading more events...' : 'Load More Events'}
                </button>
                <span className="text-[11px] font-mono text-gray-500">
                  Showing {events.length} of {total} events
                </span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

