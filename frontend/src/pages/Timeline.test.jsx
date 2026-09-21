import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { INVESTIGATION, TIMELINE } from '../test/fixtures';
import { mockApi } from '../test/mockApi';
import { caseRoutes } from '../test/routes';
import { renderApp } from '../test/render';

const calls = (all) => all.filter((call) => call.path === '/api/investigations/1/timeline');

async function open(routes = {}) {
  const mocked = mockApi(caseRoutes(INVESTIGATION, routes));
  renderApp('/investigations/1/timeline');
  await screen.findByRole('heading', { level: 2, name: 'Attack Timeline' });
  await screen.findByText(/events? in the timeline|events? match/);
  return mocked;
}
const items = () => screen.getAllByRole('article');

describe('Timeline: the events', () => {
  it('lists the events in order, each as recorded evidence', async () => {
    await open();
    expect(screen.getByRole('status')).toHaveTextContent('3 events in the timeline.');
    const cards = items();
    expect(cards).toHaveLength(3);
    const first = within(cards[0]);
    expect(first.getByText('Process created: C:\\Test\\a.exe (PID 1001)')).toBeInTheDocument();
    expect(first.getByText('Observed evidence')).toBeInTheDocument();
    expect(first.getByText('Process created', { selector: '.tl-type' })).toBeInTheDocument();
    expect(first.getByText('#1')).toBeInTheDocument();
    expect(first.getByText('LAB-HOST')).toBeInTheDocument();
    expect(first.getByText('Sysmon event 1')).toBeInTheDocument();
    expect(first.getByRole('button', { name: 'Open event 1:1' })).toBeInTheDocument();
    expect(within(cards[1]).getByText('Sysmon event 11')).toBeInTheDocument();
    expect(within(cards[2]).getByText('Sysmon event 3')).toBeInTheDocument();
    expect(within(cards[2]).getByText('Network connection', { selector: '.tl-type' })).toBeInTheDocument();
  });

  it('shows the time with milliseconds and a heading for each minute', async () => {
    await open();
    expect(screen.getByText('08:39:49.545')).toBeInTheDocument();
    expect(screen.getByText('08:40:02.250')).toBeInTheDocument();
    const minutes = document.querySelectorAll('.tl-minute');
    expect([...minutes].map((m) => m.textContent)).toEqual(['2026-09-13 08:39 UTC', '2026-09-13 08:40 UTC']);
  });

  it('shows the rules that correlated an event as derived chips, once per rule', async () => {
    await open();
    const cards = items();
    const second = within(cards[1]);
    expect(second.getByText('Correlated by')).toBeInTheDocument();
    expect(second.getByText('R001')).toBeInTheDocument();
    const r003 = second.getByText('R003', { exact: false, selector: '.group-chip' });
    expect(r003).toHaveTextContent('R003 ×2');
    expect(r003).toHaveAttribute('title', expect.stringContaining('RAVEN-R003:1001'));
    expect(second.getByText('Derived / interpreted')).toBeInTheDocument();
    expect(within(cards[2]).queryByText('Correlated by')).not.toBeInTheDocument();
  });

  it('opens the raw record of an event', async () => {
    await open();
    await userEvent.setup().click(within(items()[0]).getByRole('button', { name: 'Open event 1:1' }));
    expect(await screen.findByRole('dialog', { name: /Event 1:1/ })).toBeInTheDocument();
  });
});

describe('Timeline: filters', () => {
  it('filters by event type on the server', async () => {
    const { calls: all } = await open();
    await userEvent.setup().click(screen.getByRole('button', { name: 'Network' }));
    await waitFor(() => expect(calls(all).at(-1).url).toContain('event_type=network_connection'));
    expect(screen.getByRole('button', { name: 'Network' })).toHaveAttribute('aria-pressed', 'true');
    expect(await screen.findByRole('button', { name: 'Clear filters' })).toBeInTheDocument();
  });

  it('filters by rule, choosing from the shipped rules', async () => {
    const { calls: all } = await open();
    const select = screen.getByRole('combobox', { name: 'Filter by rule' });
    expect(within(select).getAllByRole('option').map((o) => o.textContent)).toEqual(['All rules', 'R001 Mass File Modification Burst', 'R002 Process Network File Stager Pattern', 'R003 Sustained File Creation Burst']);
    await userEvent.setup().selectOptions(select, 'RAVEN-R003');
    await waitFor(() => expect(calls(all).at(-1).url).toContain('rule=RAVEN-R003'));
  });

  it('searches the descriptions after the typing has paused', async () => {
    const { calls: all } = await open();
    const before = calls(all).length;
    await userEvent.setup().type(screen.getByRole('searchbox', { name: 'Search event descriptions' }), 'one.txt');
    expect(calls(all).length).toBe(before);
    await waitFor(() => expect(calls(all).at(-1).url).toContain('q=one.txt'), { timeout: 2000 });
  });

  it('says when no event matches, and clears the filters', async () => {
    const { calls: all } = await open({ 'GET /api/investigations/1/timeline': (call) => ({ body: call.url.includes('event_type=file_create') ? { ...TIMELINE, items: [], total: 0 } : TIMELINE }) });
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'File' }));
    expect(await screen.findByRole('heading', { name: 'No event matches these filters' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Clear filters' }));
    expect(await screen.findByText('3 events in the timeline.')).toBeInTheDocument();
    expect(calls(all).at(-1).url).not.toContain('event_type');
  });

  it('tells how many events match while filtering', async () => {
    await open({ 'GET /api/investigations/1/timeline': (call) => ({ body: call.url.includes('event_type=') ? { ...TIMELINE, items: [TIMELINE.items[2]], total: 1 } : TIMELINE }) });
    await userEvent.setup().click(screen.getByRole('button', { name: 'Network' }));
    expect(await screen.findByText('1 event match the filters.')).toBeInTheDocument();
  });
});

describe('Timeline: other states', () => {
  it('sends an investigation without a timeline to the evidence step', async () => {
    mockApi(caseRoutes(INVESTIGATION, { 'GET /api/investigations/1/timeline': { body: { items: [], total: 0, page: 1, page_size: 50 } } }));
    renderApp('/investigations/1/timeline');
    expect(await screen.findByRole('heading', { name: 'There is no timeline yet' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Go to Evidence' })).toHaveAttribute('href', '/investigations/1/evidence');
  });

  it('pages through a long timeline', async () => {
    const { calls: all } = await open({ 'GET /api/investigations/1/timeline': (call) => ({ body: { ...TIMELINE, total: 597, page: call.url.includes('page=2') ? 2 : 1 } }) });
    const nav = screen.getByRole('navigation', { name: 'Pagination' });
    expect(nav).toHaveTextContent('Showing 1 to 50 of 597');
    expect(nav).toHaveTextContent('Page 1 of 12');
    await userEvent.setup().click(within(nav).getByRole('button', { name: 'Next' }));
    await waitFor(() => expect(calls(all).at(-1).url).toContain('page=2'));
  });

  it('shows the error with a retry', async () => {
    let attempts = 0;
    mockApi(caseRoutes(INVESTIGATION, { 'GET /api/investigations/1/timeline': () => { attempts += 1; return attempts === 1 ? { status: 500, body: { detail: 'Internal server error', code: 'internal_error', request_id: 'r' } } : { body: TIMELINE }; } }));
    renderApp('/investigations/1/timeline');
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('The timeline could not be loaded');
    await userEvent.setup().click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('3 events in the timeline.')).toBeInTheDocument();
  });

  it('links back to the reconstruction and on to the impact', async () => {
    await open();
    const main = within(screen.getByRole('main'));
    expect(main.getByRole('link', { name: /Attack Reconstruction/ })).toHaveAttribute('href', '/investigations/1/reconstruction');
    expect(main.getByRole('link', { name: /Impact Analysis/ })).toHaveAttribute('href', '/investigations/1/impact');
  });
});
