import { useState, useEffect, useCallback } from 'react';
import useWebSocket from './useWebSocket';

export interface AppNotification {
  id: string;
  title: string;
  message: string;
  connector?: string;
  severity: 'info' | 'warning' | 'error' | 'success';
  timestamp: string;
  read: boolean;
}

export function useNotifications() {
  const { lastEvent } = useWebSocket();
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const [toasts, setToasts] = useState<AppNotification[]>([]);

  // Fetch initial notifications from API
  const fetchNotifications = useCallback(async () => {
    try {
      const res = await fetch('/api/notifications');
      if (res.ok) {
        const data = await res.json();
        if (data.notifications && Array.isArray(data.notifications)) {
          setNotifications(data.notifications);
        }
      }
    } catch (e) {
      console.error('Error fetching notifications:', e);
    }
  }, []);

  useEffect(() => {
    fetchNotifications();
  }, [fetchNotifications]);

  // Handle incoming live events from watcher
  useEffect(() => {
    if (!lastEvent) return;

    const eventType = (lastEvent.event_type || '').toLowerCase();
    const summary = lastEvent.summary || lastEvent.event_type || 'Watcher Event';

    let sev: 'info' | 'warning' | 'error' | 'success' = 'info';
    if (eventType.includes('fail') || eventType.includes('error') || eventType.includes('crash')) {
      sev = 'error';
    } else if (eventType.includes('alarm') || eventType.includes('spike') || eventType.includes('warn') || eventType.includes('degraded')) {
      sev = 'warning';
    } else if (eventType.includes('success') || eventType.includes('deploy') || eventType.includes('healthy')) {
      sev = 'success';
    }

    const newNotif: AppNotification = {
      id: `live_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
      title: summary,
      message: `${lastEvent.event_type} on ${lastEvent.watch_id || lastEvent.connector || 'infrastructure'}`,
      connector: lastEvent.connector,
      severity: sev,
      timestamp: lastEvent.timestamp || new Date().toISOString(),
      read: false,
    };

    setNotifications(prev => [newNotif, ...prev.slice(0, 99)]);
    setToasts(prev => [newNotif, ...prev.slice(0, 4)]);
  }, [lastEvent]);

  const dismissToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  // Client-side toast for actions that fail synchronously (a rejected
  // connect/watch/disconnect fetch) -- distinct from the websocket-driven
  // watcher events above. Found live: a failing action (e.g. clicking Watch
  // on an unconfigured connector, which the backend correctly 500s) produced
  // zero user-visible feedback -- the toast pipeline only had a source for
  // live watcher events, none for "this button's own API call just failed."
  // Does not add to the persisted `notifications` history/badge, only the
  // ephemeral toast strip -- this is transient UI feedback, not an
  // infrastructure event worth remembering after the session.
  const pushToast = useCallback((toast: Omit<AppNotification, 'id' | 'timestamp' | 'read'>) => {
    const newToast: AppNotification = {
      ...toast,
      id: `local_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
      timestamp: new Date().toISOString(),
      read: false,
    };
    setToasts(prev => [newToast, ...prev.slice(0, 4)]);
  }, []);

  const markAsRead = useCallback(async (id: string) => {
    setNotifications(prev =>
      prev.map(n => (n.id === id ? { ...n, read: true } : n))
    );
    try {
      await fetch(`/api/notifications/${id}/read`, { method: 'POST' });
    } catch (e) {
      console.error('Error marking notification as read:', e);
    }
  }, []);

  const markAllAsRead = useCallback(() => {
    setNotifications(prev => prev.map(n => ({ ...n, read: true })));
  }, []);

  const clearAll = useCallback(async () => {
    setNotifications([]);
    setToasts([]);
    try {
      await fetch('/api/notifications', { method: 'DELETE' });
    } catch (e) {
      console.error('Error clearing notifications:', e);
    }
  }, []);

  const unreadCount = notifications.filter(n => !n.read).length;

  return {
    notifications,
    toasts,
    unreadCount,
    dismissToast,
    pushToast,
    markAsRead,
    markAllAsRead,
    clearAll,
    refresh: fetchNotifications,
  };
}

export default useNotifications;
