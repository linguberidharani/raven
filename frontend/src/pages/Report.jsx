import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError } from '../api/errors';
import { getReport } from '../api/investigations';
import { Badge } from '../components/Badge';
import { EventRefList } from '../components/EventPanel';
import { Icon } from '../components/Icons';
import { SectionHeader } from '../components/PageHeader';
import { SessionPicker } from '../components/SessionPicker';
import { EmptyState, ErrorBanner, Skeleton } from '../components/States';
import { useCase } from '../cases/CaseContext';
import { useApi } from '../hooks/useApi';
import { formatNumber, formatTimestamp } from '../utils/format';
import { investigationPath } from '../utils/navigation';

const BASIS_LABEL = { observed: 'Observed evidence', derived: 'Derived / interpreted' };

/** RAVEN-R003:4:2026-09-13T08:39:49.545Z -> R003:4 */
function groupLabel(groupId) {
  const parts = String(groupId).split(':');
  return `${parts[0].replace(/^RAVEN-/, '')}:${parts[1] ?? ''}`;
}

function Finding({ finding }) {
  const { evidence } = finding;
  const refs = evidence.raw_event_refs ?? [];
  const groups = evidence.correlation_group_ids ?? [];
  return (
    <article className={`finding ${finding.basis}`}>
      <div className="finding-basis">{BASIS_LABEL[finding.basis] ?? finding.basis}</div>
      <p>{finding.statement}</p>
      {refs.length > 0 || groups.length > 0 ? (
        <div className="finding-evidence">
          {refs.length > 0 ? <EventRefList references={refs} limit={8} label="events" /> : null}
          {groups.length > 0 ? (
            <div className="ref-list">
              {groups.slice(0, 8).map((groupId) => (
                <span key={groupId} className="group-chip" title={groupId}>
                  {groupLabel(groupId)}
                </span>
              ))}
              {groups.length > 8 ? <span className="faint">and {groups.length - 8} more groups</span> : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

function Section({ section }) {
  const limitations = section.section_id === 'confidence_limitations';
  return (
    <section className={`report-section${limitations ? ' limitations' : ''}`} id={`section-${section.section_id}`} aria-labelledby={`heading-${section.section_id}`}>
      <h3 id={`heading-${section.section_id}`}>{section.title}</h3>
      {limitations ? <p className="faint">What the evidence cannot show. RAVEN reports behaviour, not intent.</p> : null}
      {section.findings.map((finding, index) => (
        <Finding key={`${section.section_id}-${index}`} finding={finding} />
      ))}
    </section>
  );
}

/** Step 7: the report of the session. Every statement is labelled observed or derived and links to its evidence. */
export default function Report() {
  const { id, investigation } = useCase();
  const [session, setSession] = useState(null);
  const { data, loading, error, reload } = useApi((signal) => getReport(id, { session }, signal), [id, session]);
  const notAnalysed = error instanceof ApiError && error.code === 'not_analysed';
  const findings = data ? data.sections.flatMap((section) => section.findings) : [];
  const observed = findings.filter((finding) => finding.basis === 'observed').length;
  const derived = findings.filter((finding) => finding.basis === 'derived').length;

  return (
    <section className="stack">
      <SectionHeader
        title="Investigation Report"
        subtitle="Assembled from recorded events and the findings RAVEN derived from them. It says what the evidence shows, not who did it or why."
        actions={
          data ? (
            <button type="button" className="btn btn-secondary no-print" onClick={() => window.print()}>
              <Icon name="file" size={18} /> Print or save as PDF
            </button>
          ) : null
        }
      />
      <div className="no-print">
        <SessionPicker investigationId={id} value={session} onChange={setSession} />
      </div>
      {notAnalysed ? (
        <EmptyState
          icon="file"
          title="There is no report yet"
          action={
            <Link className="btn" to={investigationPath(id, 'evidence')}>
              Go to Evidence
            </Link>
          }
        >
          A report is written for each attack session after the analysis has run.
        </EmptyState>
      ) : null}
      {error && !notAnalysed ? <ErrorBanner error={error} onRetry={reload} title="The report could not be loaded" /> : null}
      {!error && loading && !data ? (
        <div className="card" aria-busy="true" aria-label="Loading the report">
          <Skeleton height={20} width="40%" />
          <div style={{ height: 12 }} />
          <Skeleton height={120} />
        </div>
      ) : null}
      {data ? (
        <article className="report" aria-label="Investigation report">
          <header className="report-head">
            <div className="mono faint">{investigation?.code}</div>
            <h3 className="report-title">{investigation?.title ?? data.report_title}</h3>
            <p className="muted">
              {data.report_title}. Generated {formatTimestamp(data.generated_at)}, when this page was opened. The content does not depend on that time.
            </p>
            <div className="legend">
              <div>
                <Badge tone="observed">Observed evidence</Badge> <span className="muted">recorded in the logs, or a count of recorded events</span>
              </div>
              <div>
                <Badge tone="derived">Derived / interpreted</Badge> <span className="muted">what RAVEN concludes from the observed events</span>
              </div>
            </div>
            <p className="muted" role="status">
              {formatNumber(findings.length)} findings: {formatNumber(observed)} observed, {formatNumber(derived)} derived.
            </p>
            <nav className="toc no-print" aria-label="Report sections">
              <ol>
                {data.sections.map((section) => (
                  <li key={section.section_id}>
                    <a href={`#section-${section.section_id}`}>{section.title}</a>
                  </li>
                ))}
              </ol>
            </nav>
          </header>
          {data.sections.map((section) => (
            <Section key={section.section_id} section={section} />
          ))}
        </article>
      ) : null}
      <div className="step-nav">
        <Link className="btn btn-secondary" to={investigationPath(id, 'rarf')}>
          <Icon name="arrow" size={18} className="flip" /> RARF
        </Link>
        <span />
      </div>
    </section>
  );
}
