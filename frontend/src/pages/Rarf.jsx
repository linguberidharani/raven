import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError } from '../api/errors';
import { getRarf, rarfDownloadUrl } from '../api/investigations';
import { Card, StatCard } from '../components/Card';
import { EventRefList } from '../components/EventPanel';
import { Icon } from '../components/Icons';
import { JsonTree } from '../components/JsonTree';
import { SectionHeader } from '../components/PageHeader';
import { SessionPicker } from '../components/SessionPicker';
import { EmptyState, ErrorBanner, Skeleton } from '../components/States';
import { SeverityBadge } from '../components/Badge';
import { useCase } from '../cases/CaseContext';
import { useApi } from '../hooks/useApi';
import { formatNumber, formatTimestamp } from '../utils/format';
import { investigationPath } from '../utils/navigation';

function Overview({ doc }) {
  const session = doc.attack_session;
  return (
    <>
      <Card title="Record">
        <dl className="kv">
          <dt>RARF version</dt>
          <dd className="mono">{doc.rarf_version}</dd>
          <dt>RARF ID</dt>
          <dd className="mono">{doc.rarf_id}</dd>
          <dt>Attack session</dt>
          <dd className="mono">{session.session_id}</dd>
          <dt>Host</dt>
          <dd className="mono">{session.computer}</dd>
          <dt>Session time</dt>
          <dd>{formatTimestamp(session.start_time, { millis: true })} to {formatTimestamp(session.end_time, { millis: true })}</dd>
          <dt>Severity</dt>
          <dd><SeverityBadge value={session.severity} /></dd>
          <dt>Session confidence</dt>
          <dd>{session.confidence === null ? 'Not assigned' : `${session.confidence}%`}</dd>
        </dl>
      </Card>
      <div className="stat-grid">
        <StatCard label="Correlation groups" value={doc.detection.correlation_groups.length} />
        <StatCard label="Rules" value={doc.detection.rules.length} />
        <StatCard label="Timeline events" value={doc.timeline.events.length} />
        <StatCard label="Impact categories" value={Object.keys(doc.impact.categories).length} />
        <StatCard label="Raw event references" value={doc.traceability.raw_event_refs.length} note="Each leads to a record of the original log" />
      </div>
    </>
  );
}

function Viewer({ doc, downloadUrl }) {
  const [view, setView] = useState('structured');
  const [copied, setCopied] = useState(false);
  const text = useMemo(() => JSON.stringify(doc, null, 2), [doc]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <Card
      title="Structured record"
      actions={
        <div className="actions">
          <div className="segmented" role="group" aria-label="View">
            <button type="button" aria-pressed={view === 'structured'} onClick={() => setView('structured')}>
              Structured
            </button>
            <button type="button" aria-pressed={view === 'json'} onClick={() => setView('json')}>
              JSON
            </button>
          </div>
          <button type="button" className="btn btn-secondary" onClick={copy}>
            {copied ? 'Copied' : 'Copy JSON'}
          </button>
          <a className="btn btn-secondary" href={downloadUrl} download>
            Download
          </a>
        </div>
      }
    >
      <p className="muted">The document exactly as RAVEN wrote it. Open a section to inspect its contents.</p>
      {view === 'structured' ? <JsonTree data={doc} openKeys={['attack_session']} /> : <pre className="json-raw" tabIndex={0} aria-label="RARF as JSON">{text}</pre>}
    </Card>
  );
}

/** Step 6: the RARF document of the session, as a tree or as JSON, with a copy and a download. */
export default function Rarf() {
  const { id } = useCase();
  const [session, setSession] = useState(null);
  const { data, loading, error, reload } = useApi((signal) => getRarf(id, { session }, signal), [id, session]);
  const notAnalysed = error instanceof ApiError && error.code === 'not_analysed';

  return (
    <section className="stack">
      <SectionHeader
        title="RARF"
        subtitle="The formal, machine-readable record RAVEN writes for each attack session. Everything in the report can be traced back to it."
      />
      <SessionPicker investigationId={id} value={session} onChange={setSession} />
      {notAnalysed ? (
        <EmptyState
          icon="braces"
          title="There is no RARF yet"
          action={
            <Link className="btn" to={investigationPath(id, 'evidence')}>
              Go to Evidence
            </Link>
          }
        >
          A RARF is written for each attack session after the analysis has run.
        </EmptyState>
      ) : null}
      {error && !notAnalysed ? <ErrorBanner error={error} onRetry={reload} title="The RARF could not be loaded" /> : null}
      {!error && loading && !data ? (
        <div className="card" aria-busy="true" aria-label="Loading the RARF">
          <Skeleton height={20} width="40%" />
          <div style={{ height: 12 }} />
          <Skeleton height={100} />
        </div>
      ) : null}
      {data ? (
        <>
          <Overview doc={data} />
          <Viewer doc={data} downloadUrl={rarfDownloadUrl(id, session)} />
          <Card title="Traceability" headingLevel={3}>
            <p className="muted">
              The events this record is built from. Open one to see the original Sysmon record and its XML.
            </p>
            <div className="explain-label">{formatNumber(data.traceability.raw_event_refs.length)} raw event references</div>
            <EventRefList references={data.traceability.raw_event_refs} limit={24} label="references" />
          </Card>
        </>
      ) : null}
      <div className="step-nav">
        <Link className="btn btn-secondary" to={investigationPath(id, 'impact')}>
          <Icon name="arrow" size={18} className="flip" /> Impact Analysis
        </Link>
        <Link className="btn" to={investigationPath(id, 'report')}>
          Investigation Report <Icon name="arrow" size={18} />
        </Link>
      </div>
    </section>
  );
}
