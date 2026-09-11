import { useCallback, useEffect, useRef, useState } from 'react';

export type ConnectorState = 'UNCONFIGURED' | 'CONNECTING' | 'CONNECTED' | 'FAILED' | 'WATCHING';

export interface ConnectorResponse {
  success: boolean;
  status: string;
  identity: unknown;
  message?: string;
  error?: string;
  last_verified?: string;
}

interface ConnectorStatus {
  state: ConnectorState;
  identity: unknown;
  error: string | null;
  lastVerified: string | null;
  expired: boolean;
}

const responseMessage = (value: unknown, fallback: string) =>
  typeof value === 'string' && value.length > 0 ? value : fallback;

const isExpired = (status: unknown) => typeof status === 'string' && status.toLowerCase() === 'expired';

const stateFromStatus = (status: unknown, _configured: boolean): ConnectorState => {
  if (typeof status !== 'string') return 'UNCONFIGURED';
  switch (status.toLowerCase()) {
    case 'connected':
    case 'healthy':
      return 'CONNECTED';
    case 'configured':
    case 'unverified':
      return 'UNCONFIGURED';
    case 'watching':
      return 'WATCHING';
    case 'failed':
    case 'error':
    case 'expired':
      return 'FAILED';
    default:
      return 'UNCONFIGURED';
  }
};

const readResponse = async (response: Response): Promise<ConnectorResponse> => {
  let data: Partial<ConnectorResponse> & { message?: unknown } = {};
  try {
    data = await response.json();
  } catch {
    throw new Error(`Request failed (${response.status})`);
  }
  return {
    success: Boolean(data.success),
    status: typeof data.status === 'string' ? data.status : response.ok && data.success ? 'connected' : 'failed',
    identity: data.identity ?? null,
    message: typeof data.message === 'string' ? data.message : undefined,
    error: typeof data.error === 'string' ? data.error : typeof data.message === 'string' ? data.message : undefined,
    last_verified: data.last_verified,
  };
};

export function useConnectorStatus(connectorId: string, initialStatus: string, healthCheckInterval = 60000) {
  const configured = initialStatus.toLowerCase() !== 'unconfigured';
  const [status, setStatus] = useState<ConnectorStatus>({
    state: stateFromStatus(initialStatus, configured),
    identity: null,
    error: isExpired(initialStatus) ? 'Credentials have expired. Reconnect to continue.' : null,
    lastVerified: null,
    expired: isExpired(initialStatus),
  });
  const requestRef = useRef<AbortController | null>(null);

  const abortCurrent = useCallback(() => {
    requestRef.current?.abort();
    requestRef.current = null;
  }, []);

  useEffect(() => {
    abortCurrent();
    const nextConfigured = initialStatus.toLowerCase() !== 'unconfigured';
    setStatus(previous => {
      const nextState = stateFromStatus(initialStatus, nextConfigured);
      const preserveVerified = nextConfigured
        && nextState === 'UNCONFIGURED'
        && (previous.state === 'CONNECTED' || previous.state === 'WATCHING');
      if (preserveVerified) return previous;
      return {
        state: nextState,
        identity: null,
        error: isExpired(initialStatus) ? 'Credentials have expired. Reconnect to continue.' : null,
        lastVerified: null,
        expired: isExpired(initialStatus),
      };
    });
    return abortCurrent;
  }, [abortCurrent, connectorId, initialStatus]);

  const connect = useCallback(async (credentials: Record<string, string>) => {
    abortCurrent();
    const controller = new AbortController();
    requestRef.current = controller;
    setStatus(previous => ({ ...previous, state: 'CONNECTING', error: null, expired: false }));
    try {
      const response = await fetch(`/api/connectors/${encodeURIComponent(connectorId)}/connect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(credentials),
        signal: controller.signal,
      });
      const data = await readResponse(response);
      if (!response.ok || !data.success) {
        setStatus({ state: 'FAILED', identity: null, error: responseMessage(data.error, `Connection failed (${response.status})`), lastVerified: data.last_verified ?? null, expired: isExpired(data.status) });
        return false;
      }
      setStatus({ state: stateFromStatus(data.status, true), identity: data.identity, error: null, lastVerified: data.last_verified ?? null, expired: false });
      return true;
    } catch (error) {
      if (controller.signal.aborted) return false;
      setStatus({ state: 'FAILED', identity: null, error: responseMessage(error instanceof Error ? error.message : null, 'Network error reaching API bridge.'), lastVerified: null, expired: false });
      return false;
    } finally {
      if (requestRef.current === controller) requestRef.current = null;
    }
  }, [abortCurrent, connectorId]);

  const disconnect = useCallback(async () => {
    abortCurrent();
    const controller = new AbortController();
    requestRef.current = controller;
    setStatus(previous => ({ ...previous, state: 'CONNECTING', error: null }));
    try {
      const response = await fetch(`/api/connectors/${encodeURIComponent(connectorId)}/disconnect`, { method: 'DELETE', signal: controller.signal });
      const data = await readResponse(response);
      if (!response.ok || !data.success) {
        setStatus(previous => ({ ...previous, state: 'FAILED', error: responseMessage(data.error, `Disconnect failed (${response.status})`) }));
        return false;
      }
      setStatus({ state: 'UNCONFIGURED', identity: null, error: null, lastVerified: null, expired: false });
      return true;
    } catch (error) {
      if (controller.signal.aborted) return false;
      setStatus(previous => ({ ...previous, state: 'FAILED', error: responseMessage(error instanceof Error ? error.message : null, 'Network error reaching API bridge.') }));
      return false;
    } finally {
      if (requestRef.current === controller) requestRef.current = null;
    }
  }, [abortCurrent, connectorId]);

  const check = useCallback(async () => {
    if (requestRef.current) return false;
    const controller = new AbortController();
    requestRef.current = controller;
    try {
      const response = await fetch(`/api/connectors/${encodeURIComponent(connectorId)}/check`, { method: 'POST', signal: controller.signal });
      const data = await readResponse(response);
      if (!response.ok || !data.success || isExpired(data.status)) {
        setStatus(previous => ({ ...previous, state: 'FAILED', error: responseMessage(data.error, `Connection check failed (${response.status})`), lastVerified: data.last_verified ?? previous.lastVerified, expired: isExpired(data.status) }));
        return false;
      }
      setStatus(previous => ({ ...previous, state: stateFromStatus(data.status, true), identity: data.identity ?? previous.identity, error: null, lastVerified: data.last_verified ?? previous.lastVerified, expired: false }));
      return true;
    } catch (error) {
      if (controller.signal.aborted) return false;
      setStatus(previous => ({ ...previous, state: 'FAILED', error: responseMessage(error instanceof Error ? error.message : null, 'Network error reaching API bridge.'), expired: false }));
      return false;
    } finally {
      if (requestRef.current === controller) requestRef.current = null;
    }
  }, [connectorId]);

  useEffect(() => {
    const poll = async () => {
      if (requestRef.current) return;
      const controller = new AbortController();
      requestRef.current = controller;
      try {
        const response = await fetch(`/api/connectors/${encodeURIComponent(connectorId)}/status`, { signal: controller.signal });
        const data = await readResponse(response);
        if (!response.ok) return;
        setStatus(previous => ({
          state: stateFromStatus(data.status, configured),
          identity: data.identity ?? previous.identity,
          error: data.error ? responseMessage(data.error, 'Connection unavailable') : null,
          lastVerified: data.last_verified ?? previous.lastVerified,
          expired: isExpired(data.status),
        }));
      } catch {
        // Status polling is passive; preserve the last authoritative state on transient network errors.
      } finally {
        if (requestRef.current === controller) requestRef.current = null;
      }
    };
    const timer = window.setInterval(poll, healthCheckInterval);
    return () => window.clearInterval(timer);
  }, [configured, connectorId, healthCheckInterval]);

  return { ...status, connect, disconnect, check };
}
