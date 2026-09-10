import { useState, useCallback } from 'react';
import io from 'socket.io-client';
// Force TS Server reload
interface WebSocketMessage {
    type: string;
    date: any;
    timestamp: string;
}

export function useWebSocket(url: string = 'ws://localhost:8000/ws/events') {
    const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
    const [isConnected, setIsConnected] = useState(false);
    const [error, setError] = useState<Error | null>(null);

    const startListening = useCallback(() => {
        const socket = io(url, {
            transports: ['websocket']
        })

        socket.on('connect', () => {
            setIsConnected(true);
            setError(null);
        })

        socket.on('message', (data: WebSocketMessage) => {
            setLastMessage(data);
        })

        socket.on('error', (err) => {
            setError(err);
            setIsConnected(false);
        })

        socket.on('disconnect', () => {
            setIsConnected(false);
        });

        return () => {
            socket.off('connect');
            socket.off('message');
            socket.off('error');
            socket.off('disconnect');
        }
    }, [url]);

    return {
        lastMessage,
        isConnected,
        error,
        startListening
    };
};