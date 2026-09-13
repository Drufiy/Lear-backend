import { useEffect, useRef, useState, useCallback } from 'react';

export interface WebSocketEvent {
  watch_id?: string;
  connector?: string;
  event_type: string;
  summary: string;
  raw?: any;
  timestamp: string;
}

export type ConnectionStatus = 'connected' | 'connecting' | 'reconnecting' | 'disconnected';

export function useWebSocket(url: string = 'ws://127.0.0.1:8000/ws/events') {
  const [isConnected, setIsConnected] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('connecting');
  const [lastEvent, setLastEvent] = useState<WebSocketEvent | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<any>(null);
  const retryCountRef = useRef(0);

  const connect = useCallback(() => {
    try {
      if (wsRef.current && (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING)) {
        return;
      }

      setConnectionStatus(retryCountRef.current > 0 ? 'reconnecting' : 'connecting');
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        setConnectionStatus('connected');
        retryCountRef.current = 0; // Reset exponential backoff on successful handshake
      };

      ws.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data);
          if (parsed && parsed.events && Array.isArray(parsed.events)) {
            parsed.events.forEach((ev: WebSocketEvent) => setLastEvent(ev));
          } else if (parsed.event_type) {
            setLastEvent(parsed);
          }
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e);
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        setConnectionStatus('reconnecting');
        // Exponential backoff: 1s, 2s, 4s, 8s, 16s, capped at 30s
        const delay = Math.min(1000 * Math.pow(2, retryCountRef.current), 30000);
        retryCountRef.current += 1;
        reconnectTimeoutRef.current = setTimeout(connect, delay);
      };

      ws.onerror = () => {
        setIsConnected(false);
        setConnectionStatus('disconnected');
        try {
          ws.close();
        } catch {}
      };
    } catch (e) {
      console.error('WebSocket connection error:', e);
      setIsConnected(false);
      setConnectionStatus('disconnected');
      const delay = Math.min(1000 * Math.pow(2, retryCountRef.current), 30000);
      retryCountRef.current += 1;
      reconnectTimeoutRef.current = setTimeout(connect, delay);
    }
  }, [url]);

  const sendMessage = useCallback((msg: any): boolean => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      try {
        const payload = typeof msg === 'string' ? msg : JSON.stringify(msg);
        wsRef.current.send(payload);
        return true;
      } catch (e) {
        console.error('Failed to send WebSocket message:', e);
      }
    }
    return false;
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [connect]);

  return { isConnected, connectionStatus, lastEvent, sendMessage };
}

export default useWebSocket;
