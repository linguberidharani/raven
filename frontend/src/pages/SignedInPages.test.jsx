import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { DASHBOARD, EMPTY_DASHBOARD, HEALTH, USER } from '../test/fixtures';
import { mockApi } from '../test/mockApi';
import { renderApp } from '../test/render';

const me = { 'GET /api/auth/me': { body: USER } };

describe('Dashboard', () => {
  it('shows a loading state, then the counted figures', async () => {
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    mockApi({ ...me, 'GET /api/dashboard': async () => { await gate; return { body: DASHBOARD }; } });
    renderApp('/dashboard');
    expect(await screen.findByLabelText('Loading the dashboard')).toHaveAttribute('aria-busy', 'true');
    release();
    const investigations = await screen.findByText('Investigations', { selector: '.stat-label' });
    expect(investigations.nextElementSibling).toHaveTextContent('2');
    const value = (label) => screen.getByText(label, { selector: '.stat-label' }).nextElementSibling.textContent;
    expect(value('Active investigations')).toBe('1');
    expect(value('Open cases')).toBe('1');
    expect(value('Evidence items')).toBe('3');
    expect(value('Attack sessions')).toBe('1');
    expect(value('High severity findings')).toBe('73');
    expect(screen.queryByLabelText('Loading the dashboard')).not.toBeInTheDocument();
  });

  it('lists the recent investigations with severity and status as text', async () => {
    mockApi({ ...me, 'GET /api/dashboard': { body: DASHBOARD } });
    renderApp('/dashboard');
    const card = (await screen.findByRole('heading', { name: 'Recent investigations' })).closest('section');
    const rows = within(card).getAllByRole('listitem');
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('INV-2026-002 Waiting for evidence');
    expect(within(rows[0]).getByText('None')).toBeInTheDocument();
    expect(within(rows[0]).getByText('Active')).toBeInTheDocument();
    expect(rows[1]).toHaveTextContent('INV-2026-001 Boot activity');
    expect(rows[1]).toHaveTextContent('87 detections, 1 evidence file');
    expect(within(rows[1]).getByText('High')).toBeInTheDocument();
    expect(within(rows[1]).getByText('Open')).toBeInTheDocument();
  });

  it('shows the evidence processing status', async () => {
    mockApi({ ...me, 'GET /api/dashboard': { body: DASHBOARD } });
    renderApp('/dashboard');
    const card = (await screen.findByRole('heading', { name: 'Evidence processing status' })).closest('section');
    const terms = within(card).getAllByRole('term').map((t) => t.textContent);
    const values = within(card).getAllByRole('definition').map((d) => d.textContent);
    expect(terms).toEqual(['Uploaded', 'Processing', 'Ready', 'Failed']);
    expect(values).toEqual(['1', '0', '2', '0']);
  });

  it('says so honestly when there is nothing yet', async () => {
    mockApi({ ...me, 'GET /api/dashboard': { body: EMPTY_DASHBOARD } });
    renderApp('/dashboard');
    expect(await screen.findByRole('heading', { name: 'No investigations yet' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Go to Investigations' })).toHaveAttribute('href', '/investigations');
    expect(screen.queryByText('High severity findings')).not.toBeInTheDocument();
  });

  it('shows the error with its request ID and can try again', async () => {
    let attempts = 0;
    mockApi({
      ...me,
      'GET /api/dashboard': () => {
        attempts += 1;
        return attempts === 1 ? { status: 500, body: { detail: 'Internal server error', code: 'internal_error', request_id: 'req-500' } } : { body: DASHBOARD };
      },
    });
    renderApp('/dashboard');
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('The dashboard could not be loaded');
    expect(alert).toHaveTextContent('Internal server error');
    expect(alert).toHaveTextContent('Request ID: req-500');
    await userEvent.setup().click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('Investigations', { selector: '.stat-label' })).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});

describe('Profile', () => {
  it('shows the account and signs out', async () => {
    mockApi({ ...me, 'POST /api/auth/logout': { status: 204 } });
    renderApp('/profile');
    await screen.findByRole('heading', { level: 1, name: 'Profile' });
    const details = within(screen.getByRole('main'));
    expect(details.getByText('Ada Lovelace')).toBeInTheDocument();
    expect(details.getByText('ada@example.com')).toBeInTheDocument();
    expect(details.getByText('Analytical Engines')).toBeInTheDocument();
    expect(details.getByText('2026-09-21 10:15:30 UTC')).toBeInTheDocument();
    await userEvent.setup().click(details.getByRole('button', { name: 'Sign out' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Analyst sign in' })).toBeInTheDocument();
  });

  it('shows a dash for a missing organization', async () => {
    mockApi({ 'GET /api/auth/me': { body: { ...USER, organization: null } } });
    renderApp('/profile');
    await screen.findByRole('heading', { level: 1, name: 'Profile' });
    const term = screen.getByText('Organization', { selector: 'dt' });
    expect(term.nextElementSibling).toHaveTextContent('\u2014');
  });

  it('shows why signing out failed', async () => {
    mockApi({ ...me, 'POST /api/auth/logout': { status: 500, body: { detail: 'Internal server error', code: 'internal_error', request_id: 'r' } } });
    renderApp('/profile');
    await screen.findByRole('heading', { level: 1, name: 'Profile' });
    await userEvent.setup().click(within(screen.getByRole('main')).getByRole('button', { name: 'Sign out' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Signing out failed');
  });
});

describe('Settings', () => {
  it('shows the connection and the backend status', async () => {
    mockApi({ ...me, 'GET /api/health': { body: HEALTH } });
    renderApp('/settings');
    expect(await screen.findByText('raven-api 0.1.0')).toBeInTheDocument();
    expect(screen.getByText('RAVEN backend (real data)')).toBeInTheDocument();
    expect(screen.getByText('Correlation rules loaded').nextElementSibling).toHaveTextContent('3');
    expect(screen.getByText('RARF version').nextElementSibling).toHaveTextContent('1.0');
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });

  it('shows an error when the backend status cannot be read', async () => {
    mockApi({ ...me, 'GET /api/health': { status: 503, body: { detail: 'Degraded', code: 'degraded', request_id: 'r' } } });
    renderApp('/settings');
    expect(await screen.findByRole('alert')).toHaveTextContent('The backend status could not be read');
  });

  it('clears the local interface state and says how much', async () => {
    mockApi({ ...me, 'GET /api/health': { body: HEALTH } });
    window.localStorage.setItem('raven.sidebar', 'x');
    window.localStorage.setItem('unrelated', 'keep');
    renderApp('/settings');
    const user = userEvent.setup();
    await screen.findByText('raven-api 0.1.0');
    await user.click(screen.getByRole('button', { name: 'Clear local UI state' }));
    expect(screen.getByRole('main')).toHaveTextContent('Cleared 1 stored item.');
    expect(window.localStorage.getItem('unrelated')).toBe('keep');
    await user.click(screen.getByRole('button', { name: 'Clear local UI state' }));
    expect(screen.getByRole('main')).toHaveTextContent('There was no local interface state to clear.');
  });
});

describe('planned pages and unknown addresses', () => {
  it('opens the first step of an investigation from its address', async () => {
    mockApi(me);
    renderApp('/investigations/3');
    expect(await screen.findByRole('heading', { level: 1, name: 'Evidence & Log Upload' })).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('/investigations/3/evidence');
  });

  it('says plainly which screens are not built yet and names their API', async () => {
    mockApi(me);
    renderApp('/investigations/3/impact');
    expect(await screen.findByRole('heading', { name: 'This screen is not built yet' })).toBeInTheDocument();
    expect(screen.getByText('GET /api/investigations/3/impact')).toBeInTheDocument();
    const crumbs = within(screen.getByRole('navigation', { name: 'Breadcrumb' })).getAllByRole('listitem');
    expect(crumbs.map((item) => item.textContent)).toEqual(['Investigations', 'Investigation 3', 'Impact Analysis']);
    expect(crumbs[2].firstChild).toHaveAttribute('aria-current', 'page');
  });

  it('shows the investigations page as not built yet', async () => {
    mockApi(me);
    renderApp('/investigations');
    expect(await screen.findByRole('heading', { level: 1, name: 'Investigations' })).toBeInTheDocument();
    expect(screen.getByText('POST /api/investigations')).toBeInTheDocument();
  });

  it.each(['/nowhere', '/investigations/abc/timeline', '/investigations/3/unknown', '/investigations/0/report'])('shows page not found for %s', async (path) => {
    mockApi(me);
    renderApp(path);
    expect(await screen.findByRole('heading', { level: 1, name: 'Page not found' })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('link', { name: 'Go to the dashboard' })).toHaveAttribute('href', '/dashboard'));
  });
});
