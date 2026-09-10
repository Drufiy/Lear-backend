import { useState } from 'react';

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