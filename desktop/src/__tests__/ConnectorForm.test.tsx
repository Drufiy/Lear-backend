import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ConnectorForm, { type ConnectorDefinition } from '../components/ConnectorForm';

const connector: ConnectorDefinition = {
  id: 'github',
  name: 'GitHub',
  status: 'unconfigured',
  auth_fields: [
    { key: 'token', label: 'Personal access token', type: 'password', required: true, help_text: 'Create a token with repo access.' },
    { key: 'host', label: 'Host', type: 'text', required: false, default: 'github.com' },
  ],
};

const response = (body: unknown, ok = true, status = 200) => Promise.resolve({ ok, status, json: () => Promise.resolve(body) } as Response);

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ConnectorForm', () => {
  it('renders registry fields and sends credentials to the connector endpoint', async () => {
    const fetchMock = vi.fn().mockReturnValue(response({ success: true, status: 'connected', identity: { username: 'octocat' }, last_verified: '2026-03-01T12:00:00Z' }));
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    render(<ConnectorForm connector={connector} />);

    await user.type(screen.getByLabelText(/Personal access token/), 'ghp_secret');
    await user.click(screen.getByRole('button', { name: 'Validate & Save Credentials' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/connectors/github/connect', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ token: 'ghp_secret', host: 'github.com' }),
    })));
    expect(await screen.findByText(/Connected · username: octocat/)).toBeInTheDocument();
    expect(screen.getByText(/Last verified 2026-03-01/)).toBeInTheDocument();
  });

  it('shows the exact provider error as escaped React text', async () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(response({ success: false, status: 'failed', identity: null, error: '<b>Bad credentials</b>' }, false, 401)));
    const user = userEvent.setup();
    render(<ConnectorForm connector={connector} />);

    await user.type(screen.getByLabelText(/Personal access token/), 'wrong');
    await user.click(screen.getByRole('button', { name: 'Validate & Save Credentials' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('<b>Bad credentials</b>');
    expect(screen.getByRole('alert').querySelector('b')).toBeNull();
  });

  it('disables inputs while connecting', async () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => undefined)));
    const user = userEvent.setup();
    render(<ConnectorForm connector={connector} />);

    const token = screen.getByLabelText(/Personal access token/);
    await user.type(token, 'token');
    fireEvent.submit(screen.getByRole('button', { name: 'Validate & Save Credentials' }).closest('form')!);

    expect(await screen.findByRole('button', { name: 'Authenticating...' })).toBeDisabled();
    expect(token).toBeDisabled();
  });

  it('supports masked credentials, update, and disconnect', async () => {
    const configuredConnector: ConnectorDefinition = {
      ...connector,
      status: 'configured',
      auth_fields: [{ ...connector.auth_fields[0], masked_value: 'ghp...ret', configured: true }],
    };
    const fetchMock = vi.fn().mockReturnValue(response({ success: true, status: 'unconfigured', identity: null }));
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    render(<ConnectorForm connector={configuredConnector} />);

    const token = screen.getByLabelText(/Personal access token/);
    expect(token).toHaveValue('ghp...ret');
    expect(token).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Update credentials' }));
    await user.click(token);
    expect(token).toHaveValue('');
    await user.click(screen.getByRole('button', { name: 'Disconnect' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/connectors/github/disconnect', expect.objectContaining({ method: 'DELETE' })));
    expect(token).toHaveValue('');
    expect(token).toBeRequired();
    expect(screen.getByRole('button', { name: 'Validate & Save Credentials' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Disconnect' })).not.toBeInTheDocument();
  });

  it('keeps a successful connection visible across parent status rerender', async () => {
    const fetchMock = vi.fn().mockReturnValue(response({ success: true, status: 'healthy', identity: { username: 'octocat' } }));
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    function Parent() {
      const [current, setCurrent] = React.useState(connector);
      return <ConnectorForm connector={current} onStatusChange={(_id, status) => {
        if (status === 'CONNECTED') setCurrent(previous => ({ ...previous, status: 'configured' }));
      }} />;
    }

    render(<Parent />);
    await user.type(screen.getByLabelText(/Personal access token/), 'ghp_secret');
    await user.click(screen.getByRole('button', { name: 'Validate & Save Credentials' }));

    expect(await screen.findByText(/Connected · username: octocat/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Check connection' })).not.toBeInTheDocument();
  });

  it('renders nested identity and treats configured as unverified', () => {
    const configuredConnector: ConnectorDefinition = {
      ...connector,
      status: 'configured',
      auth_fields: [{ ...connector.auth_fields[0], configured: true, masked_value: 'ghp...ret' }],
    };
    render(<ConnectorForm connector={configuredConnector} />);

    expect(screen.queryByText(/^Connected/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Update credentials' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Check connection' })).toBeInTheDocument();
  });

  it('renders textarea and file registry fields as safe controlled text inputs', () => {
    render(<ConnectorForm connector={{
      ...connector,
      auth_fields: [
        { key: 'json', label: 'JSON credential', type: 'textarea', required: false },
        { key: 'path', label: 'Credential path', type: 'file', required: false },
      ],
    }} />);

    expect(screen.getByLabelText('JSON credential').tagName).toBe('TEXTAREA');
    expect(screen.getByLabelText('Credential path')).toHaveAttribute('type', 'text');
  });

  it('uses backend message from the real error envelope', async () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(response({
      error: true,
      code: 'CONNECTOR_AUTH_FAILED',
      message: 'Provider rejected credentials',
      detail: {},
    }, false, 401)));
    const user = userEvent.setup();
    render(<ConnectorForm connector={connector} />);
    await user.type(screen.getByLabelText(/Personal access token/), 'wrong');
    await user.click(screen.getByRole('button', { name: 'Validate & Save Credentials' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Provider rejected credentials');
  });

  it('shows expired state as a reconnect flow', () => {
    render(<ConnectorForm connector={{ ...connector, status: 'expired', auth_fields: [{ ...connector.auth_fields[0], masked_value: 'ghp...ret' }] }} />);

    expect(screen.getByRole('alert')).toHaveTextContent('Credentials have expired');
    expect(screen.getByRole('button', { name: 'Reconnect' })).toBeInTheDocument();
  });
});
