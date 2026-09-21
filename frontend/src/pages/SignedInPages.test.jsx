import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { DASHBOARD, EMPTY_DASHBOARD, HEALTH, INVESTIGATION, USER } from '../test/fixtures';
import { caseRoutes } from '../test/routes';
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

  it('welcomes the analyst by first name', async () => {
    mockApi({ ...me, 'GET /api/dashboard': { body: DASHBOARD } });
    renderApp('/dashboard');
    expect(await screen.findByText('Welcome back, Ada. Your investigations at a glance.')).toBeInTheDocument();
    await waitFor(() => expect(document.querySelector('.stat-grid-icons')).not.toBeNull());
    expect(document.querySelector('.stat-grid-icons').children).toHaveLength(6);
  });

  it('lists the recent investigations with severity and status as text', async () => {
    mockApi({ ...me, 'GET /api/dashboard': { body: DASHBOARD } });
    renderApp('/dashboard');
    const table = await screen.findByRole('table', { name: 'Recent investigations' });
    const rows = within(table).getAllByRole('row').slice(1);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('Waiting for evidence');
    expect(rows[0]).toHaveTextContent('INV-2026-002 \u00b7 0 detections');
    expect(within(rows[0]).getByText('None')).toBeInTheDocument();
    expect(within(rows[0]).getByText('Active')).toBeInTheDocument();
    expect(rows[1]).toHaveTextContent('Boot activity');
    expect(rows[1]).toHaveTextContent('INV-2026-001 \u00b7 87 detections');
    expect(within(rows[1]).getByText('High')).toBeInTheDocument();
    expect(within(rows[1]).getByText('Open')).toBeInTheDocument();
    expect(rows[1]).toHaveTextContent('2026-09-21 10:16:30 UTC');
  });

  it('links the recent investigations to their pages, and has a link to all of them', async () => {
    mockApi({ ...me, 'GET /api/dashboard': { body: DASHBOARD } });
    renderApp('/dashboard');
    const table = await screen.findByRole('table', { name: 'Recent investigations' });
    expect(within(table).getByRole('link', { name: 'Boot activity' })).toHaveAttribute('href', '/investigations/1/evidence');
    expect(within(table).getByRole('link', { name: 'Waiting for evidence' })).toHaveAttribute('href', '/investigations/2/evidence');
    expect(screen.getByRole('link', { name: 'View all' })).toHaveAttribute('href', '/investigations');
    expect(document.title).toBe('Dashboard | RAVEN');
  });

  it('shows the latest attack session with its rules in order, as derived', async () => {
    mockApi({ ...me, 'GET /api/dashboard': { body: DASHBOARD } });
    renderApp('/dashboard');
    const card = within((await screen.findByRole('heading', { name: 'Latest attack session' })).closest('section'));
    expect(card.getByRole('link', { name: 'INV-2026-001' })).toHaveAttribute('href', '/investigations/1/reconstruction');
    expect(card.getByText('High')).toBeInTheDocument();
    expect(card.getByText('2026-09-13 08:39:49 UTC to 08:43:09.488 UTC (3 min 19.9 s)')).toBeInTheDocument();
    const steps = within(card.getByRole('list', { name: 'Rules of the session in the order of their first group' })).getAllByRole('listitem');
    expect(steps.map((step) => step.textContent)).toEqual([
      'R003Sustained File Creation Burst54 groups · first at 08:39:49.545',
      'R001Mass File Modification Burst19 groups · first at 08:39:52.100',
      'R002Process Network File Stager Pattern1 group · first at 08:40:10.000',
    ]);
    expect(card.getByText('Derived / interpreted')).toBeInTheDocument();
  });

  it('says so when there is no attack session yet', async () => {
    mockApi({ ...me, 'GET /api/dashboard': { body: { ...DASHBOARD, latest_session: null } } });
    renderApp('/dashboard');
    expect(await screen.findByText(/No attack session has been reconstructed yet/)).toBeInTheDocument();
  });

  it('draws the cases by severity as a ring with the same numbers as text', async () => {
    mockApi({ ...me, 'GET /api/dashboard': { body: DASHBOARD } });
    renderApp('/dashboard');
    const card = within((await screen.findByRole('heading', { name: 'Cases by severity' })).closest('section'));
    expect(card.getByRole('img', { name: /cases: 2 in total\. High 1, Not analysed 1\./ })).toBeInTheDocument();
    const rows = card.getAllByRole('listitem').map((item) => item.textContent);
    expect(rows).toEqual(['High1', 'Medium0', 'Low0', 'Info0', 'Not analysed1']);
  });

  it('lists the important alerts and links them to the detection step', async () => {
    mockApi({ ...me, 'GET /api/dashboard': { body: DASHBOARD } });
    renderApp('/dashboard');
    const card = within((await screen.findByRole('heading', { name: 'Important alerts' })).closest('section'));
    expect(card.getByRole('link', { name: 'Sustained File Creation Burst' })).toHaveAttribute('href', '/investigations/1/detection');
    expect(card.getByText('INV-2026-001 \u00b7 2026-09-13 08:39:49 UTC \u00b7 10 events')).toBeInTheDocument();
    expect(card.getByText('High')).toBeInTheDocument();
  });

  it('says so when there are no alerts, no activity and no queue', async () => {
    mockApi({ ...me, 'GET /api/dashboard': { body: { ...DASHBOARD, alerts: [], recent_activity: [], evidence_queue: [] } } });
    renderApp('/dashboard');
    expect(await screen.findByText('No high severity correlation group has been found.')).toBeInTheDocument();
    expect(screen.getByText('Nothing has happened yet.')).toBeInTheDocument();
    expect(screen.getByText('Every evidence file is ready for investigation.')).toBeInTheDocument();
  });

  it('shows the investigation status as a bar and a list', async () => {
    mockApi({ ...me, 'GET /api/dashboard': { body: DASHBOARD } });
    renderApp('/dashboard');
    const card = within((await screen.findByRole('heading', { name: 'Investigation status' })).closest('section'));
    expect(card.getByRole('img', { name: 'Investigations by status: Open 1, Active 1, Closed 0' })).toBeInTheDocument();
    expect(card.getAllByRole('listitem').map((item) => item.textContent)).toEqual(['Open1', 'Active1', 'Closed0']);
  });

  it('shows the recent activity with links to the investigations', async () => {
    mockApi({ ...me, 'GET /api/dashboard': { body: DASHBOARD } });
    renderApp('/dashboard');
    const card = within((await screen.findByRole('heading', { name: 'Recent activity' })).closest('section'));
    const items = card.getAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(within(items[0]).getByRole('link', { name: 'Analysis completed for INV-2026-001' })).toHaveAttribute('href', '/investigations/1/evidence');
    expect(items[0]).toHaveTextContent('INV-2026-001 \u00b7 2026-09-21 10:20:00 UTC');
  });

  it('shows the findings by severity as bars', async () => {
    mockApi({ ...me, 'GET /api/dashboard': { body: DASHBOARD } });
    renderApp('/dashboard');
    const list = await screen.findByRole('list', { name: 'Correlation groups by rule severity' });
    expect(within(list).getAllByRole('listitem').map((item) => item.textContent)).toEqual(['High73', 'Medium14', 'Low0', 'Info0']);
  });

  it('shows the evidence processing counts and the files that are not ready', async () => {
    mockApi({ ...me, 'GET /api/dashboard': { body: DASHBOARD } });
    renderApp('/dashboard');
    const card = within((await screen.findByRole('heading', { name: 'Evidence processing' })).closest('section'));
    expect(card.getAllByRole('term').map((t) => t.textContent)).toEqual(['Uploaded', 'Processing', 'Ready', 'Failed']);
    expect(card.getAllByRole('definition').map((d) => d.textContent)).toEqual(['1', '0', '2', '0']);
    expect(card.getByText('pending.evtx')).toBeInTheDocument();
    expect(card.getByText(/INV-2026-002 \u00b7 2026-09-21 11:00:00 UTC/)).toBeInTheDocument();
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
    expect(details.getAllByText('Ada Lovelace')).toHaveLength(2);
    expect(details.getAllByText('ada@example.com')).toHaveLength(2);
    expect(details.getByText('AL', { selector: '.avatar-large' })).toBeInTheDocument();
    expect(details.getByText('Analytical Engines')).toBeInTheDocument();
    expect(details.getByText('2026-09-21 10:15:30 UTC')).toBeInTheDocument();
    await userEvent.setup().click(details.getByRole('button', { name: 'Sign out' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Analyst sign in' })).toBeInTheDocument();
  });

  it('offers to choose an investigation when none is open', async () => {
    mockApi(me);
    renderApp('/profile');
    await screen.findByRole('heading', { level: 1, name: 'Profile' });
    expect(within(screen.getByRole('main')).getByRole('link', { name: 'Choose an investigation' })).toHaveAttribute('href', '/investigations');
  });

  it('shows the current investigation and how to continue it', async () => {
    window.localStorage.setItem('raven.currentInvestigation', '7');
    mockApi(caseRoutes({ ...INVESTIGATION, id: 7, code: 'INV-2026-007' }));
    renderApp('/profile');
    await screen.findByRole('heading', { level: 1, name: 'Profile' });
    const card = within((await screen.findByRole('heading', { name: 'Current investigation' })).closest('section'));
    expect(await card.findByText('INV-2026-007')).toBeInTheDocument();
    expect(card.getByText('Boot activity')).toBeInTheDocument();
    expect(card.getByRole('link', { name: 'Continue investigation' })).toHaveAttribute('href', '/investigations/7/evidence');
    expect(card.getByRole('link', { name: 'Choose another case' })).toHaveAttribute('href', '/investigations');
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
    expect(screen.getByRole('link', { name: 'Replay intro' })).toHaveAttribute('href', '/');
    expect(screen.getByText('All timestamps are shown in UTC.')).toBeInTheDocument();
    expect(window.localStorage.getItem('unrelated')).toBe('keep');
    await user.click(screen.getByRole('button', { name: 'Clear local UI state' }));
    expect(screen.getByRole('main')).toHaveTextContent('There was no local interface state to clear.');
  });
});

describe('planned pages and unknown addresses', () => {
  const three = { ...INVESTIGATION, id: 3, code: 'INV-2026-003' };

  it('opens the first step of an investigation from its address', async () => {
    mockApi(caseRoutes(three));
    renderApp('/investigations/3');
    expect(await screen.findByRole('heading', { level: 2, name: 'Evidence & Log Upload' })).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('/investigations/3/evidence');
  });

  it.each(['/nowhere', '/investigations/abc/timeline', '/investigations/3/unknown', '/investigations/0/report'])('shows page not found for %s', async (path) => {
    mockApi(caseRoutes(three));
    renderApp(path);
    expect(await screen.findByRole('heading', { level: 1, name: 'Page not found' })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('link', { name: 'Go to the dashboard' })).toHaveAttribute('href', '/dashboard'));
  });
});
