import { useId, useState } from 'react';
import { Link } from 'react-router-dom';
import { getDetections } from '../api/investigations';
import { Badge, BasisBadge, SeverityBadge } from '../components/Badge';
import { Card } from '../components/Card';
import { EventRefList } from '../components/EventPanel';
import { ExpandToggle } from '../components/ExpandToggle';
import { Icon } from '../components/Icons';
import { SectionHeader } from '../components/PageHeader';
import { Pagination } from '../components/Pagination';
import { EmptyState, ErrorBanner, Skeleton } from '../components/States';
import { useCase } from '../cases/CaseContext';
import { useApi } from '../hooks/useApi';
import { formatDuration, formatNumber, formatTimestamp, formatWindow } from '../utils/format';
import { eventTypeLabel, matchKeyLabel, shortRuleId } from '../utils/mapping';
import { investigationPath } from '../utils/navigation';

export const PAGE_SIZE = 20;
const SEVERITIES = [
  { value: '', label: 'All severities' },
  { value: 'HIGH', label: 'High' },
  { value: 'MEDIUM', label: 'Medium' },
  { value: 'LOW', label: 'Low' },
  { value: 'INFO', label: 'Info' },
];

function StepChips({ steps }) {
  return (
    <ol className="step-chips" aria-label="Rule steps">
      {steps.map((step, index) => (
        <li key={`${step.event_type}-${index}`}>
          <span className="mono">{step.min_count}+</span> {eventTypeLabel(step.event_type)}
        </li>
      ))}
    </ol>
  );
}

function RuleCard({ rule, selected, onToggle }) {
  return (
    <article className="rule-card" aria-labelledby={`rule-${rule.rule_id}`}>
      <div className="rule-head">
        <div>
          <h3 id={`rule-${rule.rule_id}`}>{rule.rule_name}</h3>
          <span className="mono faint">{rule.rule_id}</span>
        </div>
        <div className="rule-badges">
          <SeverityBadge value={rule.severity} />
          {rule.enabled ? null : <Badge tone="neutral">Disabled</Badge>}
        </div>
      </div>
      <p className="muted">{rule.description}</p>
      <StepChips steps={rule.steps} />
      <dl className="rule-facts">
        <div>
          <dt>Window</dt>
          <dd>{formatWindow(rule.time_window_seconds)} per {matchKeyLabel(rule.match_key)}</dd>
        </div>
        <div>
          <dt>Rule confidence</dt>
          <dd>{rule.confidence}%</dd>
        </div>
        <div>
          <dt>Groups found</dt>
          <dd>{formatNumber(rule.groups)}</dd>
        </div>
      </dl>
      <button type="button" className="btn btn-secondary" aria-pressed={selected} onClick={onToggle} disabled={rule.groups === 0 && !selected}>
        {selected ? 'Showing only this rule' : 'Show only this rule'}
      </button>
    </article>
  );
}

function GroupCard({ group }) {
  const span = Date.parse(group.window_end) - Date.parse(group.window_start);
  const [open, setOpen] = useState(false);
  const detailsId = useId();
  return (
    <article className="group-card" aria-labelledby={`group-${group.group_id}`}>
      <div className="group-head">
        <div>
          <h3 id={`group-${group.group_id}`}>{group.rule_name}</h3>
          <span className="mono faint group-id">{group.group_id}</span>
        </div>
        <div className="rule-badges">
          <SeverityBadge value={group.severity} />
          <BasisBadge basis="derived" />
        </div>
      </div>
      <p className="group-meta">
        {matchKeyLabel(group.match_key)} <span className="mono">{group.match_value}</span> · {formatTimestamp(group.window_start, { millis: true })} to {formatTimestamp(group.window_end, { millis: true })} ({formatDuration(span)}) · {formatNumber(group.event_count)} events · rule confidence {group.confidence}%
      </p>
      {open ? (
        <div id={detailsId}>
          <div className="explain">
            <div className="explain-label">Why this activity is correlated</div>
            <p>{group.why.text}</p>
            <table className="mini-table">
              <caption className="sr-only">Steps of the rule for this group</caption>
              <thead>
                <tr>
                  <th scope="col">Step</th>
                  <th scope="col" className="num">Required</th>
                  <th scope="col" className="num">Found</th>
                </tr>
              </thead>
              <tbody>
                {group.why.steps.map((step, index) => (
                  <tr key={`${step.event_type}-${index}`}>
                    <td>{eventTypeLabel(step.event_type)}</td>
                    <td className="num">{step.required}</td>
                    <td className="num">{step.found}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="explain">
            <div className="explain-label">Interpretation</div>
            <p>{group.interpretation.text}</p>
          </div>
          <div className="explain-label">Evidence events</div>
          <EventRefList references={group.evidence.raw_event_refs} />
        </div>
      ) : null}
      <ExpandToggle open={open} onClick={() => setOpen((value) => !value)} moreLabel="View details" lessLabel="Hide details" controls={detailsId} />
    </article>
  );
}

/** Step 2: the rules RAVEN applied and the correlation groups they found, each with the evidence behind it. */
export default function Detection() {
  const { id, investigation } = useCase();
  const [rule, setRule] = useState('');
  const [severity, setSeverity] = useState('');
  const [page, setPage] = useState(1);
  const { data, loading, error, reload } = useApi((signal) => getDetections(id, { rule, severity, page, page_size: PAGE_SIZE }, signal), [id, rule, severity, page]);
  const filtered = Boolean(rule || severity);
  const hasSession = (investigation?.counts?.sessions ?? 0) > 0;

  const clear = () => {
    setRule('');
    setSeverity('');
    setPage(1);
  };

  return (
    <section className="stack">
      <SectionHeader
        title="Detection & Correlation"
        subtitle="Patterns found in the processed evidence. A detection group is one rule matched by recorded events; the events are the evidence."
      />
      {error ? <ErrorBanner error={error} onRetry={reload} title="The detections could not be loaded" /> : null}
      {!error && loading && !data ? (
        <div className="card" aria-busy="true" aria-label="Loading the detections">
          <Skeleton height={20} width="50%" />
          <div style={{ height: 12 }} />
          <Skeleton height={80} />
        </div>
      ) : null}
      {data && !data.analysed ? (
        <EmptyState
          icon="shield"
          title="This investigation has not been analysed yet"
          action={
            <Link className="btn" to={investigationPath(id, 'evidence')}>
              Go to Evidence
            </Link>
          }
        >
          Detections appear after evidence has been added and the analysis has run.
        </EmptyState>
      ) : null}
      {data && data.analysed ? (
        <>
          <Card>
            <div className="summary-row">
              <div>
                <div className="summary-value">{formatNumber(data.counts.total_groups)}</div>
                <div className="muted">
                  detection groups from {data.rules.filter((item) => item.groups > 0).length} of {data.rules.length} rules
                </div>
              </div>
              <ul className="severity-counts" aria-label="Groups by severity">
                {Object.entries(data.counts.by_severity).map(([name, count]) => (
                  <li key={name}>
                    <SeverityBadge value={name} /> <span className="mono">{formatNumber(count)}</span>
                  </li>
                ))}
              </ul>
              {hasSession ? (
                <Link className="btn btn-secondary" to={investigationPath(id, 'reconstruction')}>
                  View attack reconstruction <Icon name="arrow" size={18} />
                </Link>
              ) : null}
            </div>
            <p className="faint note">RAVEN reports these findings for investigation. It does not block or stop any activity.</p>
          </Card>

          <div>
            <h3 className="block-title">Detection rules</h3>
            <div className="rule-grid">
              {data.rules.map((item) => (
                <RuleCard
                  key={item.rule_id}
                  rule={item}
                  selected={rule === item.rule_id}
                  onToggle={() => {
                    setRule(rule === item.rule_id ? '' : item.rule_id);
                    setPage(1);
                  }}
                />
              ))}
            </div>
          </div>

          <div>
            <div className="block-head">
              <h3 className="block-title">Correlation groups</h3>
              <div className="toolbar">
                <select
                  className="input select"
                  aria-label="Filter by severity"
                  value={severity}
                  onChange={(event) => {
                    setSeverity(event.target.value);
                    setPage(1);
                  }}
                >
                  {SEVERITIES.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
                <select
                  className="input select"
                  aria-label="Filter by rule"
                  value={rule}
                  onChange={(event) => {
                    setRule(event.target.value);
                    setPage(1);
                  }}
                >
                  <option value="">All rules</option>
                  {data.rules.map((item) => (
                    <option key={item.rule_id} value={item.rule_id}>
                      {shortRuleId(item.rule_id)} {item.rule_name}
                    </option>
                  ))}
                </select>
                {filtered ? (
                  <button type="button" className="btn btn-ghost" onClick={clear}>
                    Clear filters
                  </button>
                ) : null}
              </div>
            </div>
            {data.groups.length === 0 ? (
              <EmptyState icon="search" title={filtered ? 'No group matches these filters' : 'No detection group was found'}>
                {filtered ? 'Show all rules and severities to see every group.' : 'The rules did not match any of the recorded events.'}
              </EmptyState>
            ) : (
              <>
                <div className="group-list">
                  {data.groups.map((group) => (
                    <GroupCard key={group.group_id} group={group} />
                  ))}
                </div>
                <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} />
              </>
            )}
          </div>
        </>
      ) : null}
      <div className="step-nav">
        <Link className="btn btn-secondary" to={investigationPath(id, 'evidence')}>
          <Icon name="arrow" size={18} className="flip" /> Evidence & Log Upload
        </Link>
        <Link className="btn" to={investigationPath(id, 'reconstruction')}>
          Attack Reconstruction <Icon name="arrow" size={18} />
        </Link>
      </div>
    </section>
  );
}
