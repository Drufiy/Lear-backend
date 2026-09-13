import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import Integrations from '../components/Integrations';

interface TestConnector {
  id: string;
  name: string;
  category: string;
  icon: string;
  color: string;
  description: string;
  status: string;
  auth_fields: Array<Record<string, unknown>>;
  docs_url?: string;
  last_verified?: string;
  error?: string;
}

const arbitraryConnectors: TestConnector[] = [
  {
    id: 'nebula-one',
    name: 'Nebula One',
    category: 'Orbital Systems',
    icon: 'cloud',
    color: '#123ABC',
    description: 'Controls arbitrary orbital infrastructure.',
    status: 'healthy',
    docs_url: 'https://example.com/nebula',
    last_verified: '2026-03-04T10:30:00Z',
    auth_fields: [{ key: 'NEBULA_KEY', label: 'Nebula access key', type: 'password', required: true, configured: true, masked_value: 'neb...key' }],
  },
  {
    id: 'signal-two',
    name: 'Signal Two',
    category: 'Telemetry Lab',
    icon: 'bell',
    color: '#E87921',
    description: 'Streams signals from a synthetic provider.',
    status: 'configured',
    auth_fields: [{ key: 'SIGNAL_URL', label: 'Signal endpoint', type: 'text', required: true, configured: true, masked_value: '***' }],
  },
  {
    id: 'mystery-extra',
    name: 'Mystery Extra',
    category: 'Orbital Systems',
    icon: 'not-a-real-lucide-icon',
    color: '#55AA77',
    description: 'An injected connector unknown to the application.',
    status: 'expired',
    error: 'Registry credentials expired',
    auth_fields: [{ key: 'MYSTERY_SECRET', label: 'Mystery secret', type: 'textarea', required: true }],
  },
  {
    id: 'pending-link',
    name: 'Pending Link',
    category: 'Telemetry Lab',
    icon: 'activity',
    color: '#8855CC',
    description: 'A connector still being established.',
    status: 'connecting',
    auth_fields: [],
  },
];

const response = (body: unknown, ok = true, status = 200) => Promise.resolve({ ok, status, json: () => Promise.resolve(body) } as Response);
const listResponse = (connectors: TestConnector[]) => response({ connectors });

const cardFor = (name: string) => screen.getByRole('heading', { name }).closest('[data-testid="connector-card"]') as HTMLElement;

const mockList = (connectors = arbitraryConnectors) => {
  const fetchMock = vi.fn().mockImplementation(() => listResponse(connectors));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('Integrations', () => {
  it('renders every API connector, unique API categories, metadata, statuses, and dynamic counts', async () => {
    const fetchMock = mockList();
    render(<Integrations />);

    expect(await screen.findByText('4 available · 1 connected')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith('/api/connectors');
    expect(screen.getAllByTestId('connector-card')).toHaveLength(arbitraryConnectors.length);
    expect(screen.getAllByRole('heading', { name: 'Orbital Systems' })).toHaveLength(1);
    expect(screen.getAllByRole('heading', { name: 'Telemetry Lab' })).toHaveLength(1);
    expect(screen.getByRole('heading', { name: 'Mystery Extra' })).toBeInTheDocument();

    const nebula = cardFor('Nebula One');
    expect(nebula).toHaveAttribute('data-connector-color', '#123ABC');
    expect(within(nebula).getByText('Controls arbitrary orbital infrastructure.')).toBeInTheDocument();
    expect(within(nebula).getByText('Connected')).toBeInTheDocument();
    expect(within(nebula).getByText(/Last verified/)).toBeInTheDocument();
    expect(within(nebula).getByRole('link', { name: /Docs/ })).toHaveAttribute('href', 'https://example.com/nebula');
    expect(within(nebula).getByTestId('connector-icon')).toHaveAttribute('data-icon-name', 'cloud');
    expect(within(nebula).getByTestId('connector-icon')).toHaveStyle({ color: '#123ABC' });

    expect(within(cardFor('Signal Two')).getByText('Configured, not verified')).toBeInTheDocument();
    expect(within(cardFor('Pending Link')).getByText('Connecting')).toBeInTheDocument();
    expect(within(cardFor('Mystery Extra')).getByText('Connection error')).toBeInTheDocument();
    expect(within(cardFor('Mystery Extra')).getByText('Registry credentials expired')).toBeInTheDocument();
    expect(within(cardFor('Mystery Extra')).getByTestId('connector-icon')).toHaveAttribute('data-icon-resolved', 'circle-help');
  });

  it('uses API auth fields in the inline connect form, then collapses and refreshes after success', async () => {
    const fresh = arbitraryConnectors[0];
    const unconfigured = { ...fresh, status: 'unconfigured', last_verified: undefined, auth_fields: [{ key: 'CUSTOM_TOKEN', label: 'Custom registry token', type: 'password', required: true, help_text: 'Only this injected field is valid.' }] };
    let listCalls = 0;
    const fetchMock = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url === '/api/connectors') {
        listCalls += 1;
        return listResponse(listCalls === 1 ? [unconfigured] : [{ ...unconfigured, status: 'healthy', last_verified: '2026-04-01T00:00:00Z' }]);
      }
      if (url.endsWith('/connect') && options?.method === 'POST') return response({ success: true, status: 'healthy', identity: {} });
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    render(<Integrations />);

    await user.click(await screen.findByRole('button', { name: 'Connect' }));
    const token = screen.getByLabelText(/Custom registry token/);
    expect(screen.getByText('Only this injected field is valid.')).toBeInTheDocument();
    await user.type(token, 'registry-secret');
    await user.click(screen.getByRole('button', { name: 'Validate & Save Credentials' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/connectors/nebula-one/connect', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ CUSTOM_TOKEN: 'registry-secret' }),
    })));
    await waitFor(() => expect(screen.queryByLabelText(/Custom registry token/)).not.toBeInTheDocument());
    expect(screen.getByText('1 available · 1 connected')).toBeInTheDocument();
    expect(listCalls).toBe(2);
  });

  it('keeps a failed connect form open and exposes the API error inline', async () => {
    const connector = { ...arbitraryConnectors[0], status: 'unconfigured', auth_fields: [{ key: 'TOKEN', label: 'Failure token', type: 'password', required: true }] };
    const fetchMock = vi.fn().mockImplementation((url: string) => url === '/api/connectors'
      ? listResponse([connector])
      : response({ success: false, status: 'failed', error: 'Provider rejected the injected token' }, false, 401));
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    render(<Integrations />);

    await user.click(await screen.findByRole('button', { name: 'Connect' }));
    await user.type(screen.getByLabelText(/Failure token/), 'bad');
    await user.click(screen.getByRole('button', { name: 'Validate & Save Credentials' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Provider rejected the injected token');
    expect(screen.getByLabelText(/Failure token/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('opens configure and reconnect forms without duplicating management controls', async () => {
    mockList(arbitraryConnectors.slice(0, 3));
    const user = userEvent.setup();
    render(<Integrations />);

    const configuredCard = cardFor(await screen.findByText('Signal Two').then(() => 'Signal Two'));
    await user.click(within(configuredCard).getByRole('button', { name: 'Configure' }));
    expect(within(configuredCard).getByLabelText(/Signal endpoint/)).toBeInTheDocument();
    expect(within(configuredCard).getAllByRole('button', { name: 'Disconnect' })).toHaveLength(1);
    expect(within(configuredCard).getAllByRole('button', { name: 'Check connection' })).toHaveLength(1);

    const errorCard = cardFor('Mystery Extra');
    await user.click(within(errorCard).getByRole('button', { name: 'Reconnect' }));
    expect(within(errorCard).getByLabelText(/Mystery secret/).tagName).toBe('TEXTAREA');
    expect(within(errorCard).getByRole('button', { name: 'Reconnect' })).toBeInTheDocument();
  });

  it('checks the real endpoint and refreshes the connector list', async () => {
    let listCalls = 0;
    const fetchMock = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url === '/api/connectors') {
        listCalls += 1;
        return listResponse([{ ...arbitraryConnectors[1], status: listCalls === 1 ? 'configured' : 'healthy' }]);
      }
      if (url === '/api/connectors/signal-two/check' && options?.method === 'POST') return response({ success: true, status: 'healthy' });
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    render(<Integrations />);

    await user.click(await screen.findByRole('button', { name: 'Check connection' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/connectors/signal-two/check', { method: 'POST' }));
    expect(await screen.findByText('1 available · 1 connected')).toBeInTheDocument();
    expect(listCalls).toBe(2);
  });

  it('uses an accessible disconnect dialog with cancel, escape, confirm, and focus restoration', async () => {
    let listCalls = 0;
    const fetchMock = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url === '/api/connectors') {
        listCalls += 1;
        return listResponse([{ ...arbitraryConnectors[0], status: listCalls === 1 ? 'healthy' : 'unconfigured' }]);
      }
      if (url === '/api/connectors/nebula-one/disconnect' && options?.method === 'DELETE') return response({ success: true, status: 'unconfigured' });
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    render(<Integrations />);

    const disconnect = await screen.findByRole('button', { name: 'Disconnect' });
    await user.click(disconnect);
    expect(screen.getByRole('dialog')).toHaveAccessibleName('Disconnect Nebula One?');
    expect(screen.getByRole('dialog')).toHaveAccessibleDescription(/Stored credentials will be removed/);
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(disconnect).toHaveFocus();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await user.click(disconnect);
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Disconnect' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/connectors/nebula-one/disconnect', { method: 'DELETE' }));
    expect(await screen.findByText('1 available · 0 connected')).toBeInTheDocument();
    expect(listCalls).toBe(2);
  });

  it('keeps authoritative healthy state after a failed reconfiguration and refresh', async () => {
    const healthy = { ...arbitraryConnectors[0], identity: { account_name: 'Primary <team>' } };
    const fetchMock = vi.fn().mockImplementation((url: string) => url === '/api/connectors'
      ? listResponse([healthy])
      : response({ error: true, message: 'New <token> rejected' }, false, 401));
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    render(<Integrations />);

    const card = cardFor(await screen.findByText('Nebula One').then(() => 'Nebula One'));
    expect(within(card).getByText(/Identity:/).closest('p')).toHaveTextContent('Account Name: Primary <team>');
    await user.click(within(card).getByRole('button', { name: 'Configure' }));
    const token = within(card).getByLabelText(/Nebula access key/);
    await user.click(token);
    await user.type(token, 'replacement');
    await user.click(within(card).getByRole('button', { name: 'Reconnect' }));

    expect(await within(card).findByRole('alert')).toHaveTextContent('New <token> rejected');
    expect(within(card).getByText('Connected')).toBeInTheDocument();
    await user.click(within(card).getByRole('button', { name: 'Configure' }));
    expect(within(card).getByText('Connected')).toBeInTheDocument();
  });

  it('disables every outer control while an inline connection is pending', async () => {
    const connector = { ...arbitraryConnectors[0], status: 'unconfigured', auth_fields: [{ key: 'TOKEN', label: 'Pending token', type: 'password', required: true }] };
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => url === '/api/connectors' ? listResponse([connector]) : new Promise(() => undefined)));
    const user = userEvent.setup();
    render(<Integrations />);

    await user.click(await screen.findByRole('button', { name: 'Connect' }));
    await user.type(screen.getByLabelText(/Pending token/), 'value');
    await user.click(screen.getByRole('button', { name: 'Validate & Save Credentials' }));

    expect(await screen.findByRole('button', { name: 'Authenticating...' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Check connection' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Configure' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Disconnect' })).toBeDisabled();
    expect(screen.getByLabelText(/Pending token/)).toBeDisabled();
  });

  it('polls the list passively, updates a collapsed card to expired, and cleans up its interval', async () => {
    const intervalSpy = vi.spyOn(window, 'setInterval');
    const clearSpy = vi.spyOn(window, 'clearInterval');
    let calls = 0;
    const fetchMock = vi.fn().mockImplementation(() => {
      calls += 1;
      return listResponse([{ ...arbitraryConnectors[0], status: calls === 1 ? 'healthy' : 'expired', error: calls === 1 ? undefined : 'Session expired' }]);
    });
    vi.stubGlobal('fetch', fetchMock);
    const { unmount } = render(<Integrations />);
    await waitFor(() => expect(screen.getByText('Connected')).toBeInTheDocument());
    const pollIndex = intervalSpy.mock.calls.findIndex(([, delay]) => delay === 60_000);
    expect(pollIndex).toBeGreaterThanOrEqual(0);
    const poll = intervalSpy.mock.calls[pollIndex][0] as () => void;
    const intervalId = intervalSpy.mock.results[pollIndex].value;

    await act(async () => {
      poll();
    });
    await waitFor(() => expect(screen.getByText('Connection error')).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/connectors');
    unmount();
    expect(clearSpy).toHaveBeenCalledWith(intervalId);
  });

  it('treats a malformed successful list payload as an error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(response({ connectors: null })));
    render(<Integrations />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Malformed connector list response.');
  });

  it('renders loading skeletons, fetch error with retry, and empty state', async () => {
    let resolveFirst: ((value: Response) => void) | undefined;
    const fetchMock = vi.fn()
      .mockImplementationOnce(() => new Promise<Response>(resolve => { resolveFirst = resolve; }))
      .mockImplementationOnce(() => response({}, false, 503))
      .mockImplementationOnce(() => listResponse([]));
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    const { unmount } = render(<Integrations />);

    expect(screen.getAllByTestId('integration-skeleton')).toHaveLength(6);
    resolveFirst?.({ ok: false, status: 500, json: () => Promise.resolve({}) } as Response);
    expect(await screen.findByRole('alert')).toHaveTextContent('Request failed (500)');
    unmount();

    render(<Integrations />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Request failed (503)');
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByRole('heading', { name: 'No integrations available' })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});
