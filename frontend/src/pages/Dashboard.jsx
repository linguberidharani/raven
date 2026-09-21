import { Link } from 'react-router-dom';
import { getDashboard } from '../api/dashboard';
import { useAuth } from '../auth/AuthContext';
import { BasisBadge, SeverityBadge, StatusBadge } from '../components/Badge';
import { Card, StatCard } from '../components/Card';
import { Donut } from '../components/Donut';
import { Icon } from '../components/Icons';
import { PageHeader } from '../components/PageHeader';
import { EmptyState, ErrorBanner, Skeleton } from '../components/States';
import { useApi } from '../hooks/useApi';
import { formatClock, formatDuration, formatNumber, formatTimestamp } from '../utils/format';
import { plural, severityInfo, shortRuleId, statusInfo } from '../utils/mapping';
import { investigationPath } from '../utils/navigation';

const SEVERITY_COLORS = {
  HIGH: 'var(--sev-high)',
  MEDIUM: 'var(--sev-medium)',
  LOW: 'var(--sev-low)',
  INFO: 'var(--sev-info)',
  none: 'var(--border-strong)',
};
const SEVERITY_LABELS = { HIGH: 'High', MEDIUM: 'Medium', LOW: 'Low', INFO: 'Info', none: 'Not analysed' };
const STATUS_COLORS = { open: 'var(--accent)', active: 'var(--success)', closed: 'var(--sev-info)' };
const EVIDENCE_ORDER = ['uploaded', 'processing', 'ready', 'failed'];
const ACTIVITY_ICONS = { investigation_created: 'cases', evidence_uploaded: 'upload', analysis_completed: 'check', analysis_failed: 'alert' };

function LoadingGrid() {
  return (
    <div className="stat-grid" aria-busy="true" aria-label="Loading the dashboard">
      {Array.from({ length: 6 }, (_, index) => (
        <div className="stat-card" key={index}>
          <Skeleton height={14} width="60%" />
          <Skeleton height={30} width="40%" />
        </div>
      ))}
    </div>
  );
}

function LatestSession({ session }) {
  if (session === null) {
    return <p className="muted">No attack session has been reconstructed yet. Add evidence to an investigation and run the analysis.</p>;
  }
  const span = Date.parse(session.end_time) - Date.parse(session.start_time);
  return (
    <>
      <div className="session-line">
        <Link className="case-link mono" to={investigationPath(session.investigation_id, 'reconstruction')}>
          {session.code}
        </Link>
        <SeverityBadge value={session.severity} />
        <span className="muted">
          {formatTimestamp(session.start_time)} to {formatClock(session.end_time)} UTC ({formatDuration(span)})
        </span>
      </div>
      <ol className="rule-chain" aria-label="Rules of the session in the order of their first group">
        {session.chain.map((step) => (
          <li key={step.rule_id} className={`rule-step sev-${severityInfo(step.severity).key}`}>
            <span className="mono faint">{shortRuleId(step.rule_id)}</span>
            <strong>{step.rule_name}</strong>
            <span className="muted">
              {formatNumber(step.groups)} {step.groups === 1 ? 'group' : 'groups'} · first at {formatClock(step.first_start)}
            </span>
          </li>
        ))}
      </ol>
      <p className="faint note">Rules in the order of their first correlation group. RAVEN derives this from the observed events.</p>
    </>
  );
}

function SeverityDonut({ counts }) {
  const segments = Object.keys(SEVERITY_LABELS).map((key) => ({ key, label: SEVERITY_LABELS[key], value: counts[key] ?? 0, color: SEVERITY_COLORS[key] }));
  return (
    <div className="donut-wrap">
      <Donut segments={segments} centerLabel="cases" />
      <ul className="legend-list" aria-label="Cases by severity">
        {segments.map((segment) => (
          <li key={segment.key}>
            <span className="dot" style={{ background: segment.color }} aria-hidden="true" />
            <span>{segment.label}</span>
            <span className="mono">{formatNumber(segment.value)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SegmentBar({ counts, colors, label }) {
  const entries = Object.entries(counts);
  const total = entries.reduce((sum, [, value]) => sum + value, 0);
  return (
    <>
      <div className="segment-bar" role="img" aria-label={`${label}: ${entries.map(([name, value]) => `${statusInfo(name).label} ${value}`).join(', ')}`}>
        {entries
          .filter(([, value]) => value > 0)
          .map(([name, value]) => (
            <span key={name} style={{ width: `${(value / total) * 100}%`, background: colors[name] }} />
          ))}
      </div>
      <ul className="legend-list" aria-label={label}>
        {entries.map(([name, value]) => (
          <li key={name}>
            <span className="dot" style={{ background: colors[name] }} aria-hidden="true" />
            <span>{statusInfo(name).label}</span>
            <span className="mono">{formatNumber(value)}</span>
          </li>
        ))}
      </ul>
    </>
  );
}

function FindingBars({ counts }) {
  const entries = ['HIGH', 'MEDIUM', 'LOW', 'INFO'].map((key) => [key, counts[key] ?? 0]);
  const max = Math.max(...entries.map(([, value]) => value), 1);
  return (
    <ul className="bars" aria-label="Correlation groups by rule severity">
      {entries.map(([key, value]) => (
        <li key={key}>
          <div className="bar-label">
            <span>{SEVERITY_LABELS[key]}</span>
            <span className="mono">{formatNumber(value)}</span>
          </div>
          <div className="bar-track" aria-hidden="true">
            <span style={{ width: `${(value / max) * 100}%`, background: SEVERITY_COLORS[key] }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Every figure is counted by the API from real records; this page only shows them. */
export default function Dashboard() {
  const { user } = useAuth();
  const { data, loading, error, reload } = useApi(getDashboard, []);
  const firstName = (user?.name ?? '').split(' ')[0];

  return (
    <div className="page dashboard">
      <PageHeader title="Dashboard" subtitle={`${firstName ? `Welcome back, ${firstName}. ` : ''}Your investigations at a glance.`} />
      {error ? <ErrorBanner error={error} onRetry={reload} title="The dashboard could not be loaded" /> : null}
      {!error && loading && !data ? <LoadingGrid /> : null}
      {data && data.totals.investigations === 0 ? (
        <EmptyState
          title="No investigations yet"
          action={
            <Link className="btn" to="/investigations">
              Go to Investigations
            </Link>
          }
        >
          Create an investigation and add evidence. The figures on this page are counted from your real investigations.
        </EmptyState>
      ) : null}
      {data && data.totals.investigations > 0 ? (
        <>
          <div className="stat-grid stat-grid-icons">
            <StatCard label="Investigations" value={data.totals.investigations} icon="cases" tone="accent" />
            <StatCard label="Active investigations" value={data.totals.active_investigations} icon="clock" tone="success" />
            <StatCard label="Open cases" value={data.totals.open_cases} icon="folder" tone="warning" />
            <StatCard label="Evidence items" value={data.totals.evidence_items} icon="upload" tone="observed" />
            <StatCard label="Attack sessions" value={data.totals.sessions} icon="branch" tone="derived" />
            <StatCard label="High severity findings" value={data.totals.high_severity_findings} icon="shield" tone="danger" note="Correlation groups of high severity rules" />
          </div>

          <div className="dash-grid">
            <div className="span-8">
              <Card title="Latest attack session" actions={<BasisBadge basis="derived" />}>
                <LatestSession session={data.latest_session} />
              </Card>
            </div>
            <div className="span-4">
              <Card title="Cases by severity">
                <SeverityDonut counts={data.cases_by_severity} />
              </Card>
            </div>

            <div className="span-8">
              <div className="card table-card">
                <div className="card-header padded">
                  <h2>Recent investigations</h2>
                  <Link to="/investigations">View all</Link>
                </div>
                <table className="table table-stack">
                  <caption className="sr-only">Recent investigations</caption>
                  <thead>
                    <tr>
                      <th scope="col">Case</th>
                      <th scope="col">Severity</th>
                      <th scope="col">Status</th>
                      <th scope="col" className="num">Evidence</th>
                      <th scope="col">Updated (UTC)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent_investigations.map((item) => (
                      <tr key={item.id} className="row-link">
                        <td data-label="Case">
                          <Link className="case-link" to={investigationPath(item.id, 'evidence')}>
                            {item.title}
                          </Link>
                          <div className="mono faint">
                            {item.code} · {plural(item.counts.detections, 'detection')}
                          </div>
                        </td>
                        <td data-label="Severity"><SeverityBadge value={item.severity} /></td>
                        <td data-label="Status"><StatusBadge value={item.status} /></td>
                        <td data-label="Evidence" className="num">{formatNumber(item.counts.evidence)}</td>
                        <td data-label="Updated (UTC)" className="nowrap">{formatTimestamp(item.updated_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="span-4">
              <Card title="Important alerts" actions={<BasisBadge basis="derived" />}>
                {data.alerts.length === 0 ? (
                  <p className="muted">No high severity correlation group has been found.</p>
                ) : (
                  <ul className="alert-list">
                    {data.alerts.map((alert) => (
                      <li key={alert.group_id}>
                        <SeverityBadge value={alert.severity} />
                        <Link to={investigationPath(alert.investigation_id, 'detection')}>{alert.rule_name}</Link>
                        <span className="faint">
                          {alert.code} · {formatTimestamp(alert.window_start)} · {plural(alert.event_count, 'event')}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            </div>

            <div className="span-4">
              <Card title="Investigation status">
                <SegmentBar counts={data.cases_by_status} colors={STATUS_COLORS} label="Investigations by status" />
              </Card>
            </div>
            <div className="span-4">
              <Card title="Recent activity">
                {data.recent_activity.length === 0 ? (
                  <p className="muted">Nothing has happened yet.</p>
                ) : (
                  <ul className="activity-list">
                    {data.recent_activity.map((item, index) => (
                      <li key={`${item.time}-${index}`}>
                        <span className={`activity-icon kind-${item.kind}`} aria-hidden="true">
                          <Icon name={ACTIVITY_ICONS[item.kind] ?? 'info'} size={16} />
                        </span>
                        <div>
                          <Link to={investigationPath(item.investigation_id, 'evidence')}>{item.text}</Link>
                          <div className="faint">
                            {item.code} · {formatTimestamp(item.time)}
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            </div>
            <div className="span-4">
              <Card title="Findings by severity" actions={<BasisBadge basis="derived" />}>
                <FindingBars counts={data.findings_by_severity} />
              </Card>
            </div>

            <div className="span-12">
              <Card title="Evidence processing">
                <dl className="evidence-counts">
                  {EVIDENCE_ORDER.map((key) => (
                    <div key={key}>
                      <dt>{statusInfo(key).label}</dt>
                      <dd>{formatNumber(data.evidence_by_status[key] ?? 0)}</dd>
                    </div>
                  ))}
                </dl>
                {data.evidence_queue.length === 0 ? (
                  <p className="muted">Every evidence file is ready for investigation.</p>
                ) : (
                  <ul className="list">
                    {data.evidence_queue.map((file) => (
                      <li className="list-row" key={file.id}>
                        <div className="list-main">
                          <div className="list-title mono">{file.filename}</div>
                          <div className="faint">
                            {file.code} · {formatTimestamp(file.created_at)}
                            {file.error ? ` · ${file.error}` : ''}
                          </div>
                        </div>
                        <StatusBadge value={file.status} />
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
