import React from 'react';
import { useWatcher } from '../hooks/useWatcher';
import { useWebSocket } from '../hooks/useWebSocket';

export const WatcherPanel: React.FC = () => {
    const { isRunning, status, startWatcher, stopWatcher } = useWatcher();
    const { isConnected } = useWebSocket();

    return (
        <div className="bg-[#0E131F] border border-gray-800 rounded-lg p-4 flex items-center justify-between text-white">
            <div className="flex items-center space-x-3">
                {/* Animated Radar Pulse Indicator */}
                <div className="relative flex h-3 w-3">
                    {isRunning && (
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    )}
                    <span className={`relative inline-flex rounded-full h-3 w-3 ${isRunning ? 'bg-emerald-500' : 'bg-rose-500'}`}></span>
                </div>
                <div>
                    <h4 className="text-sm font-semibold">Watcher Engine</h4>
                    <p className="text-xs text-gray-400">
                        Status: {status} | WS: {isConnected ? 'Connected' : 'Disconnected'}
                    </p>
                </div>
            </div>

            <div className="flex space-x-2">
                {isRunning ? (
                    <button
                        onClick={stopWatcher}
                        className="px-3 py-1.5 bg-rose-500/20 text-rose-400 border border-rose-500/30 rounded text-xs font-medium hover:bg-rose-500/30 transition-colors"
                    >
                        Stop Watcher
                    </button>
                ) : (
                    <button
                        onClick={startWatcher}
                        className="px-3 py-1.5 bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded text-xs font-medium hover:bg-emerald-500/30 transition-colors"
                    >
                        Start Watcher
                    </button>
                )}
            </div>
        </div>
    );
};