import { useState, useCallback, useEffect } from 'react';
import useWebSocket, { WebSocketEvent } from './useWebSocket';

export type WatcherState = 'IDLE' | 'STARTING' | 'ACTIVE' | 'DEGRADED' | 'ALERTING' | 'ERROR';

export interface ActiveWatchDetail {
  watch_id: string;
  connector: string;
  target: string;
  interval: number;
  status: 'healthy' | 'degraded' | 'error' | 'paused';
  last_poll_time?: number;
  last_error?: string | null;
}

export function useWatcher() {
  const { isConnected, connectionStatus, lastEvent, sendMessage } = useWebSocket();
  const [activeWatches, setActiveWatches] = useState<string[]>([]);
  const [activeWatchDetails, setActiveWatchDetails] = useState<ActiveWatchDetail[]>([]);
  const [pausedWatches, setPausedWatches] = useState<string[]>([]);
  const [events, setEvents] = useState<WebSocketEvent[]>([]);
  const [watcherState, setWatcherState] = useState<WatcherState>('IDLE');

  // Fetch initial active watches from server
  const refreshActiveWatches = useCallback(async () => {
    try {
      const res = await fetch('/api/watch/active');
      if (res.ok) {
        const data = await res.json();
        const watches: ActiveWatchDetail[] = data.watches || [];
        setActiveWatchDetails(watches);
        const ids = watches.map(w => w.watch_id);
        setActiveWatches(ids);
        const paused = watches.filter(w => w.status === 'paused').map(w => w.watch_id);
        setPausedWatches(paused);
        if (watches.length > 0) {
          const hasError = watches.some(w => w.status === 'error');
          const hasDegraded = watches.some(w => w.status === 'degraded');
          setWatcherState(hasError ? 'ERROR' : (hasDegraded ? 'DEGRADED' : 'ACTIVE'));
        } else {
          setWatcherState('IDLE');
        }
      }
    } catch (e) {
      console.error('Error fetching active watches:', e);
    }
  }, []);

  useEffect(() => {
    refreshActiveWatches();
  }, [refreshActiveWatches]);

  // Push incoming WS events into local event stream without stale closure
  useEffect(() => {
    if (!lastEvent) return;

    setEvents(prev => [lastEvent, ...prev.slice(0, 49)]);
    const type = (lastEvent.event_type || '').toLowerCase();
    const summary = (lastEvent.summary || '').toLowerCase();
    const isCritical = type.includes('fail') || type.includes('alarm') || summary.includes('error') || type.includes('crash');
    const isDegraded = type.includes('spike') || type.includes('warn') || type.includes('degraded');
    const isRecovered = type.includes('recovered') || type.includes('healthy');

    // Functional update prevents any stale closure bug
    setWatcherState(prev => {
      if (isCritical) return 'ALERTING';
      if (isDegraded) return 'DEGRADED';
      if (isRecovered) return 'ACTIVE';
      if (prev === 'IDLE' || prev === 'STARTING') return 'ACTIVE';
      return prev;
    });

    // Update active watch detail status if relevant
    if (lastEvent.watch_id) {
      setActiveWatchDetails(prev =>
        prev.map(w => {
          if (w.watch_id === lastEvent.watch_id) {
            const newStatus = isCritical ? 'error' : (isDegraded ? 'degraded' : 'healthy');
            return { ...w, status: newStatus };
          }
          return w;
        })
      );
    }
  }, [lastEvent]);

  // Synchronize state when active watches change
  useEffect(() => {
    if (activeWatches.length === 0) {
      setWatcherState('IDLE');
    }
  }, [activeWatches.length]);

  const startWatch = useCallback(async (connectorId: string, target: string, interval: number = 5) => {
    setWatcherState('STARTING');
    try {
      const res = await fetch(`/api/connectors/${connectorId}/watch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target, interval }),
      });
      if (res.ok) {
        const data = await res.json();
        const wid = data.watch_id || `${connectorId}:${target}`;
        setActiveWatches(prev => [...new Set([...prev, wid])]);
        setActiveWatchDetails(prev => {
          const filtered = prev.filter(w => w.watch_id !== wid);
          return [
            ...filtered,
            {
              watch_id: wid,
              connector: connectorId,
              target,
              interval,
              status: 'healthy',
            },
          ];
        });
        setPausedWatches(prev => prev.filter(w => w !== wid));
        setWatcherState('ACTIVE');
        return true;
      } else {
        const err = await res.json().catch(() => ({}));
        console.error('Watch start failed:', err);
        setWatcherState(activeWatches.length > 0 ? 'ACTIVE' : 'ERROR');
        return false;
      }
    } catch (e) {
      console.error('Network error starting watch:', e);
      setWatcherState(activeWatches.length > 0 ? 'ACTIVE' : 'ERROR');
      return false;
    }
  }, [activeWatches.length]);

  const stopWatch = useCallback(async (connectorId: string, target?: string, watchId?: string) => {
    const wid = watchId || (target ? `${connectorId}:${target}` : null);
    try {
      // Also notify WebSocket server if connected
      if (wid) {
        sendMessage({ action: 'stop', watch_id: wid, connector_id: connectorId, target });
      }

      const params = new URLSearchParams();
      if (wid) params.append('watch_id', wid);
      else if (target) params.append('target', target);

      const res = await fetch(`/api/connectors/${connectorId}/watch?${params.toString()}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        setActiveWatches(prev => prev.filter(w => w !== wid));
        setActiveWatchDetails(prev => prev.filter(w => w.watch_id !== wid));
        setPausedWatches(prev => prev.filter(w => w !== wid));
        return true;
      }
    } catch (e) {
      console.error('Error stopping watch:', e);
    }
    return false;
  }, [sendMessage]);

  const pauseWatch = useCallback(async (connectorId: string, target?: string, watchId?: string) => {
    const wid = watchId || (target ? `${connectorId}:${target}` : '');
    if (!wid) return false;

    // Send control message over WS
    sendMessage({ action: 'pause', watch_id: wid });

    try {
      const res = await fetch(`/api/connectors/${connectorId}/watch/pause`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ watch_id: wid, target }),
      });
      if (res.ok) {
        setPausedWatches(prev => [...new Set([...prev, wid])]);
        setActiveWatchDetails(prev =>
          prev.map(w => (w.watch_id === wid ? { ...w, status: 'paused' } : w))
        );
        return true;
      }
    } catch (e) {
      console.error('Error pausing watch:', e);
    }
    return false;
  }, [sendMessage]);

  const resumeWatch = useCallback(async (connectorId: string, target?: string, watchId?: string) => {
    const wid = watchId || (target ? `${connectorId}:${target}` : '');
    if (!wid) return false;

    // Send control message over WS
    sendMessage({ action: 'resume', watch_id: wid });

    try {
      const res = await fetch(`/api/connectors/${connectorId}/watch/resume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ watch_id: wid, target }),
      });
      if (res.ok) {
        setPausedWatches(prev => prev.filter(w => w !== wid));
        setActiveWatchDetails(prev =>
          prev.map(w => (w.watch_id === wid ? { ...w, status: 'healthy' } : w))
        );
        return true;
      }
    } catch (e) {
      console.error('Error resuming watch:', e);
    }
    return false;
  }, [sendMessage]);

  return {
    isConnected,
    connectionStatus,
    watcherState,
    activeWatches,
    activeWatchDetails,
    pausedWatches,
    events,
    startWatch,
    stopWatch,
    pauseWatch,
    resumeWatch,
    refreshActiveWatches,
    isRunning: watcherState === 'ACTIVE' || watcherState === 'ALERTING' || watcherState === 'DEGRADED',
  };
}

export default useWatcher;
