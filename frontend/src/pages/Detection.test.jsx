import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { DETECTIONS, INVESTIGATION, RULES, detectionGroup } from '../test/fixtures';
import { mockApi } from '../test/mockApi';
import { caseRoutes } from '../test/routes';
import { renderApp } from '../test/render';

const ruleCard = (ruleId) => within(document.getElementById(`rule-${ruleId}`).closest('article'));
const calls = (all) => all.filter((call) => call.path === '/api/investigations/1/detections');

async function open(routes = {}) {
  const mocked = mockApi(caseRoutes(INVESTIGATION, routes));
  renderApp('/investigations/1/detection');
  await screen.findByRole('heading', { level: 2, name: 'Detection & Correlation' });
  return mocked;
}

describe('Detection: summary and rules', () => {
  it('summarises the groups and the severities', async () => {
    await open();
    expect(await screen.findByText('detection groups from 2 of 3 rules')).toBeInTheDocument();
    const counts = within(screen.getByRole('list', { name: 'Groups by severity' }));
    expect(counts.getByText('High')).toBeInTheDocument();
    expect(counts.getByText('73')).toBeInTheDocument();
    expect(screen.getByText(/does not block or stop any activity/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /View attack reconstruction/ })).toHaveAttribute('href', '/investigations/1/reconstruction');
  });

  it('shows each rule with its steps, window, confidence and groups', async () => {
    await open();
    await screen.findByText('detection groups from 2 of 3 rules');
    const card = ruleCard('RAVEN-R001');
    expect(card.getByText('RAVEN-R001')).toBeInTheDocument();
    expect(card.getByText('High')).toBeInTheDocument();
    const steps = card.getAllByRole('listitem').map((item) => item.textContent);
    expect(steps).toEqual(['1+ Process created', '5+ File created']);
    expect(card.getByText('1 min per process ID')).toBeInTheDocument();
    expect(card.getByText('85%')).toBeInTheDocument();
    expect(card.getByText('Groups found').nextElementSibling).toHaveTextContent('19');
    const stager = ruleCard('RAVEN-R002');
    expect(stager.getByRole('button', { name: 'Show only this rule' })).toBeDisabled();
    expect(stager.getAllByRole('listitem').map((item) => item.textContent)).toEqual(['1+ Process created', '1+ Network connection', '1+ File created']);
  });

  it('marks a disabled rule', async () => {
    await open({ 'GET /api/investigations/1/detections': { body: { ...DETECTIONS, rules: [{ ...RULES[0], enabled: false }, RULES[1], RULES[2]] } } });
    expect(await screen.findByText('Disabled')).toBeInTheDocument();
  });
});

describe('Detection: groups', () => {
  it('explains why a group matched and what it means, as derived text, with the evidence', async () => {
    await open();
    const group = within((await screen.findByText('RAVEN-R001:1001:2026-09-13T08:39:49.545Z')).closest('article'));
    expect(group.getByText('Derived / interpreted')).toBeInTheDocument();
    expect(group.getByText(/process ID 1001/)).toBeInTheDocument();
    expect(group.getByText('For process ID 1001, the recorded events satisfy rule RAVEN-R001.')).toBeInTheDocument();
    expect(group.getByText(/A matching pattern alone does not show the purpose/)).toBeInTheDocument();
    expect(group.getByText('Why this activity is correlated')).toBeInTheDocument();
    const rows = within(group.getByRole('table', { name: 'Steps of the rule for this group' })).getAllByRole('row').slice(1);
    expect(rows.map((row) => row.textContent)).toEqual(['Process created11', 'File created55']);
    expect(group.getByText('2026-09-13 08:39:49.545 UTC to 2026-09-13 08:39:54.545 UTC', { exact: false })).toBeInTheDocument();
    expect(group.getByText(/5\.0 s/)).toBeInTheDocument();
    expect(group.getAllByRole('button', { name: /^Open event 1:/ }).map((b) => b.textContent)).toEqual(['1:1', '1:2', '1:3']);
  });

  it('shows only a few references and the rest on request', async () => {
    const refs = Array.from({ length: 15 }, (_, index) => `1:${index + 1}`);
    await open({ 'GET /api/investigations/1/detections': { body: { ...DETECTIONS, groups: [detectionGroup(1, RULES[2], refs)] } } });
    const group = within((await screen.findByText(detectionGroup(1, RULES[2], refs).group_id)).closest('article'));
    expect(group.getAllByRole('button', { name: /^Open event/ })).toHaveLength(12);
    const more = group.getByRole('button', { name: 'Show all 15 evidence events' });
    await userEvent.setup().click(more);
    expect(group.getAllByRole('button', { name: /^Open event/ })).toHaveLength(15);
    expect(group.getByRole('button', { name: 'Show fewer' })).toHaveAttribute('aria-expanded', 'true');
  });

  it('filters by rule from the rule card and from the list', async () => {
    const { calls: all } = await open();
    const user = userEvent.setup();
    await screen.findByText('detection groups from 2 of 3 rules');
    const card = ruleCard('RAVEN-R003');
    await user.click(card.getByRole('button', { name: 'Show only this rule' }));
    await waitFor(() => expect(calls(all).at(-1).url).toContain('rule=RAVEN-R003'));
    expect(await card.findByRole('button', { name: 'Showing only this rule' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('combobox', { name: 'Filter by rule' })).toHaveValue('RAVEN-R003');
    await user.click(card.getByRole('button', { name: 'Showing only this rule' }));
    await waitFor(() => expect(calls(all).at(-1).url).not.toContain('rule='));
  });

  it('filters by severity and clears the filters', async () => {
    const { calls: all } = await open();
    const user = userEvent.setup();
    await screen.findByText('detection groups from 2 of 3 rules');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Filter by severity' }), 'MEDIUM');
    await waitFor(() => expect(calls(all).at(-1).url).toContain('severity=MEDIUM'));
    await user.click(await screen.findByRole('button', { name: 'Clear filters' }));
    await waitFor(() => expect(calls(all).at(-1).url).not.toContain('severity='));
    expect(screen.queryByRole('button', { name: 'Clear filters' })).not.toBeInTheDocument();
  });

  it('says so when no group matches the filters', async () => {
    await open({ 'GET /api/investigations/1/detections': (call) => ({ body: call.url.includes('severity=LOW') ? { ...DETECTIONS, groups: [], total: 0 } : DETECTIONS }) });
    await screen.findByText('detection groups from 2 of 3 rules');
    await userEvent.setup().selectOptions(screen.getByRole('combobox', { name: 'Filter by severity' }), 'LOW');
    expect(await screen.findByRole('heading', { name: 'No group matches these filters' })).toBeInTheDocument();
  });

  it('says so when no rule matched at all', async () => {
    await open({ 'GET /api/investigations/1/detections': { body: { ...DETECTIONS, groups: [], total: 0, counts: { total_groups: 0, by_rule: {}, by_severity: {} } } } });
    expect(await screen.findByRole('heading', { name: 'No detection group was found' })).toBeInTheDocument();
  });

  it('pages through the groups', async () => {
    const { calls: all } = await open({ 'GET /api/investigations/1/detections': (call) => ({ body: { ...DETECTIONS, total: 45, page: call.url.includes('page=2') ? 2 : 1 } }) });
    const nav = await screen.findByRole('navigation', { name: 'Pagination' });
    expect(nav).toHaveTextContent('Showing 1 to 20 of 45');
    await userEvent.setup().click(within(nav).getByRole('button', { name: 'Next' }));
    await waitFor(() => expect(calls(all).at(-1).url).toContain('page=2'));
  });
});

describe('Detection: other states', () => {
  it('sends an investigation that has not been analysed to the evidence step', async () => {
    await open({ 'GET /api/investigations/1/detections': { body: { analysed: false, rules: RULES, counts: { total_groups: 0, by_rule: {}, by_severity: {} }, groups: [], total: 0, page: 1, page_size: 20 } } });
    expect(await screen.findByRole('heading', { name: 'This investigation has not been analysed yet' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Go to Evidence' })).toHaveAttribute('href', '/investigations/1/evidence');
    expect(screen.queryByText('Detection rules')).not.toBeInTheDocument();
  });

  it('shows the error with a retry', async () => {
    let attempts = 0;
    mockApi(caseRoutes(INVESTIGATION, { 'GET /api/investigations/1/detections': () => { attempts += 1; return attempts === 1 ? { status: 500, body: { detail: 'Internal server error', code: 'internal_error', request_id: 'req-d' } } : { body: DETECTIONS }; } }));
    renderApp('/investigations/1/detection');
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('The detections could not be loaded');
    await userEvent.setup().click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('detection groups from 2 of 3 rules')).toBeInTheDocument();
  });

  it('links back to evidence and on to the reconstruction', async () => {
    await open();
    const main = within(screen.getByRole('main'));
    expect(main.getByRole('link', { name: /Evidence & Log Upload/ })).toHaveAttribute('href', '/investigations/1/evidence');
    expect(main.getByRole('link', { name: /Attack Reconstruction/ })).toHaveAttribute('href', '/investigations/1/reconstruction');
  });
});
