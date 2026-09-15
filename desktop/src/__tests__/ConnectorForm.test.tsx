import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ConnectorForm, type ConnectorModel } from '../components/ConnectorForm';

function jsonResponse(body: unknown, init: { ok?: boolean; status?: number } = {}) {
  const { ok = true, status = ok ? 200 : 400 } = init;
  return Promise.resolve({ ok, status, json: () => Promise.resolve(body) } as Response);
}

function mockFetch(handlers: Record<string, () => Promise<Response>>) {
  const fetchMock = vi.fn((url: string, options?: RequestInit) => {
    const key = `${options?.method || 'GET'} ${url}`;
    const handler = handlers[key];
    if (!handler) throw new Error(`Unexpected request: ${key}`);
    return handler();
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const baseConnector: ConnectorModel = {
  id: 'aws',
  name: 'AWS',
  category: 'infrastructure',
  color: '#FF9900',
  description: 'Amazon Web Services',
  status: 'unconfigured',
  auth_fields: [
    { key: 'AWS_ACCESS_KEY_ID', label: 'Access Key ID', type: 'text', required: true },
    { key: 'AWS_SECRET_ACCESS_KEY', label: 'Secret Access Key', type: 'password', required: true },
  ],
};

const configuredConnector: ConnectorModel = {
  ...baseConnector,
  status: 'configured',
  identity: 'AWS Account 123456789012',
  masked_credentials: { AWS_ACCESS_KEY_ID: 'AKIA...MPLE' },
  last_verified: '2026-09-16T09:00:00Z',
};

describe('ConnectorForm', () => {
  it('renders connector details and the unconfigured state with no identity or disconnect control', async () => {
    mockFetch({ 'GET /api/connectors/aws': () => jsonResponse(baseConnector) });
    render(<ConnectorForm connector={baseConnector} />);

    expect(screen.getByText('AWS')).toBeInTheDocument();
    expect(screen.getByText('Amazon Web Services')).toBeInTheDocument();
    expect(await screen.findByText('○ Not Configured')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Validate & Connect' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Disconnect' })).not.toBeInTheDocument();
    expect(screen.getByPlaceholderText('Enter Access Key ID')).toBeInTheDocument();
  });

  it('masks the secret field by default and reveals it on toggle', async () => {
    mockFetch({ 'GET /api/connectors/aws': () => jsonResponse(baseConnector) });
    const user = userEvent.setup();
    render(<ConnectorForm connector={baseConnector} />);

    const secretInput = screen.getByPlaceholderText('Enter Secret Access Key');
    expect(secretInput).toHaveAttribute('type', 'password');

    await user.click(secretInput.parentElement!.querySelector('button')!);
    expect(secretInput).toHaveAttribute('type', 'text');
  });

  it('submits credentials, shows success feedback, and notifies onSuccess', async () => {
    const onSuccess = vi.fn();
    const fetchMock = mockFetch({
      'GET /api/connectors/aws': () => jsonResponse(baseConnector),
      'POST /api/connectors/aws/connect': () =>
        jsonResponse({
          success: true,
          message: 'AWS credentials verified',
          identity: 'AWS Account 123456789012',
          last_verified: '2026-09-16T10:00:00Z',
        }),
    });
    const user = userEvent.setup();
    render(<ConnectorForm connector={baseConnector} onSuccess={onSuccess} />);

    await user.type(screen.getByPlaceholderText('Enter Access Key ID'), 'AKIAEXAMPLE');
    await user.type(screen.getByPlaceholderText('Enter Secret Access Key'), 'secret-value');
    await user.click(screen.getByRole('button', { name: 'Validate & Connect' }));

    expect(await screen.findByText('Authenticated')).toBeInTheDocument();
    expect(screen.getByText('AWS credentials verified')).toBeInTheDocument();
    expect(onSuccess).toHaveBeenCalledWith('aws', expect.objectContaining({ success: true }));
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/connectors/aws/connect',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ AWS_ACCESS_KEY_ID: 'AKIAEXAMPLE', AWS_SECRET_ACCESS_KEY: 'secret-value' }),
      })
    );
  });

  it('shows a connection error and does not call onSuccess when the API rejects credentials', async () => {
    const onSuccess = vi.fn();
    mockFetch({
      'GET /api/connectors/aws': () => jsonResponse(baseConnector),
      'POST /api/connectors/aws/connect': () =>
        jsonResponse({ success: false, message: 'Invalid AWS credentials' }, { ok: false, status: 401 }),
    });
    const user = userEvent.setup();
    render(<ConnectorForm connector={baseConnector} onSuccess={onSuccess} />);

    await user.type(screen.getByPlaceholderText('Enter Access Key ID'), 'bad');
    await user.type(screen.getByPlaceholderText('Enter Secret Access Key'), 'bad');
    await user.click(screen.getByRole('button', { name: 'Validate & Connect' }));

    expect(await screen.findByText('Connection Error')).toBeInTheDocument();
    expect(screen.getByText('Invalid AWS credentials')).toBeInTheDocument();
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it('renders the connected state with identity, masked credential, and a working disconnect flow', async () => {
    const onDisconnect = vi.fn();
    mockFetch({
      'GET /api/connectors/aws': () => jsonResponse(configuredConnector),
      'POST /api/connectors/aws/disconnect': () => jsonResponse({ success: true, message: 'Disconnected successfully' }),
    });
    const user = userEvent.setup();
    render(<ConnectorForm connector={configuredConnector} onDisconnect={onDisconnect} />);

    expect(await screen.findByText('● Connected')).toBeInTheDocument();
    expect(screen.getByText('AWS Account 123456789012')).toBeInTheDocument();
    expect(screen.getByText(/Active: AKIA\.\.\.MPLE/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Update & Re-verify' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Disconnect' }));
    expect(screen.getByText('Are you sure you want to disconnect AWS?')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByText('Are you sure you want to disconnect AWS?')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Disconnect' }));
    await user.click(screen.getByRole('button', { name: 'Yes, Disconnect Service' }));

    expect(await screen.findByText('Disconnected successfully')).toBeInTheDocument();
    expect(onDisconnect).toHaveBeenCalledWith('aws');
  });

  it('lets a connected user manually re-verify via the health check control', async () => {
    const fetchMock = mockFetch({
      'GET /api/connectors/aws': () => jsonResponse(configuredConnector),
      'GET /api/connectors/aws/validate': () =>
        jsonResponse({ status: 'connected', identity: 'AWS Account 123456789012', last_verified: '2026-09-16T11:00:00Z' }),
    });
    render(<ConnectorForm connector={configuredConnector} />);

    await screen.findByText('● Connected');
    await userEvent.click(screen.getByTitle('Verify connection liveness'));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/connectors/aws/validate'));
  });
});
