import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { INVESTIGATION, RARF_DOC, RECONSTRUCTION, SESSION } from '../test/fixtures';
import { mockApi } from '../test/mockApi';
import { caseRoutes } from '../test/routes';
import { renderApp } from '../test/render';

afterEach(() => vi.restoreAllMocks());
const rarfCalls = (all) => all.filter((call) => call.path === '/api/investigations/1/rarf');

async function open(routes = {}) {
  const mocked = mockApi(caseRoutes(INVESTIGATION, routes));
  renderApp('/investigations/1/rarf');
  await screen.findByRole('heading', { level: 2, name: 'RARF' });
  await screen.findByRole('heading', { name: 'Structured record' });
  return mocked;
}

describe('RARF: the record', () => {
  it('shows the identity of the record and the counts of what it holds', async () => {
    await open();
    const record = within(screen.getByRole('heading', { name: 'Record' }).closest('section'));
    const value = (label) => record.getByText(label).nextElementSibling;
    expect(value('RARF version')).toHaveTextContent('1.0');
    expect(value('RARF ID')).toHaveTextContent('RARF-RAVEN-SESSION-LAB-R001-1001');
    expect(value('Host')).toHaveTextContent('LAB-HOST');
    expect(value('Session time')).toHaveTextContent('2026-09-13 08:39:49.545 UTC to 2026-09-13 08:43:09.488 UTC');
    expect(value('Severity')).toHaveTextContent('High');
    expect(value('Session confidence')).toHaveTextContent('Not assigned');
    const stat = (label) => screen.getByText(label, { selector: '.stat-label' }).nextElementSibling.textContent;
    expect(stat('Correlation groups')).toBe('3');
    expect(stat('Rules')).toBe('2');
    expect(stat('Timeline events')).toBe('4');
    expect(stat('Impact categories')).toBe('4');
    expect(stat('Raw event references')).toBe('4');
  });
});

describe('RARF: the viewer', () => {
  it('opens the session first and the rest on request', async () => {
    await open();
    const tree = within(screen.getByRole('group', { name: 'Structured document' }));
    expect(tree.getByRole('button', { name: /attack_session/ })).toHaveAttribute('aria-expanded', 'true');
    expect(tree.getByText('computer').parentElement).toHaveTextContent('computer: "LAB-HOST"');
    const detection = tree.getByRole('button', { name: /^detection/ });
    expect(detection).toHaveAttribute('aria-expanded', 'false');
    await userEvent.setup().click(detection);
    expect(tree.getByRole('button', { name: /correlation_groups/ })).toHaveTextContent('[3]');
  });

  it('switches to the JSON text', async () => {
    await open();
    const user = userEvent.setup();
    expect(screen.getByRole('button', { name: 'Structured' })).toHaveAttribute('aria-pressed', 'true');
    await user.click(screen.getByRole('button', { name: 'JSON' }));
    const raw = screen.getByLabelText('RARF as JSON');
    expect(raw.textContent).toContain('"rarf_version": "1.0"');
    expect(JSON.parse(raw.textContent)).toEqual(RARF_DOC);
    expect(screen.getByRole('button', { name: 'JSON' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByRole('group', { name: 'Structured document' })).not.toBeInTheDocument();
  });

  it('copies the JSON', async () => {
    await open();
    const user = userEvent.setup();
    const write = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: write } });
    await user.click(screen.getByRole('button', { name: 'Copy JSON' }));
    expect(write).toHaveBeenCalledTimes(1);
    expect(JSON.parse(write.mock.calls[0][0])).toEqual(RARF_DOC);
    expect(await screen.findByRole('button', { name: 'Copied' })).toBeInTheDocument();
  });

  it('offers the file download from the server', async () => {
    await open();
    const link = screen.getByRole('link', { name: 'Download' });
    expect(link).toHaveAttribute('href', '/api/investigations/1/rarf?download=true');
    expect(link).toHaveAttribute('download');
  });

  it('lists the traceability references and opens the raw record', async () => {
    await open();
    const card = within(screen.getByRole('heading', { name: 'Traceability' }).closest('section'));
    expect(card.getByText('4 raw event references')).toBeInTheDocument();
    expect(card.getAllByRole('button', { name: /^Open event/ }).map((b) => b.textContent)).toEqual(['1:1', '1:2', '1:3', '1:4']);
    await userEvent.setup().click(card.getByRole('button', { name: 'Open event 1:1' }));
    expect(await screen.findByRole('dialog', { name: /Event 1:1/ })).toBeInTheDocument();
  });
});

describe('RARF: sessions and other states', () => {
  it('asks for the chosen session and downloads that one', async () => {
    const other = { ...SESSION, session_id: 'RAVEN-SESSION-OTHER', computer: 'OTHER-HOST' };
    const { calls } = await open({ 'GET /api/investigations/1/reconstruction': { body: { sessions: [SESSION, other] } } });
    await userEvent.setup().selectOptions(await screen.findByLabelText('Attack session'), 'RAVEN-SESSION-OTHER');
    await waitFor(() => expect(rarfCalls(calls).at(-1).url).toContain('session=RAVEN-SESSION-OTHER'));
    await waitFor(() => expect(screen.getByRole('link', { name: 'Download' })).toHaveAttribute('href', '/api/investigations/1/rarf?download=true&session=RAVEN-SESSION-OTHER'));
  });

  it('has no session choice when there is only one', async () => {
    await open({ 'GET /api/investigations/1/reconstruction': { body: RECONSTRUCTION } });
    expect(screen.queryByLabelText('Attack session')).not.toBeInTheDocument();
  });

  it('says so when there is no RARF yet', async () => {
    mockApi(caseRoutes(INVESTIGATION, { 'GET /api/investigations/1/rarf': { status: 404, body: { detail: 'Not analysed.', code: 'not_analysed', request_id: 'r' } } }));
    renderApp('/investigations/1/rarf');
    expect(await screen.findByRole('heading', { name: 'There is no RARF yet' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Go to Evidence' })).toHaveAttribute('href', '/investigations/1/evidence');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows another error with a retry', async () => {
    let attempts = 0;
    mockApi(caseRoutes(INVESTIGATION, { 'GET /api/investigations/1/rarf': () => { attempts += 1; return attempts === 1 ? { status: 404, body: { detail: 'The RARF file is missing. Run the analysis again.', code: 'rarf_not_found', request_id: 'req-r' } } : { body: RARF_DOC }; } }));
    renderApp('/investigations/1/rarf');
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('The RARF could not be loaded');
    expect(alert).toHaveTextContent('Run the analysis again.');
    await userEvent.setup().click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('heading', { name: 'Structured record' })).toBeInTheDocument();
  });

  it('links back to the impact and on to the report', async () => {
    await open();
    const main = within(screen.getByRole('main'));
    expect(main.getByRole('link', { name: /Impact Analysis/ })).toHaveAttribute('href', '/investigations/1/impact');
    expect(main.getByRole('link', { name: /Investigation Report/ })).toHaveAttribute('href', '/investigations/1/report');
  });
});
