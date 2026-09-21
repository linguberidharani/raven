import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { INVESTIGATION } from '../test/fixtures';
import { mockApi } from '../test/mockApi';
import { caseRoutes } from '../test/routes';
import { renderApp } from '../test/render';

const second = { ...INVESTIGATION, id: 2, code: 'INV-2026-002', title: 'Live VM check', host: null, severity: null, status: 'active', analysis_status: null, counts: { evidence: 0, detections: 0, sessions: 0, timeline_events: 0 } };
const page = (items, extra = {}) => ({ body: { items, total: items.length, page: 1, page_size: 20, ...extra } });
const listCalls = (calls) => calls.filter((call) => call.path === '/api/investigations');

describe('Investigations list', () => {
  it('lists the investigations with the values of the API', async () => {
    const { calls } = mockApi({ ...caseRoutes(), 'GET /api/investigations': page([second, INVESTIGATION]) });
    renderApp('/investigations');
    expect(await screen.findByRole('heading', { level: 1, name: 'Investigations' })).toBeInTheDocument();
    const table = await screen.findByRole('table', { name: 'Investigations' });
    expect(within(table).getAllByRole('columnheader').map((h) => h.textContent)).toEqual(['Case', 'Host', 'Severity', 'Status', 'Analysis', 'Evidence', 'Detections', 'Updated (UTC)']);
    const rows = within(table).getAllByRole('row').slice(1);
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByRole('link', { name: 'Live VM check' })).toHaveAttribute('href', '/investigations/2/evidence');
    expect(rows[0]).toHaveTextContent('INV-2026-002');
    expect(within(rows[0]).getByText('Not analysed')).toBeInTheDocument();
    expect(within(rows[0]).getByText('Active')).toBeInTheDocument();
    expect(within(rows[0]).getByText('None')).toBeInTheDocument();
    expect(within(rows[1]).getByRole('link', { name: 'Boot activity' })).toBeInTheDocument();
    expect(rows[1]).toHaveTextContent('HOST-1');
    expect(within(rows[1]).getByText('High')).toBeInTheDocument();
    expect(within(rows[1]).getByText('Completed')).toBeInTheDocument();
    expect(rows[1]).toHaveTextContent('87');
    expect(rows[1]).toHaveTextContent('2026-09-21 10:16:30 UTC');
    expect(listCalls(calls)[0].url).toBe('/api/investigations?page=1&page_size=20');
  });

  it('filters by status and by severity on the server', async () => {
    const { calls } = mockApi(caseRoutes());
    renderApp('/investigations');
    const user = userEvent.setup();
    await screen.findByRole('table');
    await user.click(screen.getByRole('button', { name: 'Active' }));
    await waitFor(() => expect(listCalls(calls).at(-1).url).toContain('status=active'));
    expect(screen.getByRole('button', { name: 'Active' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'All' })).toHaveAttribute('aria-pressed', 'false');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Filter by severity' }), 'HIGH');
    await waitFor(() => expect(listCalls(calls).at(-1).url).toContain('severity=HIGH'));
    expect(listCalls(calls).at(-1).url).toContain('status=active');
  });

  it('searches after the typing has paused', async () => {
    const { calls } = mockApi(caseRoutes());
    renderApp('/investigations');
    await screen.findByRole('table');
    const before = listCalls(calls).length;
    await userEvent.setup().type(screen.getByRole('searchbox', { name: 'Search investigations' }), 'boot');
    expect(listCalls(calls).length).toBe(before);
    await waitFor(() => expect(listCalls(calls).at(-1).url).toContain('q=boot'), { timeout: 2000 });
    expect(listCalls(calls).length).toBe(before + 1);
  });

  it('says when nothing matches and can clear the filters', async () => {
    let filtered = true;
    const { calls } = mockApi({ ...caseRoutes(), 'GET /api/investigations': (call) => (call.url.includes('status=closed') && filtered ? page([]) : page([INVESTIGATION])) });
    renderApp('/investigations');
    const user = userEvent.setup();
    await screen.findByRole('table');
    await user.click(screen.getByRole('button', { name: 'Closed' }));
    expect(await screen.findByRole('heading', { name: 'No investigation matches these filters' })).toBeInTheDocument();
    filtered = false;
    await user.click(screen.getByRole('button', { name: 'Clear filters' }));
    expect(await screen.findByRole('table')).toBeInTheDocument();
    expect(listCalls(calls).at(-1).url).not.toContain('status=');
  });

  it('is honest when there are no investigations at all', async () => {
    mockApi({ ...caseRoutes(), 'GET /api/investigations': page([]) });
    renderApp('/investigations');
    expect(await screen.findByRole('heading', { name: 'No investigations yet' })).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole('button', { name: 'Create the first investigation' }));
    expect(screen.getByRole('heading', { name: 'New investigation' })).toBeInTheDocument();
  });

  it('pages through a long list', async () => {
    const { calls } = mockApi({ ...caseRoutes(), 'GET /api/investigations': (call) => ({ body: { items: [INVESTIGATION], total: 45, page: call.url.includes('page=2') ? 2 : 1, page_size: 20 } }) });
    renderApp('/investigations');
    const user = userEvent.setup();
    const nav = await screen.findByRole('navigation', { name: 'Pagination' });
    expect(nav).toHaveTextContent('Showing 1 to 20 of 45');
    expect(nav).toHaveTextContent('Page 1 of 3');
    expect(within(nav).getByRole('button', { name: 'Previous' })).toBeDisabled();
    await user.click(within(nav).getByRole('button', { name: 'Next' }));
    await waitFor(() => expect(listCalls(calls).at(-1).url).toContain('page=2'));
    await waitFor(() => expect(screen.getByRole('navigation', { name: 'Pagination' })).toHaveTextContent('Page 2 of 3'));
  });

  it('shows the error and can try again', async () => {
    let attempts = 0;
    mockApi({ ...caseRoutes(), 'GET /api/investigations': () => { attempts += 1; return attempts === 1 ? { status: 500, body: { detail: 'Internal server error', code: 'internal_error', request_id: 'req-7' } } : page([INVESTIGATION]); } });
    renderApp('/investigations');
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('The investigations could not be loaded');
    expect(alert).toHaveTextContent('req-7');
    await userEvent.setup().click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('table')).toBeInTheDocument();
  });
});

describe('creating an investigation', () => {
  const created = { ...INVESTIGATION, id: 9, code: 'INV-2026-009', title: 'New case', host: 'PC-1' };

  it('checks the title before asking the server', async () => {
    const { calls } = mockApi(caseRoutes());
    renderApp('/investigations');
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'New investigation' }));
    await user.click(screen.getByRole('button', { name: 'Create investigation' }));
    const title = screen.getByLabelText('Title');
    expect(title).toHaveAccessibleDescription('Enter a title.');
    expect(title).toHaveFocus();
    expect(calls.some((call) => call.method === 'POST')).toBe(false);
  });

  it('creates it and opens its evidence step', async () => {
    const { calls } = mockApi({ ...caseRoutes(created), 'POST /api/investigations': { status: 201, body: created } });
    renderApp('/investigations');
    const user = userEvent.setup();
    const opener = await screen.findByRole('button', { name: 'New investigation' });
    expect(opener).toHaveAttribute('aria-expanded', 'false');
    await user.click(opener);
    expect(opener).toHaveAttribute('aria-expanded', 'true');
    await user.type(screen.getByLabelText('Title'), '  New case  ');
    await user.type(screen.getByLabelText(/Host/), 'PC-1');
    await user.click(screen.getByRole('button', { name: 'Create investigation' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'New case' })).toBeInTheDocument();
    expect(calls.find((call) => call.method === 'POST' && call.path === '/api/investigations').body).toEqual({ title: 'New case', host: 'PC-1' });
    expect(screen.getByTestId('location')).toHaveTextContent('/investigations/9/evidence');
  });

  it('shows what the server refused', async () => {
    mockApi({ ...caseRoutes(), 'POST /api/investigations': { status: 422, body: { detail: [{ loc: ['body', 'title'], msg: 'title must have 1 to 200 characters' }], code: 'validation_error', request_id: 'r' } } });
    renderApp('/investigations');
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'New investigation' }));
    await user.type(screen.getByLabelText('Title'), 'x');
    await user.click(screen.getByRole('button', { name: 'Create investigation' }));
    await waitFor(() => expect(screen.getByLabelText('Title')).toHaveAccessibleDescription('title must have 1 to 200 characters'));
  });

  it('shows another failure in a banner and can be cancelled', async () => {
    mockApi({ ...caseRoutes(), 'POST /api/investigations': { status: 500, body: { detail: 'Internal server error', code: 'internal_error', request_id: 'r' } } });
    renderApp('/investigations');
    const user = userEvent.setup();
    const opener = await screen.findByRole('button', { name: 'New investigation' });
    await user.click(opener);
    await user.type(screen.getByLabelText('Title'), 'x');
    await user.click(screen.getByRole('button', { name: 'Create investigation' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('The investigation could not be created');
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('heading', { name: 'New investigation' })).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });
});
