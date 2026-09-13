import { useEffect, useRef, useState, useCallback } from 'react';

export interface WebSocketEvent {
  watch_id?: string;
  connector?: string;
  event_type: string;
  summary: string;
  raw?: any;
  timestamp: string;
}

export function useWebSocket(url: string = 'ws://127.0.0.1:8000/ws/events') {
  const [isConnected, setIsConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<WebSocketEvent | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<any>(null);
  const reconnectAttemptRef = useRef<number>(0);

  const connect = useCallback(() => {
    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        reconnectAttemptRef.current = 0; // Reset on successful connection
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
        // Exponential backoff: 1s, 2s, 4s, 8s, 16s, max 30s
        const delay = Math.min(1000 * Math.pow(2, reconnectAttemptRef.current), 30000);
        reconnectAttemptRef.current += 1;
        reconnectTimeoutRef.current = setTimeout(connect, delay);
      };

      ws.onerror = () => {
        setIsConnected(false);
        ws.close();
      };
    } catch (e) {
      console.error('WebSocket connection error:', e);
      const delay = Math.min(1000 * Math.pow(2, reconnectAttemptRef.current), 30000);
      reconnectAttemptRef.current += 1;
      reconnectTimeoutRef.current = setTimeout(connect, delay);
    }
  }, [url]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [connect]);

  return { isConnected, lastEvent };
}

export default useWebSocket;
