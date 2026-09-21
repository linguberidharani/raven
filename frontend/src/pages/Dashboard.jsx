import { Link } from 'react-router-dom';
import { getDashboard } from '../api/dashboard';
import { Card, StatCard } from '../components/Card';
import { SeverityBadge, StatusBadge } from '../components/Badge';
import { EmptyState, ErrorBanner, Skeleton } from '../components/States';
import { PageHeader } from '../components/PageHeader';
import { useApi } from '../hooks/useApi';
import { formatNumber } from '../utils/format';
import { plural, statusInfo } from '../utils/mapping';

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

const EVIDENCE_ORDER = ['uploaded', 'processing', 'ready', 'failed'];

/** Every figure is counted by the API from real records; this page only shows them. */
export default function Dashboard() {
  const { data, loading, error, reload } = useApi(getDashboard, []);

  return (
    <div className="page">
      <PageHeader title="Dashboard" subtitle="Your investigations at a glance." />
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
          <div className="stat-grid">
            <StatCard label="Investigations" value={data.totals.investigations} />
            <StatCard label="Active investigations" value={data.totals.active_investigations} />
            <StatCard label="Open cases" value={data.totals.open_cases} />
            <StatCard label="Evidence items" value={data.totals.evidence_items} />
            <StatCard label="Attack sessions" value={data.totals.sessions} />
            <StatCard label="High severity findings" value={data.totals.high_severity_findings} note="Correlation groups of high severity rules" />
          </div>
          <div className="two-col">
            <Card title="Recent investigations">
              <ul className="list">
                {data.recent_investigations.map((item) => (
                  <li className="list-row" key={item.id}>
                    <div className="list-main">
                      <div className="list-title">
                        <span className="mono">{item.code}</span> {item.title}
                      </div>
                      <div className="faint">{plural(item.counts.detections, 'detection')}, {plural(item.counts.evidence, 'evidence file')}</div>
                    </div>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      <SeverityBadge value={item.severity} />
                      <StatusBadge value={item.status} />
                    </div>
                  </li>
                ))}
              </ul>
            </Card>
            <Card title="Evidence processing status">
              <dl className="kv">
                {EVIDENCE_ORDER.map((key) => (
                  <div key={key} style={{ display: 'contents' }}>
                    <dt>{statusInfo(key).label}</dt>
                    <dd>{formatNumber(data.evidence_by_status[key] ?? 0)}</dd>
                  </div>
                ))}
              </dl>
            </Card>
          </div>
        </>
      ) : null}
    </div>
  );
}
