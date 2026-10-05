import { lazy, Suspense, useId, useState } from 'react';
import { Link } from 'react-router-dom';
import { getImpact } from '../api/investigations';
import { BasisBadge } from '../components/Badge';
import { Card } from '../components/Card';
import { EventRefList } from '../components/EventPanel';
import { ExpandToggle } from '../components/ExpandToggle';
import { Icon } from '../components/Icons';
import { SectionHeader } from '../components/PageHeader';
import { EmptyState, ErrorBanner, Skeleton } from '../components/States';
import { useCase } from '../cases/CaseContext';
import { useApi } from '../hooks/useApi';
import { formatClock, formatNumber } from '../utils/format';
import { impactCategoryLabel, impactDetails } from '../utils/mapping';
import { investigationPath } from '../utils/navigation';

const ActivityChart = lazy(() => import('../components/ActivityChart'));

function ObservedCard({ category }) {
  const { observed, evidence } = category;
  const [open, setOpen] = useState(false);
  const detailsId = useId();
  const hasAssets = observed.top_assets.length > 0;
  const hasEvidence = evidence.raw_event_refs.length > 0;
  return (
    <article className="impact-card" aria-labelledby={`observed-${category.category}`}>
      <h4 id={`observed-${category.category}`}>{impactCategoryLabel(category.category)}</h4>
      <div className="impact-count">
        {formatNumber(observed.event_count)} <span className="muted">observed events</span>
      </div>
      <p className="faint">{impactDetails(observed.details)}</p>
      {!hasAssets ? <p className="faint">No assets were named by these events.</p> : null}
      {open ? (
        <div id={detailsId}>
          {hasAssets ? (
            <>
              <div className="explain-label">Most affected ({formatNumber(observed.affected_assets.length)} distinct)</div>
              <ul className="asset-list">
                {observed.top_assets.map((asset) => (
                  <li key={asset.asset}>
                    <span className="mono asset-name">{asset.asset}</span>
                    <span className="mono">{formatNumber(asset.events)}</span>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {hasEvidence ? (
            <>
              <div className="explain-label">Evidence events</div>
              <EventRefList references={evidence.raw_event_refs} limit={6} />
            </>
          ) : null}
        </div>
      ) : null}
      {hasAssets || hasEvidence ? (
        <ExpandToggle open={open} onClick={() => setOpen((value) => !value)} moreLabel="View details" lessLabel="Hide details" controls={detailsId} />
      ) : null}
    </article>
  );
}

function DerivedCard({ category }) {
  return (
    <div className="stat-card derived-card">
      <span className="stat-label">{impactCategoryLabel(category.category)}</span>
      <span className="stat-value">{formatNumber(category.derived.impact_score)}</span>
      <span className="stat-note">{category.derived.definition}</span>
    </div>
  );
}

function ActivityTable({ buckets }) {
  return (
    <details className="alt-table">
      <summary>Show the chart data as a table</summary>
      <div className="table-scroll">
        <table className="mini-table">
          <caption className="sr-only">Events per time bucket</caption>
          <thead>
            <tr>
              <th scope="col">Bucket start (UTC)</th>
              <th scope="col" className="num">Process created</th>
              <th scope="col" className="num">Network connection</th>
              <th scope="col" className="num">File created</th>
              <th scope="col" className="num">Total</th>
            </tr>
          </thead>
          <tbody>
            {buckets.map((bucket) => (
              <tr key={bucket.start}>
                <td className="mono">{formatClock(bucket.start).slice(0, 8)}</td>
                <td className="num">{bucket.process_creation}</td>
                <td className="num">{bucket.network_connection}</td>
                <td className="num">{bucket.file_create}</td>
                <td className="num">{bucket.total}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function SessionImpact({ session }) {
  const { categories, activity } = session;
  const total = activity.buckets.reduce((sum, bucket) => sum + bucket.total, 0);
  return (
    <>
      <div>
        <div className="block-head">
          <h3 className="block-title">Observed impact</h3>
          <BasisBadge basis="observed" />
        </div>
        <p className="muted">Consequences recorded in the evidence, counted from the events themselves.</p>
        <div className="impact-grid">
          {categories.map((category) => (
            <ObservedCard key={category.category} category={category} />
          ))}
        </div>
      </div>

      <div>
        <div className="block-head">
          <h3 className="block-title">Calculated and derived figures</h3>
          <BasisBadge basis="derived" />
        </div>
        <p className="muted">RAVEN calculates these from the observed events. They are counts, not measures of damage.</p>
        <div className="stat-grid">
          {categories.map((category) => (
            <DerivedCard key={category.category} category={category} />
          ))}
        </div>
      </div>

      <Card title="Activity over time" actions={<BasisBadge basis={activity.basis} />}>
        <p className="muted">
          {formatNumber(total)} events in buckets of {activity.bucket_seconds} seconds ({activity.buckets.length} buckets).
        </p>
        <Suspense fallback={<Skeleton height={300} />}>
          <ActivityChart buckets={activity.buckets} bucketSeconds={activity.bucket_seconds} />
        </Suspense>
        <ActivityTable buckets={activity.buckets} />
      </Card>

      <p className="faint note">No financial or business loss is estimated. The evidence contains no such figures, so none are stated.</p>
    </>
  );
}

/** Step 5: what the events show was affected (observed), and figures RAVEN calculates from them (derived). */
export default function Impact() {
  const { id } = useCase();
  const { data, loading, error, reload } = useApi((signal) => getImpact(id, signal), [id]);
  const [chosen, setChosen] = useState(null);
  const sessions = data?.sessions ?? [];
  const session = sessions.find((item) => item.session_id === chosen) ?? sessions[0];

  return (
    <section className="stack">
      <SectionHeader title="Impact Analysis" subtitle="Consequences recorded in the evidence, kept separate from the figures RAVEN calculates from them." />
      {error ? <ErrorBanner error={error} onRetry={reload} title="The impact analysis could not be loaded" /> : null}
      {!error && loading && !data ? (
        <div className="card" aria-busy="true" aria-label="Loading the impact analysis">
          <Skeleton height={20} width="40%" />
          <div style={{ height: 12 }} />
          <Skeleton height={100} />
        </div>
      ) : null}
      {data && sessions.length === 0 ? (
        <EmptyState
          icon="chart"
          title="There is no impact analysis yet"
          action={
            <Link className="btn" to={investigationPath(id, 'evidence')}>
              Go to Evidence
            </Link>
          }
        >
          The impact analysis is made for each attack session, after the analysis has run.
        </EmptyState>
      ) : null}
      {sessions.length > 1 ? (
        <div className="toolbar">
          <label htmlFor="impact-session" className="field-label">Attack session</label>
          <select id="impact-session" className="input select" value={session.session_id} onChange={(event) => setChosen(event.target.value)}>
            {sessions.map((item) => (
              <option key={item.session_id} value={item.session_id}>
                {item.session_id}
              </option>
            ))}
          </select>
        </div>
      ) : null}
      {session ? <SessionImpact key={session.session_id} session={session} /> : null}
      <div className="step-nav">
        <Link className="btn btn-secondary" to={investigationPath(id, 'timeline')}>
          <Icon name="arrow" size={18} className="flip" /> Attack Timeline
        </Link>
        <Link className="btn" to={investigationPath(id, 'rarf')}>
          RARF <Icon name="arrow" size={18} />
        </Link>
      </div>
    </section>
  );
}
