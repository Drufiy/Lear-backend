import { useState, useEffect, useCallback, useRef } from 'react';

export type ConnectorConnectionStatus = 'unconfigured' | 'connecting' | 'connected' | 'error' | 'expired';

export interface UseConnectorStatusReturn {
  status: ConnectorConnectionStatus;
  identity: string | null;
  maskedCredentials: Record<string, string>;
  loading: boolean;
  error: string | null;
  connect: (credentials: Record<string, string>) => Promise<{ success: boolean; message: string; identity?: string }>;
  disconnect: () => Promise<{ success: boolean; message: string }>;
  checkHealth: () => Promise<void>;
}

export function useConnectorStatus(connectorId: string, initialStatus?: string): UseConnectorStatusReturn {
  const [status, setStatus] = useState<ConnectorConnectionStatus>(
    (initialStatus as ConnectorConnectionStatus) || 'unconfigured'
  );
  const [identity, setIdentity] = useState<string | null>(null);
  const [maskedCredentials, setMaskedCredentials] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isMountedRef = useRef(true);

  // Check health and validate credentials without modifying .env
  const checkHealth = useCallback(async () => {
    if (!connectorId) return;
    try {
      const res = await fetch(`/api/connectors/${connectorId}/validate`);
      if (res.ok && isMountedRef.current) {
        const data = await res.json();
        if (data.status === 'connected') {
          setStatus('connected');
          setIdentity(data.identity || null);
          setError(null);
        } else if (data.status === 'expired') {
          setStatus('expired');
          setError(data.message || 'Credentials expired or invalid');
        } else if (data.status === 'unconfigured') {
          setStatus('unconfigured');
        }
      }
    } catch (e: any) {
      if (isMountedRef.current) {
        console.warn(`Health check failed for ${connectorId}:`, e);
      }
    }
  }, [connectorId]);

  // Initial load of connector details & masked credentials
  useEffect(() => {
    isMountedRef.current = true;
    let cancel = false;

    fetch(`/api/connectors/${connectorId}`)
      .then(res => res.json())
      .then(data => {
        if (!cancel && data) {
          if (data.status === 'configured') {
            setStatus('connected');
          } else {
            setStatus('unconfigured');
          }
          setMaskedCredentials(data.masked_credentials || {});
        }
      })
      .catch(err => console.error(`Error loading connector info for ${connectorId}:`, err));

    return () => {
      cancel = true;
      isMountedRef.current = false;
    };
  }, [connectorId]);

  // Periodic 60s health check (Phase D1 & D2)
  useEffect(() => {
    if (status !== 'connected') return;

    const interval = setInterval(() => {
      checkHealth();
    }, 60000); // every 60s

    return () => clearInterval(interval);
  }, [status, checkHealth]);

  // Connect action
  const connect = useCallback(
    async (credentials: Record<string, string>) => {
      setLoading(true);
      setError(null);
      setStatus('connecting');

      try {
        const res = await fetch(`/api/connectors/${connectorId}/connect`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(credentials),
        });

        const data = await res.json();
        if (res.ok && data.success) {
          setStatus('connected');
          setIdentity(data.identity || null);
          // Refresh masked credentials
          const resDetail = await fetch(`/api/connectors/${connectorId}`);
          if (resDetail.ok) {
            const detail = await resDetail.json();
            setMaskedCredentials(detail.masked_credentials || {});
          }
          return { success: true, message: data.message || 'Connected successfully', identity: data.identity };
        } else {
          setStatus('error');
          const errMsg = data.detail || data.message || 'Authentication failed. Verify credentials.';
          setError(errMsg);
          return { success: false, message: errMsg };
        }
      } catch (e: any) {
        setStatus('error');
        const errMsg = e.message || 'Network error reaching API bridge';
        setError(errMsg);
        return { success: false, message: errMsg };
      } finally {
        setLoading(false);
      }
    },
    [connectorId]
  );

  // Disconnect action (Phase C4)
  const disconnect = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`/api/connectors/${connectorId}/disconnect`, {
        method: 'POST',
      });
      const data = await res.json();
      if (res.ok && data.success) {
        setStatus('unconfigured');
        setIdentity(null);
        setMaskedCredentials({});
        return { success: true, message: data.message || 'Disconnected successfully' };
      } else {
        const errMsg = data.detail || data.message || 'Failed to disconnect';
        setError(errMsg);
        return { success: false, message: errMsg };
      }
    } catch (e: any) {
      const errMsg = e.message || 'Network error disconnecting';
      setError(errMsg);
      return { success: false, message: errMsg };
    } finally {
      setLoading(false);
    }
  }, [connectorId]);

  return {
    status,
    identity,
    maskedCredentials,
    loading,
    error,
    connect,
    disconnect,
    checkHealth,
  };
}

export default useConnectorStatus;
