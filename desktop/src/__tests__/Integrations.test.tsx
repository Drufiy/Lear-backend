import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import Integrations from '../components/Integrations';
import type { ConnectorModel } from '../components/ConnectorForm';

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

const connectorA: ConnectorModel = {
  id: 'aws',
  name: 'AWS',
  category: 'infrastructure',
  color: '#FF9900',
  description: 'Amazon Web Services',
  status: 'configured',
  identity: 'AWS Account 123456789012',
  last_verified: '2026-09-16T09:00:00Z',
  auth_fields: [{ key: 'AWS_ACCESS_KEY_ID', label: 'Access Key ID', type: 'text', required: true }],
  masked_credentials: { AWS_ACCESS_KEY_ID: 'AKIA...MPLE' },
};

const connectorB: ConnectorModel = {
  id: 'github',
  name: 'GitHub',
  category: 'cicd',
  color: '#333333',
  description: 'Source control and CI',
  status: 'unconfigured',
  auth_fields: [{ key: 'GITHUB_TOKEN', label: 'Personal Access Token', type: 'password', required: true }],
};

const connectorC: ConnectorModel = {
  id: 'snyk',
  name: 'Snyk',
  category: 'security',
  color: '#4C4A73',
  description: 'Security scanning',
  status: 'expired',
  auth_fields: [{ key: 'SNYK_API_TOKEN', label: 'API Token', type: 'password', required: true }],
};

describe('Integrations', () => {
  it('renders connectors grouped by category with status badges, identity, and verification timestamps', async () => {
    mockFetch({ 'GET /api/connectors': () => jsonResponse({ connectors: [connectorA, connectorB, connectorC] }) });
    render(<Integrations />);

    expect(await screen.findByText('1 / 3 Active')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /infrastructure/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /cicd/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /security/ })).toBeInTheDocument();

    expect(screen.getByText('● Configured')).toBeInTheDocument();
    expect(screen.getByText('○ Not Configured')).toBeInTheDocument();
    expect(screen.getByText('▲ Expired')).toBeInTheDocument();

    expect(screen.getByText('AWS Account 123456789012')).toBeInTheDocument();
    expect(screen.getByText(/Verified:/)).toBeInTheDocument();
    expect(screen.getAllByText('Not checked this session')).toHaveLength(2);
  });

  it('filters connectors by search text and by status tab', async () => {
    mockFetch({ 'GET /api/connectors': () => jsonResponse({ connectors: [connectorA, connectorB, connectorC] }) });
    const user = userEvent.setup();
    render(<Integrations />);
    await screen.findByText('AWS');

    await user.type(screen.getByPlaceholderText('Search integrations...'), 'git');
    expect(screen.getByText('GitHub')).toBeInTheDocument();
    expect(screen.queryByText('AWS')).not.toBeInTheDocument();

    await user.clear(screen.getByPlaceholderText('Search integrations...'));
    await user.click(screen.getByRole('button', { name: 'Configured (1)' }));
    expect(screen.getByText('AWS')).toBeInTheDocument();
    expect(screen.queryByText('GitHub')).not.toBeInTheDocument();
    expect(screen.queryByText('Snyk')).not.toBeInTheDocument();
  });

  it('connects an unconfigured integration inline and refreshes the list on success', async () => {
    let listCalls = 0;
    const fetchMock = vi.fn((url: string, options?: RequestInit) => {
      const method = options?.method || 'GET';
      if (url === '/api/connectors') {
        listCalls += 1;
        return jsonResponse({
          connectors: [
            listCalls === 1
              ? connectorB
              : { ...connectorB, status: 'configured', identity: 'octocat', last_verified: '2026-09-16T12:00:00Z' },
          ],
        });
      }
      if (url === '/api/connectors/github' && method === 'GET') return jsonResponse(connectorB);
      if (url === '/api/connectors/github/connect' && method === 'POST') {
        return jsonResponse({ success: true, message: 'GitHub token verified', identity: 'octocat' });
      }
      throw new Error(`Unexpected request: ${method} ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    render(<Integrations />);

    await user.click(await screen.findByRole('button', { name: 'Connect' }));
    await user.type(screen.getByPlaceholderText('Enter Personal Access Token'), 'ghp_example');
    await user.click(screen.getByRole('button', { name: 'Validate & Connect' }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith('/api/connectors/github/connect', expect.objectContaining({ method: 'POST' }))
    );
    await waitFor(() => expect(screen.queryByPlaceholderText('Enter Personal Access Token')).not.toBeInTheDocument());
    expect(await screen.findByText('GitHub token verified')).toBeInTheDocument();
    expect(listCalls).toBe(2);
  });

  it('runs a quick health check from the collapsed card', async () => {
    const fetchMock = vi.fn((url: string) => {
      if (url === '/api/connectors') return jsonResponse({ connectors: [connectorA] });
      if (url === '/api/connectors/aws/validate') {
        return jsonResponse({
          status: 'connected',
          valid: true,
          identity: 'AWS Account 123456789012',
          message: 'Active & Validated',
          last_verified: '2026-09-16T13:00:00Z',
        });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    render(<Integrations />);

    await user.click(await screen.findByRole('button', { name: 'Check' }));
    expect(await screen.findByText('Active & Validated')).toBeInTheDocument();
  });

  it('disconnects a configured integration from the collapsed card without a full reload', async () => {
    const fetchMock = vi.fn((url: string, options?: RequestInit) => {
      if (url === '/api/connectors') return jsonResponse({ connectors: [connectorA] });
      if (url === '/api/connectors/aws/disconnect' && options?.method === 'POST') return jsonResponse({ success: true });
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    render(<Integrations />);

    await screen.findByText('AWS');
    await user.click(screen.getByTitle('Disconnect AWS'));
    expect(screen.getByText(/Disconnect AWS\? This will remove credentials and stop watches\./)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Yes, Disconnect' }));

    expect(await screen.findByText('Disconnected successfully')).toBeInTheDocument();
    expect(screen.getByText('○ Not Configured')).toBeInTheDocument();
  });

  it('shows an empty state when no connector matches the active filters', async () => {
    mockFetch({ 'GET /api/connectors': () => jsonResponse({ connectors: [connectorA] }) });
    const user = userEvent.setup();
    render(<Integrations />);

    await screen.findByText('AWS');
    await user.type(screen.getByPlaceholderText('Search integrations...'), 'does-not-exist');

    expect(await screen.findByText('No integrations found')).toBeInTheDocument();
    expect(screen.getByText(/No services match your search/)).toBeInTheDocument();
  });
});
