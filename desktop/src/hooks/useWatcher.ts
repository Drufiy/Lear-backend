import { useState } from 'react';

/**
 * Custom hook to manage the watcher state.
 */
export const useWatcher = () => {
    const [isRunning, setIsRunning] = useState(false);
    const [status, setStatus] = useState('Idle');

    const startWatcher = () => {
        setIsRunning(true);
        setStatus('Watching...');
    };

    const stopWatcher = () => {
        setIsRunning(false);
        setStatus('Idle');
    };

    return {
        isRunning,
        status,
        startWatcher,
        stopWatcher
    };
};