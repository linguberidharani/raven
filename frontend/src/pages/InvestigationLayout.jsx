import { useState } from 'react';
import { Link, Outlet, useParams } from 'react-router-dom';
import { updateInvestigation } from '../api/investigations';
import { SeverityBadge, StatusBadge } from '../components/Badge';
import { EventPanelProvider } from '../components/EventPanel';
import { InvestigationTabs } from '../components/InvestigationTabs';
import { EmptyState, ErrorBanner, Skeleton } from '../components/States';
import { useCase } from '../cases/CaseContext';
import { formatTimestamp } from '../utils/format';
import { readySteps } from '../utils/mapping';
import { WORKFLOW } from '../utils/navigation';
import NotFound from './NotFound';

const STATUS_OPTIONS = [
  { value: 'open', label: 'Open' },
  { value: 'active', label: 'Active' },
  { value: 'closed', label: 'Closed' },
];

function Header({ investigation, reload }) {
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState(null);

  const changeStatus = async (event) => {
    setSaving(true);
    setFailure(null);
    try {
      await updateInvestigation(investigation.id, { status: event.target.value });
      reload();
    } catch (error) {
      setFailure(error);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="case-header">
      <div className="case-badges">
        <span className="mono faint">{investigation.code}</span>
        <SeverityBadge value={investigation.severity} />
        <StatusBadge value={investigation.status} />
      </div>
      <h1>{investigation.title}</h1>
      {investigation.description ? <p className="page-subtitle">{investigation.description}</p> : null}
      <dl className="case-facts">
        <div>
          <dt>Host</dt>
          <dd className="mono">{investigation.host ?? '\u2014'}</dd>
        </div>
        <div>
          <dt>Analyst</dt>
          <dd>{investigation.analyst?.name ?? '\u2014'}</dd>
        </div>
        <div>
          <dt>Updated</dt>
          <dd>{formatTimestamp(investigation.updated_at)}</dd>
        </div>
        <div>
          <dt>Progress</dt>
          <dd>{readySteps(investigation)} of {WORKFLOW.length} steps have data</dd>
        </div>
        <div>
          <dt>
            <label htmlFor="case-status">Set status</label>
          </dt>
          <dd>
            <select id="case-status" className="input select compact" value={investigation.status} disabled={saving} onChange={changeStatus}>
              {STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </dd>
        </div>
      </dl>
      {failure ? <ErrorBanner error={failure} title="The status could not be changed" /> : null}
      <InvestigationTabs investigation={investigation} />
    </div>
  );
}

function Body({ step }) {
  const { investigation, loading, error, reload } = useCase();
  if (error?.status === 404) {
    return (
      <div className="page">
        <EmptyState icon="alert" title="This investigation does not exist" action={<Link className="btn" to="/investigations">Go to Investigations</Link>}>
          It may have been mistyped, or it belongs to another RAVEN installation.
        </EmptyState>
      </div>
    );
  }
  if (error) {
    return (
      <div className="page">
        <ErrorBanner error={error} onRetry={reload} title="The investigation could not be loaded" />
      </div>
    );
  }
  if (loading || investigation === null) {
    return (
      <div className="page" aria-busy="true" aria-label="Loading the investigation">
        <Skeleton height={16} width="30%" />
        <Skeleton height={30} width="55%" />
        <Skeleton height={40} />
      </div>
    );
  }
  return (
    <div className="page">
      <Header investigation={investigation} reload={reload} />
      <EventPanelProvider investigationId={investigation.id}>
        <div className="route-fade" key={step}>
          <Outlet />
        </div>
      </EventPanelProvider>
    </div>
  );
}

/** The frame of one investigation: its header, the seven steps, and the page of the chosen step. */
export default function InvestigationLayout() {
  const { id, step } = useParams();
  const valid = /^\d+$/.test(id ?? '') && Number(id) >= 1 && (step === undefined || WORKFLOW.some((item) => item.key === step));
  if (!valid) return <NotFound />;
  return <Body step={step} />;
}
