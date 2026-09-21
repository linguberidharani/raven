import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { INVESTIGATION, RECONSTRUCTION, SESSION, chainOf } from '../test/fixtures';
import { mockApi } from '../test/mockApi';
import { caseRoutes } from '../test/routes';
import { renderApp } from '../test/render';

async function open(routes = {}) {
  const mocked = mockApi(caseRoutes(INVESTIGATION, routes));
  renderApp('/investigations/1/reconstruction');
  await screen.findByRole('heading', { level: 2, name: 'Attack Reconstruction' });
  return mocked;
}
const card = (title) => within(screen.getByRole('heading', { name: title }).closest('section'));

describe('Reconstruction: the session', () => {
  it('shows the facts of the attack session', async () => {
    await open();
    await screen.findByRole('heading', { name: 'Attack session' });
    const session = card('Attack session');
    const value = (label) => session.getByText(label).nextElementSibling;
    expect(value('Host')).toHaveTextContent('LAB-HOST');
    expect(value('First event')).toHaveTextContent('2026-09-13 08:39:49.545 UTC');
    expect(value('Last event')).toHaveTextContent('2026-09-13 08:43:09.488 UTC');
    expect(value('Duration')).toHaveTextContent('3 min 19.9 s');
    expect(value('Severity')).toHaveTextContent('High');
    expect(value('Session confidence')).toHaveTextContent('Not assigned');
    expect(value('Correlation groups')).toHaveTextContent('3');
    expect(value('Rules')).toHaveTextContent('R001R003');
    expect(session.getByText(/Reconstructed attack session containing 3 correlation group/)).toBeInTheDocument();
    expect(session.getByText('RAVEN-SESSION-LAB-R001-1001')).toBeInTheDocument();
    expect(session.getByText('Derived / interpreted')).toBeInTheDocument();
  });

  it('shows a session confidence when there is one', async () => {
    await open({ 'GET /api/investigations/1/reconstruction': { body: { sessions: [{ ...SESSION, confidence: 85 }] } } });
    await screen.findByRole('heading', { name: 'Attack session' });
    expect(card('Attack session').getByText('Session confidence').nextElementSibling).toHaveTextContent('85%');
  });

  it('says so when no session was reconstructed', async () => {
    await open({ 'GET /api/investigations/1/reconstruction': { body: { sessions: [] } } });
    expect(await screen.findByRole('heading', { name: 'No attack session has been reconstructed' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Go to Evidence' })).toHaveAttribute('href', '/investigations/1/evidence');
    expect(screen.queryByRole('heading', { name: 'Attack chain' })).not.toBeInTheDocument();
  });

  it('lets the analyst choose between several sessions', async () => {
    const other = { ...SESSION, session_id: 'RAVEN-SESSION-OTHER', computer: 'OTHER-HOST', group_count: 1, chain: chainOf(1), rule_ids: ['RAVEN-R001'] };
    await open({ 'GET /api/investigations/1/reconstruction': { body: { sessions: [SESSION, other] } } });
    await screen.findByRole('heading', { name: 'Attack session' });
    expect(card('Attack session').getByText('LAB-HOST')).toBeInTheDocument();
    await userEvent.setup().selectOptions(screen.getByLabelText('Attack session', { selector: 'select' }), 'RAVEN-SESSION-OTHER');
    expect(card('Attack session').getByText('OTHER-HOST')).toBeInTheDocument();
  });

  it('shows the error with a retry', async () => {
    let attempts = 0;
    mockApi(caseRoutes(INVESTIGATION, { 'GET /api/investigations/1/reconstruction': () => { attempts += 1; return attempts === 1 ? { status: 500, body: { detail: 'Internal server error', code: 'internal_error', request_id: 'r' } } : { body: RECONSTRUCTION }; } }));
    renderApp('/investigations/1/reconstruction');
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('The reconstruction could not be loaded');
    await userEvent.setup().click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('heading', { name: 'Attack session' })).toBeInTheDocument();
  });
});

describe('Reconstruction: the attack chain', () => {
  it('lists the correlation groups in time order and opens the first', async () => {
    await open();
    await screen.findByRole('heading', { name: 'Attack chain' });
    const chain = card('Attack chain');
    const entries = chain.getAllByRole('listitem').filter((item) => item.classList.contains('chain-entry'));
    expect(entries).toHaveLength(3);
    expect(entries.map((item) => within(item).getByText(/^\d$/).textContent)).toEqual(['1', '2', '3']);
    const first = within(entries[0]);
    expect(first.getByRole('button', { name: /Mass File Modification Burst/ })).toHaveAttribute('aria-expanded', 'true');
    expect(first.getByText('Recorded events')).toBeInTheDocument();
    expect(first.getByText('Observed evidence')).toBeInTheDocument();
    expect(first.getByText('Process created: C:\\Test\\a.exe (PID 1001)')).toBeInTheDocument();
    expect(first.getByText('Interpretation')).toBeInTheDocument();
    expect(first.getByText('Derived / interpreted')).toBeInTheDocument();
    expect(first.getByText('Interpretation of group 1.')).toBeInTheDocument();
    expect(within(entries[1]).getByRole('button', { name: /Sustained File Creation Burst/ })).toHaveAttribute('aria-expanded', 'false');
    expect(within(entries[1]).queryByText('Interpretation')).not.toBeInTheDocument();
  });

  it('opens and closes an entry', async () => {
    await open();
    await screen.findByRole('heading', { name: 'Attack chain' });
    const user = userEvent.setup();
    const second = card('Attack chain').getByRole('button', { name: /Sustained File Creation Burst.*process 1002/s });
    await user.click(second);
    expect(second).toHaveAttribute('aria-expanded', 'true');
    expect(card('Attack chain').getByText('Interpretation of group 2.')).toBeInTheDocument();
    await user.click(second);
    expect(second).toHaveAttribute('aria-expanded', 'false');
    expect(card('Attack chain').queryByText('Interpretation of group 2.')).not.toBeInTheDocument();
  });

  it('counts the groups of each rule and shows only one rule on request', async () => {
    await open();
    await screen.findByRole('heading', { name: 'Attack chain' });
    const user = userEvent.setup();
    const filter = within(screen.getByRole('group', { name: 'Show groups of one rule' }));
    expect(filter.getByRole('button', { name: /All rules/ })).toHaveTextContent('3');
    expect(filter.getByRole('button', { name: /R001 Mass File Modification Burst/ })).toHaveTextContent('1');
    await user.click(filter.getByRole('button', { name: /R003 Sustained File Creation Burst/ }));
    expect(filter.getByRole('button', { name: /R003/ })).toHaveAttribute('aria-pressed', 'true');
    const entries = card('Attack chain').getAllByRole('listitem').filter((item) => item.classList.contains('chain-entry'));
    expect(entries).toHaveLength(2);
    expect(entries.map((item) => within(item).getByText(/^\d$/).textContent)).toEqual(['2', '3']);
  });

  it('pages a long chain', async () => {
    await open({ 'GET /api/investigations/1/reconstruction': { body: { sessions: [{ ...SESSION, chain: chainOf(20), group_count: 20 }] } } });
    await screen.findByRole('heading', { name: 'Attack chain' });
    const chain = card('Attack chain');
    const nav = chain.getByRole('navigation', { name: 'Pagination' });
    expect(nav).toHaveTextContent('Showing 1 to 15 of 20');
    await userEvent.setup().click(within(nav).getByRole('button', { name: 'Next' }));
    expect(chain.getByRole('navigation', { name: 'Pagination' })).toHaveTextContent('Showing 16 to 20 of 20');
    expect(chain.getAllByRole('listitem').filter((item) => item.classList.contains('chain-entry'))).toHaveLength(5);
  });

  it('opens the raw record of an event of the chain', async () => {
    await open();
    await screen.findByRole('heading', { name: 'Attack chain' });
    await userEvent.setup().click(card('Attack chain').getByRole('button', { name: 'Open event 1:1' }));
    expect(await screen.findByRole('dialog', { name: /Event 1:1/ })).toBeInTheDocument();
  });
});

describe('Reconstruction: the process tree', () => {
  it('shows parents and children, and whether they are in the session', async () => {
    await open();
    await screen.findByRole('heading', { name: 'Process tree' });
    const tree = within(screen.getByRole('list', { name: 'Process tree' }));
    expect(tree.getByText('explorer.exe')).toBeInTheDocument();
    expect(tree.getByText('Outside the session')).toBeInTheDocument();
    expect(tree.getByText('a.exe')).toBeInTheDocument();
    expect(tree.getByText('cmd.exe')).toBeInTheDocument();
    expect(tree.getAllByText('In session')).toHaveLength(2);
    expect(tree.getByText('PID 1002')).toBeInTheDocument();
    expect(tree.getByText('no events in the session')).toBeInTheDocument();
    expect(tree.getAllByText(/File created/).length).toBeGreaterThan(0);
    expect(tree.getByText('a.exe')).toHaveAttribute('title', 'C:\\Test\\a.exe');
  });

  it('collapses and expands', async () => {
    await open();
    await screen.findByRole('heading', { name: 'Process tree' });
    const user = userEvent.setup();
    const section = card('Process tree');
    await user.click(section.getByRole('button', { name: 'Collapse all' }));
    expect(section.queryByText('a.exe')).not.toBeInTheDocument();
    expect(section.getByText('explorer.exe')).toBeInTheDocument();
    await user.click(section.getByRole('button', { name: 'Expand explorer.exe (900)' }));
    expect(section.getByText('a.exe')).toBeInTheDocument();
    expect(section.queryByText('cmd.exe')).not.toBeInTheDocument();
    await user.click(section.getByRole('button', { name: 'Expand all' }));
    expect(section.getByText('cmd.exe')).toBeInTheDocument();
    await user.click(section.getByRole('button', { name: 'Collapse explorer.exe (900)' }));
    expect(section.queryByText('a.exe')).not.toBeInTheDocument();
  });

  it('does not loop when the records point at each other', async () => {
    const loop = { ...SESSION.process_tree, nodes: [
      { ...SESSION.process_tree.nodes[0], child_guids: ['{P2}'] },
      { ...SESSION.process_tree.nodes[2], child_guids: ['{P1}', '{MISSING}'] },
    ], roots: ['{P1}'] };
    await open({ 'GET /api/investigations/1/reconstruction': { body: { sessions: [{ ...SESSION, process_tree: loop }] } } });
    await screen.findByRole('heading', { name: 'Process tree' });
    const tree = within(screen.getByRole('list', { name: 'Process tree' }));
    expect(tree.getAllByText('a.exe')).toHaveLength(1);
    expect(tree.getAllByText('cmd.exe')).toHaveLength(1);
  });

  it('says so when there are no process relations', async () => {
    await open({ 'GET /api/investigations/1/reconstruction': { body: { sessions: [{ ...SESSION, process_tree: { nodes: [], roots: [] } }] } } });
    expect(await screen.findByText('No process relations were recorded in this session.')).toBeInTheDocument();
  });
});
