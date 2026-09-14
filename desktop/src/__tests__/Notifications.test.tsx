import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { AppNotification } from '../hooks/useNotifications';

const mocks = vi.hoisted(() => ({
  openChat: vi.fn(),
  markAsRead: vi.fn(),
  markAllAsRead: vi.fn(),
  clearAll: vi.fn(),
  notifications: [] as any[],
}));

vi.mock('../hooks/useNotifications', () => ({
  default: () => ({
    notifications: mocks.notifications,
    unreadCount: mocks.notifications.filter((n: any) => !n.read).length,
    markAsRead: mocks.markAsRead,
    markAllAsRead: mocks.markAllAsRead,
    clearAll: mocks.clearAll,
  }),
}));

vi.mock('../context/LearContext', () => ({
  useLear: () => ({ openChat: mocks.openChat }),
}));

import Notifications from '../components/Notifications';
import NotificationToast from '../components/NotificationToast';

const alert = (over: Partial<AppNotification> = {}): AppNotification => ({
  id: 'n1',
  title: 'CPU spike',
  message: 'cpu above threshold',
  connector: 'kubernetes',
  severity: 'error',
  timestamp: '2026-01-01T00:00:00+00:00',
  read: false,
  ...over,
});

describe('Notifications center', () => {
  afterEach(() => {
    vi.clearAllMocks();
    mocks.notifications = [];
  });

  it('groups unread alerts under New and read alerts under Earlier', () => {
    mocks.notifications = [
      alert({ id: 'n1', title: 'CPU spike', read: false }),
      alert({ id: 'n2', title: 'Recovered', severity: 'success', read: true }),
    ];
    render(<Notifications />);

    expect(screen.getByText('New (1)')).toBeInTheDocument();
    expect(screen.getByText('Earlier (1)')).toBeInTheDocument();
    expect(screen.getByText('CPU spike')).toBeInTheDocument();
    expect(screen.getByText('Recovered')).toBeInTheDocument();
  });

  it('marks a notification read and opens the scoped service view on click', () => {
    mocks.notifications = [alert({ id: 'n1' })];
    render(<Notifications />);

    fireEvent.click(screen.getByText('CPU spike'));

    expect(mocks.markAsRead).toHaveBeenCalledWith('n1');
    expect(mocks.openChat).toHaveBeenCalledWith({ connectorId: 'kubernetes' });
  });

  it('shows an honest empty state instead of demo cards', () => {
    mocks.notifications = [];
    render(<Notifications />);

    expect(screen.getByText(/No notifications found/)).toBeInTheDocument();
    expect(screen.queryByText('New (0)')).not.toBeInTheDocument();
  });
});

describe('NotificationToast severity timing', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it('keeps critical toasts (10s) longer than informational toasts (5s)', () => {
    vi.useFakeTimers();
    const onDismiss = vi.fn();
    render(<NotificationToast toasts={[alert({ id: 'err', severity: 'error' })]} onDismiss={onDismiss} />);

    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(onDismiss).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(onDismiss).toHaveBeenCalledWith('err');
  });

  it('dismisses informational toasts after 5s', () => {
    vi.useFakeTimers();
    const onDismiss = vi.fn();
    render(<NotificationToast toasts={[alert({ id: 'info', severity: 'info' })]} onDismiss={onDismiss} />);

    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(onDismiss).toHaveBeenCalledWith('info');
  });
});
