import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { mockApi } from '../test/mockApi';
import { renderApp } from '../test/render';
import { DEMO_DASHBOARD, DEMO_USER, demoRequest } from './index';

describe('demo mode', () => {
  it('is off by default: no banner and only the real API is used', async () => {
    const { calls } = mockApi({ 'GET /api/auth/me': { body: { ...DEMO_USER, name: 'Real Person' } }, 'GET /api/dashboard': { body: { ...DEMO_DASHBOARD, totals: { ...DEMO_DASHBOARD.totals, investigations: 0 } } } });
    renderApp('/dashboard');
    await screen.findByRole('heading', { name: 'No investigations yet' });
    expect(screen.queryByText('Demo data, not real telemetry.')).not.toBeInTheDocument();
    expect(document.body).not.toHaveClass('has-demo-banner');
    expect(calls.length).toBeGreaterThan(0);
  });

  it('shows a permanent banner, uses only the demo data and never the network', async () => {
    vi.stubEnv('VITE_DATA_SOURCE', 'demo');
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    renderApp('/dashboard');
    expect(await screen.findByRole('heading', { level: 1, name: 'Dashboard' })).toBeInTheDocument();
    expect(screen.getByRole('status', { name: '' })).toHaveTextContent('Demo data, not real telemetry.');
    expect(document.body).toHaveClass('has-demo-banner');
    expect(await screen.findByText(/DEMO-001/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('has no demo data for pages that were not prepared', async () => {
    await expect(demoRequest('GET', '/api/investigations/1/rarf')).rejects.toMatchObject({ code: 'demo_not_available', status: 404 });
  });

  it('keeps demo values recognisable as invented', () => {
    expect(DEMO_USER.email.endsWith('.invalid')).toBe(true);
    for (const item of DEMO_DASHBOARD.recent_investigations) expect(item.code.startsWith('DEMO-')).toBe(true);
  });
});
