import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DETECTIONS, EVENT_DETAIL, INVESTIGATION } from '../test/fixtures';
import { mockApi } from '../test/mockApi';
import { caseRoutes } from '../test/routes';
import { renderApp } from '../test/render';

afterEach(() => vi.restoreAllMocks());

async function openPanel(routes = {}) {
  const mocked = mockApi(caseRoutes(INVESTIGATION, routes));
  renderApp('/investigations/1/detection');
  const user = userEvent.setup();
  await user.click((await screen.findAllByRole('button', { name: 'View details' }))[0]);
  const chip = (await screen.findAllByRole('button', { name: 'Open event 1:1' }))[0];
  await user.click(chip);
  return { ...mocked, chip, user };
}

describe('the event details panel', () => {
  it('opens as a dialog with the record, the original data, the groups and the timeline', async () => {
    const { calls } = await openPanel();
    const dialog = await screen.findByRole('dialog', { name: /Event 1:1/ });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(await within(dialog).findByText('Normalized record')).toBeInTheDocument();
    expect(calls.some((call) => call.path === '/api/investigations/1/events/1:1')).toBe(true);
    expect(within(dialog).getByText('Observed evidence')).toBeInTheDocument();
    expect(within(dialog).getByText('Process created')).toBeInTheDocument();
    expect(within(dialog).getByText('Sysmon event 1')).toBeInTheDocument();
    expect(within(dialog).getByText('Process image').nextElementSibling).toHaveTextContent('C:\\Test\\a.exe');
    expect(within(dialog).getByText('Command line').nextElementSibling).toHaveTextContent('a.exe --run');
    expect(within(dialog).queryByText('MD5')).not.toBeInTheDocument();
    expect(within(dialog).getByText('ProcessId').nextElementSibling).toHaveTextContent('1001');
    expect(within(dialog).getByText(/Record 1 on LAB-HOST/)).toBeInTheDocument();
    expect(within(dialog).getByText('<Event><System><EventID>1</EventID></System></Event>')).toBeInTheDocument();
    expect(within(dialog).getByText('RAVEN-R001:1001:2026-09-13T08:39:49.545Z')).toBeInTheDocument();
    expect(within(dialog).getByText('Derived / interpreted')).toBeInTheDocument();
    expect(within(dialog).getByText(/Position/)).toHaveTextContent('Position 4 of session RAVEN-SESSION-LAB-R001-1001');
  });

  it('says when an event is in no group and no session', async () => {
    await openPanel({ 'GET /api/investigations/1/events/1:1': { body: { ...EVENT_DETAIL, groups: [], timeline: null } } });
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('This event is not part of a correlation group.')).toBeInTheDocument();
    expect(within(dialog).getByText('This event is not part of an attack session.')).toBeInTheDocument();
  });

  it('puts the focus in the panel and gives it back to the reference when it closes', async () => {
    const { chip, user } = await openPanel();
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('button', { name: 'Close event details' })).toHaveFocus();
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    await waitFor(() => expect(chip).toHaveFocus());
  });

  it('closes with the button and with a click outside', async () => {
    const { user } = await openPanel();
    await user.click(await screen.findByRole('button', { name: 'Close event details' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    await user.click((await screen.findAllByRole('button', { name: 'Open event 1:1' }))[0]);
    await screen.findByRole('dialog');
    fireEvent.click(document.querySelector('.panel-backdrop'));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('keeps the focus inside while it is open', async () => {
    const { user } = await openPanel();
    const dialog = await screen.findByRole('dialog');
    await within(dialog).findByText('Normalized record');
    const close = within(dialog).getByRole('button', { name: 'Close event details' });
    const buttons = within(dialog).getAllByRole('button');
    const last = [...dialog.querySelectorAll('button, summary, [href]')].at(-1);
    last.focus();
    await user.tab();
    expect(dialog.contains(document.activeElement)).toBe(true);
    close.focus();
    await user.tab({ shift: true });
    expect(dialog.contains(document.activeElement)).toBe(true);
    expect(buttons.length).toBeGreaterThan(1);
  });

  it('copies the reference', async () => {
    const { user } = await openPanel();
    const dialog = await screen.findByRole('dialog');
    const write = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: write } });
    await user.click(within(dialog).getByRole('button', { name: 'Copy reference' }));
    expect(write).toHaveBeenCalledWith('1:1');
    expect(await within(dialog).findByRole('button', { name: 'Copied' })).toBeInTheDocument();
  });

  it('explains an event that is not stored', async () => {
    await openPanel({ 'GET /api/investigations/1/events/1:1': { status: 404, body: { detail: 'No stored event for this reference.', code: 'event_not_found', request_id: 'r' } } });
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('This event is not stored');
    expect(within(dialog).getByText(/removed as duplicates/)).toBeInTheDocument();
    expect(within(dialog).queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument();
  });

  it('shows another error with a retry', async () => {
    let attempts = 0;
    await openPanel({ 'GET /api/investigations/1/events/1:1': () => { attempts += 1; return attempts === 1 ? { status: 500, body: { detail: 'Internal server error', code: 'internal_error', request_id: 'req-p' } } : { body: EVENT_DETAIL }; } });
    const dialog = await screen.findByRole('dialog');
    const alert = await within(dialog).findByRole('alert');
    expect(alert).toHaveTextContent('The event could not be loaded');
    await userEvent.setup().click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await within(dialog).findByText('Normalized record')).toBeInTheDocument();
  });

  it('shows a loading state first', async () => {
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    await openPanel({ 'GET /api/investigations/1/events/1:1': async () => { await gate; return { body: EVENT_DETAIL }; } });
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByLabelText('Loading the event')).toBeInTheDocument();
    release();
    expect(await within(dialog).findByText('Normalized record')).toBeInTheDocument();
  });

  it('is available for the references of every group', async () => {
    mockApi(caseRoutes(INVESTIGATION));
    renderApp('/investigations/1/detection');
    const user = userEvent.setup();
    for (const button of await screen.findAllByRole('button', { name: 'View details' })) {
      await user.click(button);
    }
    const chips = await screen.findAllByRole('button', { name: /^Open event/ });
    expect(chips.length).toBe(DETECTIONS.groups.reduce((total, group) => total + group.evidence.raw_event_refs.length, 0));
  });
});
