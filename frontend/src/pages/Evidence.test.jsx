import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BREAKDOWN, EVIDENCE_ITEM, INVESTIGATION, analysisRun } from '../test/fixtures';
import { mockApi } from '../test/mockApi';
import { caseRoutes } from '../test/routes';
import { renderApp } from '../test/render';

const flush = (ms = 50) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });
const count = (calls, method, path) => calls.filter((call) => call.method === method && call.path === path).length;
const main = () => within(screen.getByRole('main'));

afterEach(() => vi.useRealTimers());

async function open(routes = {}) {
  const mocked = mockApi(caseRoutes(INVESTIGATION, routes));
  renderApp('/investigations/1/evidence');
  await screen.findByRole('heading', { level: 2, name: 'Evidence & Log Upload' });
  await screen.findByRole('table', { name: 'Evidence items of this investigation' });
  return mocked;
}

describe('Evidence: what is attached', () => {
  it('shows the counts from evidence to investigation', async () => {
    await open();
    const strip = within(screen.getByRole('heading', { name: 'From evidence to investigation' }).closest('section'));
    const cell = (label) => strip.getByText(label).parentElement;
    expect(cell('Evidence files')).toHaveTextContent('1');
    expect(cell('Raw records')).toHaveTextContent('2,816');
    expect(cell('Stored events')).toHaveTextContent('2,719');
    expect(cell('Ready for investigation')).toHaveTextContent('1 of 1 files');
  });

  it('lists the evidence with its source, size, hash and status', async () => {
    await open();
    const table = screen.getByRole('table', { name: 'Evidence items of this investigation' });
    const row = within(table).getAllByRole('row')[1];
    expect(row).toHaveTextContent('sysmon_export.evtx');
    expect(row).toHaveTextContent('EV-01');
    expect(row).toHaveTextContent('EVTX upload');
    expect(row).toHaveTextContent('2,816');
    expect(row).toHaveTextContent('3.07 MB');
    expect(within(row).getByText('4F2F825EF88B\u2026')).toHaveAttribute('title', EVIDENCE_ITEM.sha256);
    expect(within(row).getByText('Ready')).toBeInTheDocument();
    expect(row).toHaveTextContent('2026-09-21 10:16:00 UTC');
  });

  it('shows why a file failed', async () => {
    await open({ 'GET /api/investigations/1/evidence': { body: { items: [{ ...EVIDENCE_ITEM, status: 'failed', error: 'The file is truncated.' }], event_breakdown: [] } } });
    const row = within(screen.getByRole('table', { name: 'Evidence items of this investigation' })).getAllByRole('row')[1];
    expect(within(row).getByText('Failed')).toBeInTheDocument();
    expect(row).toHaveTextContent('The file is truncated.');
  });

  it('is honest when there is no evidence, and cannot run an analysis', async () => {
    mockApi(caseRoutes(INVESTIGATION, { 'GET /api/investigations/1/evidence': { body: { items: [], event_breakdown: [] } } }));
    renderApp('/investigations/1/evidence');
    expect(await screen.findByRole('heading', { name: 'No evidence yet' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Run analysis' })).toBeDisabled();
    const strip = within(screen.getByRole('heading', { name: 'From evidence to investigation' }).closest('section'));
    expect(strip.getByText('Stored events').parentElement).toHaveTextContent('\u2014');
    expect(screen.queryByRole('heading', { name: 'Telemetry by Sysmon event' })).not.toBeInTheDocument();
  });

  it('shows the stored events by Sysmon event ID, biggest first', async () => {
    await open();
    const card = within(screen.getByRole('heading', { name: 'Telemetry by Sysmon event' }).closest('section'));
    const rows = card.getAllByRole('listitem').map((item) => item.textContent);
    expect(rows).toEqual(['Event 11 · File created2,000', 'Event 1 · Process created500', 'Event 7 · Not supported by RAVEN219']);
  });

  it('shows the error of the evidence list with a retry', async () => {
    let attempts = 0;
    mockApi(caseRoutes(INVESTIGATION, { 'GET /api/investigations/1/evidence': () => { attempts += 1; return attempts === 1 ? { status: 500, body: { detail: 'Internal server error', code: 'internal_error', request_id: 'req-e' } } : { body: { items: [EVIDENCE_ITEM], event_breakdown: BREAKDOWN } }; } }));
    renderApp('/investigations/1/evidence');
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('The evidence could not be loaded');
    await userEvent.setup().click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('table', { name: 'Evidence items of this investigation' })).toBeInTheDocument();
  });

  it('leads on to detection', async () => {
    await open();
    expect(main().getByRole('link', { name: /Detection & Correlation/ })).toHaveAttribute('href', '/investigations/1/detection');
  });
});

describe('Evidence: upload', () => {
  it('sends the chosen file and reloads the list', async () => {
    const { calls } = await open({ 'POST /api/investigations/1/evidence': { status: 201, body: { ...EVIDENCE_ITEM, id: 2, status: 'uploaded' } } });
    const before = count(calls, 'GET', '/api/investigations/1/evidence');
    const file = new File(['ElfFile\0'], 'second.evtx');
    await userEvent.setup().upload(screen.getByLabelText('EVTX files'), file);
    await waitFor(() => expect(count(calls, 'POST', '/api/investigations/1/evidence')).toBe(1));
    const sent = calls.find((call) => call.method === 'POST' && call.path === '/api/investigations/1/evidence').body;
    expect(sent.get('file').name).toBe('second.evtx');
    expect(await screen.findByText('Uploaded', { selector: 'li span' })).toBeInTheDocument();
    await waitFor(() => expect(count(calls, 'GET', '/api/investigations/1/evidence')).toBeGreaterThan(before));
  });

  it('refuses a file that is not .evtx without asking the server', async () => {
    const { calls } = await open();
    await userEvent.setup({ applyAccept: false }).upload(screen.getByLabelText('EVTX files'), new File(['x'], 'notes.txt'));
    expect(await screen.findByText('Only .evtx files are accepted.')).toBeInTheDocument();
    expect(count(calls, 'POST', '/api/investigations/1/evidence')).toBe(0);
  });

  it('says why the server refused a file, per file', async () => {
    let n = 0;
    await open({ 'POST /api/investigations/1/evidence': () => { n += 1; return n === 1 ? { status: 409, body: { detail: 'This file is already part of the investigation.', code: 'duplicate_evidence', request_id: 'r' } } : { status: 201, body: { ...EVIDENCE_ITEM, id: 3 } }; } });
    await userEvent.setup().upload(screen.getByLabelText('EVTX files'), [new File(['a'], 'dup.evtx'), new File(['b'], 'new.evtx')]);
    await waitFor(() => expect(screen.getByText('This file is already part of the investigation.')).toBeInTheDocument());
    expect(screen.getByText('dup.evtx')).toBeInTheDocument();
    expect(screen.getByText('new.evtx')).toBeInTheDocument();
  });

  it('accepts files dropped on the zone', async () => {
    const { calls } = await open({ 'POST /api/investigations/1/evidence': { status: 201, body: { ...EVIDENCE_ITEM, id: 4 } } });
    const zone = screen.getByText('Upload evidence').closest('.dropzone');
    fireEvent.dragOver(zone);
    expect(zone).toHaveClass('dragging');
    fireEvent.drop(zone, { dataTransfer: { files: [new File(['x'], 'dropped.evtx')] } });
    await waitFor(() => expect(count(calls, 'POST', '/api/investigations/1/evidence')).toBe(1));
    expect(zone).not.toHaveClass('dragging');
  });
});

describe('Evidence: analysis', () => {
  it('says that nothing has run yet', async () => {
    await open();
    expect(screen.getByText(/No analysis has run yet/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Run analysis' })).toBeEnabled();
  });

  it('starts a run, follows it while it goes, and refreshes the case when it is done', async () => {
    vi.useFakeTimers();
    let phase = 0;
    const { calls } = mockApi(caseRoutes(INVESTIGATION, {
      'GET /api/investigations/1/analysis': () => ({ body: phase === 0 ? null : phase === 1 ? analysisRun('running', 1) : analysisRun('completed') }),
      'POST /api/investigations/1/analysis': () => { phase = 1; return { status: 202, body: analysisRun('running', 0) }; },
    }));
    renderApp('/investigations/1/evidence');
    await flush(200);
    fireEvent.click(screen.getByRole('button', { name: 'Run analysis' }));
    await flush();
    expect(screen.getByRole('button', { name: 'Analysis is running\u2026' })).toBeDisabled();
    expect(screen.getByRole('progressbar', { name: 'Analysis progress' })).toHaveAttribute('aria-valuetext', '1 of 10 stages done');
    expect(screen.getByText('Collect records').closest('li')).toHaveTextContent('Done');
    expect(screen.getByText('Normalize').closest('li')).toHaveTextContent('Running');
    expect(screen.getByText('Generate report').closest('li')).toHaveTextContent('Waiting');
    const caseBefore = count(calls, 'GET', '/api/investigations/1');
    const evidenceBefore = count(calls, 'GET', '/api/investigations/1/evidence');

    phase = 2;
    await flush(3000);
    await flush(200);
    expect(screen.getByRole('progressbar', { name: 'Analysis progress' })).toHaveAttribute('aria-valuetext', '10 of 10 stages done');
    expect(screen.getByRole('button', { name: 'Run analysis' })).toBeEnabled();
    expect(screen.getByText('Took 20.3 s')).toBeInTheDocument();
    expect(count(calls, 'GET', '/api/investigations/1')).toBeGreaterThan(caseBefore);
    expect(count(calls, 'GET', '/api/investigations/1/evidence')).toBeGreaterThan(evidenceBefore);
  });

  it('shows a failed run with its reason', async () => {
    await open({ 'GET /api/investigations/1/analysis': { body: analysisRun('failed', 3, { error: 'Interrupted by a server restart.' }) } });
    expect(screen.getByText('Failed', { selector: '.run-summary .badge' })).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('The analysis failed');
    expect(screen.getByRole('alert')).toHaveTextContent('Interrupted by a server restart.');
  });

  it('shows why a run could not be started', async () => {
    await open({ 'POST /api/investigations/1/analysis': { status: 409, body: { detail: 'There is no usable evidence file.', code: 'no_evidence', request_id: 'r' } } });
    await userEvent.setup().click(screen.getByRole('button', { name: 'Run analysis' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('There is no usable evidence file.');
  });

  it('does not complain when a run is already going', async () => {
    await open({ 'POST /api/investigations/1/analysis': { status: 409, body: { detail: 'A run is already active.', code: 'analysis_already_running', request_id: 'r' } } });
    await userEvent.setup().click(screen.getByRole('button', { name: 'Run analysis' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Run analysis' })).toBeEnabled());
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});

describe('Evidence: VM collector', () => {
  const inboxFile = { source_name: 'sysmon-LAB.jsonl', size_bytes: 1021516, modified_at: '2026-09-21T12:52:19.000Z', investigation_id: null, investigation_code: null };

  it('lists the inbox files and links one to this investigation', async () => {
    let linked = false;
    const { calls } = await open({
      'GET /api/inbox': () => ({ body: { items: [linked ? { ...inboxFile, investigation_id: 1, investigation_code: 'INV-2026-001' } : inboxFile] } }),
      'POST /api/investigations/1/collector': () => { linked = true; return { status: 201, body: { ...EVIDENCE_ITEM, id: 2, source_type: 'vm_collector', filename: 'sysmon-LAB.jsonl' } }; },
    });
    const card = within(screen.getByRole('heading', { name: 'VM collector' }).closest('section'));
    expect(await card.findByText('sysmon-LAB.jsonl')).toBeInTheDocument();
    expect(card.getByText(/997\.6 KB/)).toBeInTheDocument();
    await userEvent.setup().click(card.getByRole('button', { name: 'Link sysmon-LAB.jsonl to this investigation' }));
    expect(await card.findByText('Linked here')).toBeInTheDocument();
    expect(calls.find((call) => call.method === 'POST' && call.path === '/api/investigations/1/collector').body).toEqual({ source_name: 'sysmon-LAB.jsonl' });
    expect(card.getByText(/is linked\. New events are read and analysed automatically\./)).toBeInTheDocument();
  });

  it('shows a file that belongs to another investigation without a link button', async () => {
    await open({ 'GET /api/inbox': { body: { items: [{ ...inboxFile, investigation_id: 9, investigation_code: 'INV-2026-009' }] } } });
    const card = within(screen.getByRole('heading', { name: 'VM collector' }).closest('section'));
    expect(await card.findByText('Linked to INV-2026-009')).toBeInTheDocument();
    expect(card.queryByRole('button', { name: /^Link / })).not.toBeInTheDocument();
  });

  it('says when the inbox is empty', async () => {
    await open();
    expect(await screen.findByText('The inbox has no collector files.')).toBeInTheDocument();
  });

  it('checks the inbox now and reports what it found', async () => {
    const { calls } = await open({ 'POST /api/inbox/poll': { body: { results: [{ source_name: 'a.jsonl', investigation_id: 1, records_added: 250, rejected: 0, offset: 10, error: null, skipped: null }], analyses_started: [1] } } });
    await userEvent.setup().click(screen.getByRole('button', { name: 'Check the inbox now' }));
    expect(await screen.findByText('Checked the inbox: 250 new records, 1 analysis started.')).toBeInTheDocument();
    expect(count(calls, 'POST', '/api/inbox/poll')).toBe(1);
  });

  it('shows why linking failed', async () => {
    await open({
      'GET /api/inbox': { body: { items: [inboxFile] } },
      'POST /api/investigations/1/collector': { status: 409, body: { detail: 'The inbox file is already linked.', code: 'source_already_linked', request_id: 'r' } },
    });
    const card = within(screen.getByRole('heading', { name: 'VM collector' }).closest('section'));
    await userEvent.setup().click(await card.findByRole('button', { name: /^Link sysmon-LAB\.jsonl/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent('The collector action failed');
    expect(screen.getByRole('alert')).toHaveTextContent('The inbox file is already linked.');
  });

  it('keeps the page current while a VM file feeds the investigation', async () => {
    vi.useFakeTimers();
    const { calls } = mockApi(caseRoutes(INVESTIGATION, {
      'GET /api/investigations/1/collector': { body: { items: [{ source_name: 'sysmon-LAB.jsonl', evidence_id: 2, last_offset: 100, last_record_id: 24882, updated_at: '2026-09-21T12:52:19.000Z', status: 'ready', events_total: 424, error: null }] } },
    }));
    renderApp('/investigations/1/evidence');
    await flush(300);
    const before = count(calls, 'GET', '/api/investigations/1/evidence');
    await flush(3000);
    await flush(3000);
    expect(count(calls, 'GET', '/api/investigations/1/evidence')).toBeGreaterThanOrEqual(before + 2);
    expect(count(calls, 'GET', '/api/investigations/1/analysis')).toBeGreaterThanOrEqual(3);
  });
});
