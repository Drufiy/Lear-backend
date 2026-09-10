import { useState, useCallback, useEffect } from 'react';
import useWebSocket, { WebSocketEvent } from './useWebSocket';

export type WatcherState = 'IDLE' | 'STARTING' | 'ACTIVE' | 'DEGRADED' | 'ALERTING' | 'ERROR';

export function useWatcher() {
  const { isConnected, lastEvent } = useWebSocket();
  const [activeWatches, setActiveWatches] = useState<string[]>([]);
  const [events, setEvents] = useState<WebSocketEvent[]>([]);
  const [watcherState, setWatcherState] = useState<WatcherState>('IDLE');

  // Push incoming WS events into local event stream
  useEffect(() => {
    if (lastEvent) {
      setEvents(prev => [lastEvent, ...prev.slice(0, 49)]);
      const type = (lastEvent.event_type || '').toLowerCase();
      const summary = (lastEvent.summary || '').toLowerCase();
      if (type.includes('fail') || type.includes('alarm') || summary.includes('error')) {
        setWatcherState('ALERTING');
      } else if (watcherState === 'IDLE' || watcherState === 'STARTING') {
        setWatcherState('ACTIVE');
      }
    }
  }, [lastEvent]);

  // Update state based on active watches count
  useEffect(() => {
    if (activeWatches.length > 0) {
      if (watcherState === 'IDLE') {
        setWatcherState('ACTIVE');
      }
    } else {
      setWatcherState('IDLE');
    }
  }, [activeWatches.length]);

  const startWatch = useCallback(async (connectorId: string, target: string) => {
    setWatcherState('STARTING');
    try {
      const res = await fetch(`/api/connectors/${connectorId}/watch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target }),
      });
      if (res.ok) {
        const data = await res.json();
        setActiveWatches(prev => [...new Set([...prev, data.watch_id || `${connectorId}:${target}`])]);
        setWatcherState('ACTIVE');
        return true;
      } else {
        const err = await res.json();
        console.error('Watch start failed:', err);
        setWatcherState('ERROR');
        return false;
      }
    } catch (e) {
      console.error('Network error starting watch:', e);
      setWatcherState('ERROR');
      return false;
    }
  }, []);

  const stopWatch = useCallback(async (connectorId: string, target?: string, watchId?: string) => {
    const wid = watchId || (target ? `${connectorId}:${target}` : null);
    try {
      const params = new URLSearchParams();
      if (wid) params.append('watch_id', wid);
      else if (target) params.append('target', target);

      const res = await fetch(`/api/connectors/${connectorId}/watch?${params.toString()}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        setActiveWatches(prev => prev.filter(w => w !== wid));
        return true;
      }
    } catch (e) {
      console.error('Error stopping watch:', e);
    }
    return false;
  }, []);

  return {
    isConnected,
    watcherState,
    activeWatches,
    events,
    startWatch,
    stopWatch,
  };
}

export default useWatcher;
