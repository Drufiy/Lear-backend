import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import WidgetConfigurator, { type WidgetConfig } from '../components/WidgetConfigurator';

const response = (body: unknown, ok = true, status = 200) =>
  Promise.resolve({ ok, status, json: () => Promise.resolve(body) } as Response);

const widgets: WidgetConfig[] = [
  { id: 'cpu', type: 'gauge', label: 'CPU', metric_keys: ['cpu'], unit: '%' },
  { id: 'net', type: 'line_chart', label: 'Network', metric_keys: ['NetworkIn'], unit: 'bytes' },
];

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('WidgetConfigurator', () => {
  it('renders the current layout with labels, types, and metric keys', () => {
    render(
      <WidgetConfigurator
        connectorId="aws"
        resourceId="i-123"
        widgets={widgets}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />
    );

    expect(screen.getByDisplayValue('CPU')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Network')).toBeInTheDocument();
    expect(screen.getByDisplayValue('cpu')).toBeInTheDocument();
    expect(screen.getByDisplayValue('NetworkIn')).toBeInTheDocument();
    expect(screen.getAllByRole('combobox')).toHaveLength(2);
  });

  it('reorders widgets and removes them before saving', async () => {
    const fetchMock = vi.fn().mockReturnValue(
      response({ widgets: [{ id: 'net', type: 'line_chart', label: 'Network', metric_keys: ['NetworkIn'] }] })
    );
    vi.stubGlobal('fetch', fetchMock);
    const onSaved = vi.fn();
    const user = userEvent.setup();

    render(
      <WidgetConfigurator connectorId="aws" widgets={widgets} onClose={vi.fn()} onSaved={onSaved} />
    );

    // Move the first widget down so Network leads.
    await user.click(screen.getByRole('button', { name: 'Move CPU down' }));
    const labelInputs = screen.getAllByLabelText('Label') as HTMLInputElement[];
    expect(labelInputs[0].value).toBe('Network');
    expect(labelInputs[1].value).toBe('CPU');

    // Remove the now-second widget (CPU).
    await user.click(screen.getByRole('button', { name: 'Remove CPU' }));
    await user.click(screen.getByRole('button', { name: 'Save layout' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/connectors/aws/widgets', expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({
        resource_id: '',
        widgets: [{ id: 'net', type: 'line_chart', label: 'Network', metric_keys: ['NetworkIn'], unit: 'bytes' }],
      }),
    })));
    expect(onSaved).toHaveBeenCalledWith([{ id: 'net', type: 'line_chart', label: 'Network', metric_keys: ['NetworkIn'] }]);
  });

  it('adds a new widget to the draft', async () => {
    vi.stubGlobal('fetch', vi.fn());
    const user = userEvent.setup();
    render(<WidgetConfigurator connectorId="aws" widgets={[]} onClose={vi.fn()} onSaved={vi.fn()} />);

    expect(screen.getByText(/No widgets yet/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Add widget' }));

    expect(screen.getByDisplayValue('New widget')).toBeInTheDocument();
  });

  it('surfaces backend validation rejections inline and does not call onSaved', async () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(response({
      code: 'WIDGET_VALIDATION_FAILED',
      message: 'Invalid widget definitions',
      detail: { rejected: ['cpu: unknown metric keys NotARealMetric'] },
    }, false, 400)));
    const onSaved = vi.fn();
    const user = userEvent.setup();

    render(<WidgetConfigurator connectorId="aws" widgets={widgets} onClose={vi.fn()} onSaved={onSaved} />);
    await user.click(screen.getByRole('button', { name: 'Save layout' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('unknown metric keys NotARealMetric');
    expect(onSaved).not.toHaveBeenCalled();
  });

  it('disables saving when the layout is empty', () => {
    render(<WidgetConfigurator connectorId="aws" widgets={[]} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Save layout' })).toBeDisabled();
  });

  it('edits a widget type through the select', () => {
    render(<WidgetConfigurator connectorId="aws" widgets={widgets} onClose={vi.fn()} onSaved={vi.fn()} />);
    const selects = screen.getAllByRole('combobox') as HTMLSelectElement[];
    fireEvent.change(selects[0], { target: { value: 'bar_chart' } });
    expect(selects[0].value).toBe('bar_chart');
  });
});
