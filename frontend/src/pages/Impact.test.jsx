import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, expect, it } from 'vitest';
import { IMPACT, INVESTIGATION } from '../test/fixtures';
import { mockApi } from '../test/mockApi';
import { caseRoutes } from '../test/routes';
import { renderApp } from '../test/render';

// The chart library is large and slow to load on some machines; the page tests only need its text alternative.
vi.mock('../components/ActivityChart', async () => {
  const React = await import('react');
  return {
    default: ({ buckets, bucketSeconds }) =>
      React.createElement('div', { role: 'img', 'aria-label': `Events over time in buckets of ${bucketSeconds} seconds, by event type. The data is also available as a table.` }, `${buckets.length} buckets`),
  };
});


async function open(routes = {}) {
  const mocked = mockApi(caseRoutes(INVESTIGATION, routes));
  renderApp('/investigations/1/impact');
  await screen.findByRole('heading', { level: 2, name: 'Impact Analysis' });
  await screen.findByRole('heading', { name: 'Observed impact' });
  return mocked;
}
const observed = (name) => within(document.getElementById(`observed-${name}`).closest('article'));

describe('Impact: observed impact', () => {
  it('shows what the events record for each category, as observed', async () => {
    await open();
    expect(screen.getAllByText('Observed evidence').length).toBeGreaterThan(0);
    const files = observed('files_affected');
    expect(files.getByText('558')).toBeInTheDocument();
    expect(files.getByText('1 computer, 3 users, 16 processes')).toBeInTheDocument();
    expect(files.queryByText('Most affected (475 distinct)')).not.toBeInTheDocument();
    await userEvent.setup().click(files.getByRole('button', { name: 'View details' }));
    expect(files.getByText('Most affected (475 distinct)')).toBeInTheDocument();
    expect(files.getByText('C:\\Users\\lab\\files_affected\\top.txt')).toBeInTheDocument();
    expect(files.getAllByRole('button', { name: /^Open event/ }).map((b) => b.textContent)).toEqual(['1:1', '1:2']);
    expect(observed('network_activity').getByText('14')).toBeInTheDocument();
    expect(observed('process_activity').getByText('25')).toBeInTheDocument();
  });

  it('starts each category collapsed and shows its detail on request', async () => {
    await open();
    const files = observed('files_affected');
    const toggle = files.getByRole('button', { name: 'View details' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await userEvent.setup().click(toggle);
    expect(files.getByRole('button', { name: 'Hide details' })).toHaveAttribute('aria-expanded', 'true');
  });

  it('says so when a category names no assets', async () => {
    await open();
    expect(observed('unsupported_events').getByText('No assets were named by these events.')).toBeInTheDocument();
  });

  it('opens the raw record behind an impact figure', async () => {
    await open();
    const category = observed('network_activity');
    const user = userEvent.setup();
    await user.click(category.getByRole('button', { name: 'View details' }));
    await user.click(category.getAllByRole('button', { name: 'Open event 1:1' })[0]);
    expect(await screen.findByRole('dialog', { name: /Event 1:1/ })).toBeInTheDocument();
  });
});

describe('Impact: derived figures and the chart', () => {
  it('shows the calculated scores with the definition the API gives', async () => {
    await open();
    const block = screen.getByRole('heading', { name: 'Calculated and derived figures' }).parentElement.parentElement;
    const cards = [...block.querySelectorAll('.derived-card')].map((card) => card.textContent);
    expect(cards[0]).toContain('Files affected');
    expect(cards[0]).toContain('475');
    expect(cards[1]).toContain('12');
    expect(cards[2]).toContain('14');
    expect(cards[0]).toContain('The number of distinct affected assets. A calculated count; it does not measure damage.');
    expect(within(block).getByText('Derived / interpreted')).toBeInTheDocument();
    expect(within(block).getByText(/They are counts, not measures of damage/)).toBeInTheDocument();
  });

  it('describes the chart in words and gives its data as a table', async () => {
    await open();
    const card = within(screen.getByRole('heading', { name: 'Activity over time' }).closest('section'));
    expect(card.getByText('16 events in buckets of 10 seconds (2 buckets).')).toBeInTheDocument();
    expect(await card.findByRole('img', { name: /Events over time in buckets of 10 seconds, by event type/ })).toBeInTheDocument();
    await userEvent.setup().click(card.getByText('Show the chart data as a table'));
    const rows = within(card.getByRole('table', { name: 'Events per time bucket' })).getAllByRole('row').slice(1);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('08:39:40');
    expect(rows[0]).toHaveTextContent('4');
    expect(rows[1]).toHaveTextContent('08:39:50');
    expect(rows[1]).toHaveTextContent('12');
  });

  it('does not estimate any financial or business loss', async () => {
    await open();
    expect(screen.getByText(/No financial or business loss is estimated/)).toBeInTheDocument();
  });
});

describe('Impact: other states', () => {
  it('sends an investigation without an impact analysis to the evidence step', async () => {
    mockApi(caseRoutes(INVESTIGATION, { 'GET /api/investigations/1/impact': { body: { sessions: [] } } }));
    renderApp('/investigations/1/impact');
    expect(await screen.findByRole('heading', { name: 'There is no impact analysis yet' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Go to Evidence' })).toHaveAttribute('href', '/investigations/1/evidence');
  });

  it('lets the analyst choose between sessions', async () => {
    const other = { ...IMPACT.sessions[0], session_id: 'RAVEN-SESSION-OTHER', categories: IMPACT.sessions[0].categories.map((c) => ({ ...c, observed: { ...c.observed, event_count: c.observed.event_count + 1 } })) };
    await open({ 'GET /api/investigations/1/impact': { body: { sessions: [IMPACT.sessions[0], other] } } });
    expect(observed('files_affected').getByText('558')).toBeInTheDocument();
    await userEvent.setup().selectOptions(screen.getByLabelText('Attack session'), 'RAVEN-SESSION-OTHER');
    expect(observed('files_affected').getByText('559')).toBeInTheDocument();
  });

  it('shows the error with a retry', async () => {
    let attempts = 0;
    mockApi(caseRoutes(INVESTIGATION, { 'GET /api/investigations/1/impact': () => { attempts += 1; return attempts === 1 ? { status: 500, body: { detail: 'Internal server error', code: 'internal_error', request_id: 'r' } } : { body: IMPACT }; } }));
    renderApp('/investigations/1/impact');
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('The impact analysis could not be loaded');
    await userEvent.setup().click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('heading', { name: 'Observed impact' })).toBeInTheDocument();
  });

  it('links back to the timeline and on to the RARF', async () => {
    await open();
    const main = within(screen.getByRole('main'));
    expect(main.getByRole('link', { name: /Attack Timeline/ })).toHaveAttribute('href', '/investigations/1/timeline');
    expect(main.getByRole('link', { name: 'RARF' })).toHaveAttribute('href', '/investigations/1/rarf');
  });
});
