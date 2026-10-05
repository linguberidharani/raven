import { useId, useState } from 'react';
import { Link } from 'react-router-dom';
import { getRules } from '../api/rules';
import { getTimeline } from '../api/investigations';
import { BasisBadge } from '../components/Badge';
import { EventRef } from '../components/EventPanel';
import { ExpandToggle } from '../components/ExpandToggle';
import { Icon } from '../components/Icons';
import { SectionHeader } from '../components/PageHeader';
import { Pagination } from '../components/Pagination';
import { EmptyState, ErrorBanner, Skeleton } from '../components/States';
import { useCase } from '../cases/CaseContext';
import { useApi } from '../hooks/useApi';
import { useDebounced } from '../hooks/useDebounced';
import { formatClock, formatNumber } from '../utils/format';
import { eventTypeIcon, eventTypeLabel, shortRuleId } from '../utils/mapping';
import { investigationPath } from '../utils/navigation';

export const PAGE_SIZE = 50;
const TYPES = [
  { value: '', label: 'All' },
  { value: 'process_creation', label: 'Process' },
  { value: 'network_connection', label: 'Network' },
  { value: 'file_create', label: 'File' },
];

function uniqueRules(groups) {
  const byRule = new Map();
  for (const group of groups) {
    if (!byRule.has(group.rule_id)) byRule.set(group.rule_id, []);
    byRule.get(group.rule_id).push(group.group_id);
  }
  return Array.from(byRule, ([ruleId, ids]) => ({ ruleId, ids }));
}

function TimelineItem({ item }) {
  const rules = uniqueRules(item.groups);
  const [open, setOpen] = useState(false);
  const detailsId = useId();
  return (
    <li className={`tl-item type-${item.event_type}`}>
      <div className="tl-time mono">{formatClock(item.timestamp)}</div>
      <div className="tl-node" aria-hidden="true">
        <Icon name={eventTypeIcon(item.event_type)} size={16} />
      </div>
      <article className="tl-card">
        <div className="tl-badges">
          <BasisBadge basis={item.basis} />
          <span className="tl-type">{eventTypeLabel(item.event_type)}</span>
          <span className="faint mono">#{item.sequence_number}</span>
        </div>
        <p className="tl-text">{item.description}</p>
        {rules.length > 0 ? (
          <div className="tl-groups">
            <span className="faint">Correlated by</span>
            {rules.map((rule) => (
              <span key={rule.ruleId} className="group-chip" title={rule.ids.join('\n')}>
                {shortRuleId(rule.ruleId)}
                {rule.ids.length > 1 ? <span className="mono"> ×{rule.ids.length}</span> : null}
              </span>
            ))}
            <BasisBadge basis="derived" />
          </div>
        ) : null}
        {open ? (
          <div className="tl-meta" id={detailsId}>
            <span>Host <span className="mono">{item.computer}</span></span>
            <span>Sysmon event {item.sysmon_event_id}</span>
            <EventRef reference={item.raw_event_ref} />
          </div>
        ) : null}
        <ExpandToggle open={open} onClick={() => setOpen((value) => !value)} moreLabel="Show details" lessLabel="Hide details" controls={detailsId} className="tl-details-toggle" />
      </article>
    </li>
  );
}

/** Step 4: every correlated event in time order. Solid cards are recorded events; the chips are what RAVEN derived. */
export default function Timeline() {
  const { id } = useCase();
  const [type, setType] = useState('');
  const [rule, setRule] = useState('');
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);
  const search = useDebounced(q.trim(), 300);
  const rules = useApi(getRules, []);
  const { data, loading, error, reload } = useApi((signal) => getTimeline(id, { event_type: type, rule, q: search, page, page_size: PAGE_SIZE }, signal), [id, type, rule, search, page]);
  const filtered = Boolean(type || rule || search);

  const clear = () => {
    setType('');
    setRule('');
    setQ('');
    setPage(1);
  };

  let previousMinute = '';
  const rows = [];
  for (const item of data?.items ?? []) {
    const minute = item.timestamp.slice(0, 16);
    if (minute !== previousMinute) {
      rows.push(
        <li key={`minute-${item.timeline_event_id}`} className="tl-minute" aria-hidden="true">
          {minute.replace('T', ' ')} UTC
        </li>,
      );
      previousMinute = minute;
    }
    rows.push(<TimelineItem key={item.timeline_event_id} item={item} />);
  }

  return (
    <section className="stack">
      <SectionHeader
        title="Attack Timeline"
        subtitle="The correlated events of the attack session in time order. Each card is an event recorded in the logs; the chips show the correlation groups RAVEN derived."
      />
      <div className="toolbar">
        <div className="segmented" role="group" aria-label="Filter by event type">
          {TYPES.map((item) => (
            <button
              key={item.value}
              type="button"
              aria-pressed={type === item.value}
              onClick={() => {
                setType(item.value);
                setPage(1);
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
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
          {(rules.data?.rules ?? []).map((item) => (
            <option key={item.rule_id} value={item.rule_id}>
              {shortRuleId(item.rule_id)} {item.rule_name}
            </option>
          ))}
        </select>
        <div className="search">
          <Icon name="search" size={18} />
          <input
            type="search"
            className="input"
            aria-label="Search event descriptions"
            placeholder="Search the descriptions"
            value={q}
            maxLength={100}
            onChange={(event) => {
              setQ(event.target.value);
              setPage(1);
            }}
          />
        </div>
        {filtered ? (
          <button type="button" className="btn btn-ghost" onClick={clear}>
            Clear filters
          </button>
        ) : null}
      </div>
      {error ? <ErrorBanner error={error} onRetry={reload} title="The timeline could not be loaded" /> : null}
      {!error && loading && !data ? (
        <div className="card" aria-busy="true" aria-label="Loading the timeline">
          <Skeleton height={18} width="40%" />
          <div style={{ height: 12 }} />
          <Skeleton height={90} />
        </div>
      ) : null}
      {data && data.total === 0 && !filtered ? (
        <EmptyState
          icon="clock"
          title="There is no timeline yet"
          action={
            <Link className="btn" to={investigationPath(id, 'evidence')}>
              Go to Evidence
            </Link>
          }
        >
          The timeline is built from the events of an attack session, after the analysis has run.
        </EmptyState>
      ) : null}
      {data && data.total === 0 && filtered ? (
        <EmptyState icon="search" title="No event matches these filters">
          Show all event types and rules, or search for other words.
        </EmptyState>
      ) : null}
      {data && data.total > 0 ? (
        <>
          <p className="muted" role="status">
            {formatNumber(data.total)} {data.total === 1 ? 'event' : 'events'}{filtered ? ' match the filters' : ' in the timeline'}.
          </p>
          <ol className="timeline">{rows}</ol>
          <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} />
        </>
      ) : null}
      <div className="step-nav">
        <Link className="btn btn-secondary" to={investigationPath(id, 'reconstruction')}>
          <Icon name="arrow" size={18} className="flip" /> Attack Reconstruction
        </Link>
        <Link className="btn" to={investigationPath(id, 'impact')}>
          Impact Analysis <Icon name="arrow" size={18} />
        </Link>
      </div>
    </section>
  );
}
