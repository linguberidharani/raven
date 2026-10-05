import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { INVESTIGATION, REPORT_DOC, SESSION } from '../test/fixtures';
import { mockApi } from '../test/mockApi';
import { caseRoutes } from '../test/routes';
import { renderApp } from '../test/render';

afterEach(() => vi.restoreAllMocks());

async function open(routes = {}) {
  const mocked = mockApi(caseRoutes(INVESTIGATION, routes));
  renderApp('/investigations/1/report');
  await screen.findByRole('heading', { level: 2, name: 'Investigation Report' });
  await screen.findByRole('article', { name: 'Investigation report' });
  return mocked;
}
const section = (id) => within(document.getElementById(`section-${id}`));

describe('Report: the document', () => {
  it('names the case, the time it was generated and how to read it', async () => {
    await open();
    const report = within(screen.getByRole('article', { name: 'Investigation report' }));
    expect(report.getByText('INV-2026-001')).toBeInTheDocument();
    expect(report.getByRole('heading', { name: 'Boot activity' })).toBeInTheDocument();
    expect(report.getByText(/Investigation Report: RAVEN-SESSION-LAB-R001-1001\. Generated 2026-09-21 18:25:36 UTC, when this page was opened/)).toBeInTheDocument();
    expect(report.getByText('recorded in the logs, or a count of recorded events')).toBeInTheDocument();
    expect(report.getByText('what RAVEN concludes from the observed events')).toBeInTheDocument();
    expect(report.getByRole('status')).toHaveTextContent('9 findings: 5 observed, 4 derived.');
  });

  it('has the seven sections in order, with a table of contents that links to them', async () => {
    await open();
    const titles = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent).filter((t) => t !== 'Boot activity');
    expect(titles).toEqual(['Executive summary', 'Session overview', 'Detection evidence', 'Timeline summary', 'Impact analysis', 'Evidence traceability', 'Confidence and limitations']);
    const toc = within(screen.getByRole('navigation', { name: 'Report sections' })).getAllByRole('link');
    expect(toc.map((a) => a.textContent)).toEqual(titles);
    expect(toc[0]).toHaveAttribute('href', '#section-executive_summary');
    expect(document.getElementById('section-executive_summary')).not.toBeNull();
  });

  it('labels every statement as observed or derived', async () => {
    await open();
    const findings = section('executive_summary').getAllByRole('article');
    expect(findings).toHaveLength(2);
    expect(within(findings[0]).getByText('Observed evidence')).toBeInTheDocument();
    expect(findings[0]).toHaveClass('observed');
    expect(within(findings[0]).getByText('RAVEN reconstructed one attack session on LAB-HOST.')).toBeInTheDocument();
    expect(within(findings[1]).getByText('Derived / interpreted')).toBeInTheDocument();
    expect(findings[1]).toHaveClass('derived');
  });

  it('links a statement to the recorded events and to the groups behind it', async () => {
    await open();
    const [observed, derived] = section('executive_summary').getAllByRole('article');
    expect(within(observed).getAllByRole('button', { name: /^Open event/ }).map((b) => b.textContent)).toEqual(['1:1', '1:4']);
    const chips = derived.querySelectorAll('.group-chip');
    expect([...chips].map((chip) => chip.textContent)).toEqual(['R001:1001 \u00b7 08:39:49', 'R003:1001 \u00b7 08:39:51', 'R003:1001 \u00b7 08:40:01']);
    expect(chips[0]).toHaveAttribute('title', 'RAVEN-R001:1001:2026-09-13T08:39:49.545Z');
    await userEvent.setup().click(within(observed).getByRole('button', { name: 'Open event 1:1' }));
    expect(await screen.findByRole('dialog', { name: /Event 1:1/ })).toBeInTheDocument();
  });

  it('marks the limitations section', async () => {
    await open();
    const limits = document.getElementById('section-confidence_limitations');
    expect(limits).toHaveClass('limitations');
    expect(within(limits).getByText('What the evidence cannot show. RAVEN reports behaviour, not intent.')).toBeInTheDocument();
    expect(within(limits).getByText('The telemetry does not show who carried out the activity or why.')).toBeInTheDocument();
    expect(document.getElementById('section-executive_summary')).not.toHaveClass('limitations');
  });

  it('limits how many references and groups it lists at once', async () => {
    const refs = Array.from({ length: 12 }, (_, i) => `1:${i + 1}`);
    const groups = Array.from({ length: 10 }, (_, i) => `RAVEN-R003:${i}:2026-09-13T08:39:49.545Z`);
    const doc = { ...REPORT_DOC, sections: [{ section_id: 'executive_summary', title: 'Executive summary', findings: [{ statement: 'Many.', basis: 'observed', evidence: { event_ids: [], correlation_group_ids: groups, timeline_event_ids: [], impact_analysis_ids: [], raw_event_refs: refs } }] }] };
    await open({ 'GET /api/investigations/1/report': { body: doc } });
    const finding = within(section('executive_summary').getByRole('article'));
    expect(finding.getAllByRole('button', { name: /^Open event/ })).toHaveLength(8);
    await userEvent.setup().click(finding.getByRole('button', { name: 'Show all 12 events' }));
    expect(finding.getAllByRole('button', { name: /^Open event/ })).toHaveLength(12);
    expect(finding.getAllByText(/^R003:/)).toHaveLength(8);
    expect(finding.getByText('and 2 more groups')).toBeInTheDocument();
  });

  it('collapses the extra findings of a long section behind View more findings', async () => {
    const many = Array.from({ length: 5 }, (_, i) => ({ statement: `Finding ${i}.`, basis: 'observed', evidence: { event_ids: [], correlation_group_ids: [], timeline_event_ids: [], impact_analysis_ids: [], raw_event_refs: [] } }));
    const doc = { ...REPORT_DOC, sections: [{ section_id: 'executive_summary', title: 'Executive summary', findings: many }] };
    await open({ 'GET /api/investigations/1/report': { body: doc } });
    const region = section('executive_summary');
    expect(region.getByText('Finding 0.')).toBeInTheDocument();
    expect(region.getByText('Finding 1.')).toBeInTheDocument();
    // The rest are collapsed with a CSS class (report.css: .report-more { display: none }), not unmounted, so
    // a printed or saved PDF still has them (checked below and in styles/report.css) -- jsdom does not apply
    // external stylesheets, so this checks the class and the toggle state rather than visibility.
    const more = region.getByText('Finding 4.').closest('.report-more');
    expect(more).not.toHaveClass('open');
    const toggle = region.getByRole('button', { name: 'View more findings (3)' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await userEvent.setup().click(toggle);
    expect(more).toHaveClass('open');
    expect(region.getByRole('button', { name: 'View less' })).toHaveAttribute('aria-expanded', 'true');
  });

  it('has no View more findings toggle when a section fits within the preview', async () => {
    await open();
    expect(section('executive_summary').queryByRole('button', { name: /View more findings/ })).not.toBeInTheDocument();
  });

  it('prints the report', async () => {
    await open();
    const print = vi.spyOn(window, 'print').mockImplementation(() => {});
    await userEvent.setup().click(screen.getByRole('button', { name: /Print or save as PDF/ }));
    expect(print).toHaveBeenCalledTimes(1);
  });
});

describe('Report: sessions and other states', () => {
  it('asks for the chosen session', async () => {
    const other = { ...SESSION, session_id: 'RAVEN-SESSION-OTHER', computer: 'OTHER-HOST' };
    const { calls } = await open({ 'GET /api/investigations/1/reconstruction': { body: { sessions: [SESSION, other] } } });
    await userEvent.setup().selectOptions(await screen.findByLabelText('Attack session'), 'RAVEN-SESSION-OTHER');
    await vi.waitFor(() => expect(calls.filter((c) => c.path === '/api/investigations/1/report').at(-1).url).toContain('session=RAVEN-SESSION-OTHER'));
  });

  it('says so when there is no report yet, and hides the print button', async () => {
    mockApi(caseRoutes(INVESTIGATION, { 'GET /api/investigations/1/report': { status: 404, body: { detail: 'Not analysed.', code: 'not_analysed', request_id: 'r' } } }));
    renderApp('/investigations/1/report');
    expect(await screen.findByRole('heading', { name: 'There is no report yet' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Go to Evidence' })).toHaveAttribute('href', '/investigations/1/evidence');
    expect(screen.queryByRole('button', { name: /Print/ })).not.toBeInTheDocument();
  });

  it('shows another error with a retry', async () => {
    let attempts = 0;
    mockApi(caseRoutes(INVESTIGATION, { 'GET /api/investigations/1/report': () => { attempts += 1; return attempts === 1 ? { status: 500, body: { detail: 'Internal server error', code: 'internal_error', request_id: 'r' } } : { body: REPORT_DOC }; } }));
    renderApp('/investigations/1/report');
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('The report could not be loaded');
    await userEvent.setup().click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('article', { name: 'Investigation report' })).toBeInTheDocument();
  });

  it('links back to the RARF', async () => {
    await open();
    expect(within(screen.getByRole('main')).getByRole('link', { name: 'RARF' })).toHaveAttribute('href', '/investigations/1/rarf');
  });
});
