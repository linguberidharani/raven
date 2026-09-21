import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { INVESTIGATION } from '../test/fixtures';
import { mockApi } from '../test/mockApi';
import { caseRoutes } from '../test/routes';
import { renderApp } from '../test/render';

const fresh = { ...INVESTIGATION, id: 4, code: 'INV-2026-004', title: 'Fresh case', severity: null, status: 'open', stage: null, analysis_status: null, host: null, counts: { evidence: 1, detections: 0, sessions: 0, timeline_events: 0 } };

describe('the header of an investigation', () => {
  it('shows the case, its badges, its facts and how far it is', async () => {
    mockApi(caseRoutes());
    renderApp('/investigations/1/detection');
    expect(await screen.findByRole('heading', { level: 1, name: 'Boot activity' })).toBeInTheDocument();
    const main = within(screen.getByRole('main'));
    expect(main.getByText('INV-2026-001')).toBeInTheDocument();
    expect(main.getByText('High')).toBeInTheDocument();
    expect(main.getByText('Open', { selector: '.badge' })).toBeInTheDocument();
    expect(main.getByText('HOST-1')).toBeInTheDocument();
    expect(main.getByText('Ada Lovelace')).toBeInTheDocument();
    expect(main.getByText('2026-09-21 10:16:30 UTC')).toBeInTheDocument();
    expect(main.getByText('7 of 7 steps have data')).toBeInTheDocument();
  });

  it('marks the steps that have data and the current one', async () => {
    mockApi(caseRoutes(fresh));
    renderApp('/investigations/4/detection');
    await screen.findByRole('heading', { level: 1, name: 'Fresh case' });
    const steps = within(screen.getByRole('navigation', { name: 'Investigation steps' }));
    const links = steps.getAllByRole('link');
    expect(links).toHaveLength(7);
    expect(links[0]).toHaveAccessibleName('Evidence (has data)');
    expect(links[1]).toHaveAccessibleName('Detection (no data yet)');
    expect(links[1]).toHaveAttribute('aria-current', 'page');
    expect(links[6]).toHaveAccessibleName('Report (no data yet)');
    expect(links[3]).toHaveAttribute('href', '/investigations/4/timeline');
    expect(screen.getByText('1 of 7 steps have data')).toBeInTheDocument();
    expect(within(screen.getByRole('main')).getAllByText('None').length).toBeGreaterThan(0);
  });

  it('changes the status through the API and shows the new one', async () => {
    let current = { ...INVESTIGATION };
    const { calls } = mockApi({
      ...caseRoutes(),
      'GET /api/investigations/1': () => ({ body: current }),
      'PATCH /api/investigations/1': (call) => { current = { ...current, ...call.body }; return { body: current }; },
    });
    renderApp('/investigations/1/evidence');
    await screen.findByRole('heading', { level: 1, name: 'Boot activity' });
    await userEvent.setup().selectOptions(screen.getByLabelText('Set status'), 'closed');
    await waitFor(() => expect(within(screen.getByRole('main')).getByText('Closed', { selector: '.badge' })).toBeInTheDocument());
    expect(calls.find((call) => call.method === 'PATCH').body).toEqual({ status: 'closed' });
  });

  it('shows why the status could not be changed', async () => {
    mockApi({ ...caseRoutes(), 'PATCH /api/investigations/1': { status: 422, body: { detail: 'Invalid status.', code: 'validation_error', request_id: 'r' } } });
    renderApp('/investigations/1/evidence');
    await screen.findByRole('heading', { level: 1, name: 'Boot activity' });
    await userEvent.setup().selectOptions(screen.getByLabelText('Set status'), 'active');
    expect(await screen.findByRole('alert')).toHaveTextContent('The status could not be changed');
  });
});

describe('an investigation that cannot be shown', () => {
  it('says so for an investigation that does not exist', async () => {
    mockApi({ ...caseRoutes(), 'GET /api/investigations/5': { status: 404, body: { detail: 'Investigation not found.', code: 'investigation_not_found', request_id: 'r' } } });
    renderApp('/investigations/5/timeline');
    expect(await screen.findByRole('heading', { name: 'This investigation does not exist' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Go to Investigations' })).toHaveAttribute('href', '/investigations');
    expect(screen.queryByRole('navigation', { name: 'Investigation steps' })).not.toBeInTheDocument();
  });

  it('shows another error with a retry', async () => {
    let attempts = 0;
    mockApi({ ...caseRoutes(), 'GET /api/investigations/1': () => { attempts += 1; return attempts === 1 ? { status: 500, body: { detail: 'Internal server error', code: 'internal_error', request_id: 'req-3' } } : { body: INVESTIGATION }; } });
    renderApp('/investigations/1/evidence');
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('The investigation could not be loaded');
    await userEvent.setup().click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Boot activity' })).toBeInTheDocument();
  });

  it('shows a loading state first', async () => {
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    mockApi({ ...caseRoutes(), 'GET /api/investigations/1': async () => { await gate; return { body: INVESTIGATION }; } });
    renderApp('/investigations/1/evidence');
    expect(await screen.findByLabelText('Loading the investigation')).toBeInTheDocument();
    release();
    expect(await screen.findByRole('heading', { level: 1, name: 'Boot activity' })).toBeInTheDocument();
  });
});
