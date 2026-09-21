import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { getReconstruction } from '../api/investigations';
import { BasisBadge, SeverityBadge } from '../components/Badge';
import { Card } from '../components/Card';
import { EventRef } from '../components/EventPanel';
import { Icon } from '../components/Icons';
import { SectionHeader } from '../components/PageHeader';
import { Pagination } from '../components/Pagination';
import { ProcessTree } from '../components/ProcessTree';
import { EmptyState, ErrorBanner, Skeleton } from '../components/States';
import { useCase } from '../cases/CaseContext';
import { useApi } from '../hooks/useApi';
import { formatClock, formatDuration, formatNumber, formatTimestamp } from '../utils/format';
import { eventTypeLabel, matchKeyLabel, shortRuleId } from '../utils/mapping';
import { investigationPath } from '../utils/navigation';

export const CHAIN_PAGE_SIZE = 15;

function ChainEntry({ entry, index, open, onToggle }) {
  const panel = `chain-panel-${index}`;
  return (
    <li className="chain-entry">
      <button type="button" className="chain-head" aria-expanded={open} aria-controls={panel} onClick={onToggle}>
        <span className="chain-index mono">{index}</span>
        <span className="chain-main">
          <span className="chain-title">{entry.rule_name}</span>
          <span className="faint">
            {formatClock(entry.start_time)} UTC · process <span className="mono">{entry.match_value}</span> · {formatNumber(entry.event_count)} events
          </span>
        </span>
        <SeverityBadge value={entry.severity} />
        <Icon name="arrow" size={16} className={open ? 'rot' : ''} />
      </button>
      {open ? (
        <div className="chain-panel" id={panel}>
          <div className="explain-label">
            Recorded events <BasisBadge basis="observed" />
          </div>
          <ul className="event-rows">
            {entry.events.map((event) => (
              <li key={event.raw_event_ref}>
                <span className="mono faint">{formatClock(event.timestamp)}</span>
                <span className="event-kind">{eventTypeLabel(event.event_type)}</span>
                <span className="event-text">{event.description}</span>
                <EventRef reference={event.raw_event_ref} />
              </li>
            ))}
          </ul>
          <div className="explain">
            <div className="explain-label">
              Interpretation <BasisBadge basis={entry.interpretation.basis} />
            </div>
            <p>{entry.interpretation.text}</p>
          </div>
        </div>
      ) : null}
    </li>
  );
}

function SessionView({ session }) {
  const [rule, setRule] = useState('');
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(() => new Set([0]));

  const rules = useMemo(() => {
    const order = [];
    const seen = new Map();
    for (const entry of session.chain) {
      if (!seen.has(entry.rule_id)) {
        seen.set(entry.rule_id, { rule_id: entry.rule_id, rule_name: entry.rule_name, severity: entry.severity, groups: 0, first_start: entry.start_time });
        order.push(entry.rule_id);
      }
      seen.get(entry.rule_id).groups += 1;
    }
    return order.map((ruleId) => seen.get(ruleId));
  }, [session]);

  const entries = useMemo(() => session.chain.map((entry, position) => ({ entry, position })).filter(({ entry }) => !rule || entry.rule_id === rule), [session, rule]);
  const pageEntries = entries.slice((page - 1) * CHAIN_PAGE_SIZE, page * CHAIN_PAGE_SIZE);

  const toggle = (position) =>
    setOpen((previous) => {
      const next = new Set(previous);
      if (next.has(position)) next.delete(position);
      else next.add(position);
      return next;
    });

  return (
    <>
      <Card title="Attack session" actions={<BasisBadge basis="derived" />}>
        <dl className="session-facts">
          <div>
            <dt>Host</dt>
            <dd className="mono">{session.computer}</dd>
          </div>
          <div>
            <dt>First event</dt>
            <dd>{formatTimestamp(session.start_time, { millis: true })}</dd>
          </div>
          <div>
            <dt>Last event</dt>
            <dd>{formatTimestamp(session.end_time, { millis: true })}</dd>
          </div>
          <div>
            <dt>Duration</dt>
            <dd>{formatDuration(session.duration_ms)}</dd>
          </div>
          <div>
            <dt>Severity</dt>
            <dd><SeverityBadge value={session.severity} /></dd>
          </div>
          <div>
            <dt>Session confidence</dt>
            <dd>{session.confidence === null ? 'Not assigned' : `${session.confidence}%`}</dd>
          </div>
          <div>
            <dt>Correlation groups</dt>
            <dd>{formatNumber(session.group_count)}</dd>
          </div>
          <div>
            <dt>Rules</dt>
            <dd>{session.rule_ids.map((ruleId) => <span key={ruleId} className="mono rule-tag">{shortRuleId(ruleId)}</span>)}</dd>
          </div>
        </dl>
        <p className="muted">{session.description}</p>
        <p className="faint note">Session ID <span className="mono">{session.session_id}</span></p>
      </Card>

      <Card title="Attack chain" actions={<BasisBadge basis="derived" />}>
        <p className="muted">
          The correlation groups of this session in time order. RAVEN does not invent attack stages: each entry is a rule matched by recorded events.
        </p>
        <div className="rule-summary" role="group" aria-label="Show groups of one rule">
          <button type="button" aria-pressed={rule === ''} onClick={() => { setRule(''); setPage(1); }}>
            All rules <span className="mono">{formatNumber(session.chain.length)}</span>
          </button>
          {rules.map((item) => (
            <button key={item.rule_id} type="button" aria-pressed={rule === item.rule_id} onClick={() => { setRule(item.rule_id); setPage(1); }}>
              {shortRuleId(item.rule_id)} {item.rule_name} <span className="mono">{formatNumber(item.groups)}</span>
            </button>
          ))}
        </div>
        <ol className="chain" start={1}>
          {pageEntries.map(({ entry, position }) => (
            <ChainEntry key={entry.group_id} entry={entry} index={position + 1} open={open.has(position)} onToggle={() => toggle(position)} />
          ))}
        </ol>
        <Pagination page={page} pageSize={CHAIN_PAGE_SIZE} total={entries.length} onPage={setPage} />
      </Card>

      <Card title="Process tree" actions={<BasisBadge basis="observed" />}>
        <p className="muted">
          Parent and child processes recorded in this session. A parent without events in the session is shown as outside the session; {matchKeyLabel('process_guid')}s link the levels.
        </p>
        <ProcessTree tree={session.process_tree} />
      </Card>
    </>
  );
}

/** Step 3: the attack session rebuilt from the correlation groups, and the process tree behind it. */
export default function Reconstruction() {
  const { id } = useCase();
  const { data, loading, error, reload } = useApi((signal) => getReconstruction(id, signal), [id]);
  const [chosen, setChosen] = useState(null);
  const sessions = data?.sessions ?? [];
  const session = sessions.find((item) => item.session_id === chosen) ?? sessions[0];

  return (
    <section className="stack">
      <SectionHeader
        title="Attack Reconstruction"
        subtitle="The attack session rebuilt from correlated events. Recorded events are labelled observed; what RAVEN concludes from them is labelled derived."
      />
      {error ? <ErrorBanner error={error} onRetry={reload} title="The reconstruction could not be loaded" /> : null}
      {!error && loading && !data ? (
        <div className="card" aria-busy="true" aria-label="Loading the reconstruction">
          <Skeleton height={20} width="40%" />
          <div style={{ height: 12 }} />
          <Skeleton height={100} />
        </div>
      ) : null}
      {data && sessions.length === 0 ? (
        <EmptyState
          icon="branch"
          title="No attack session has been reconstructed"
          action={
            <Link className="btn" to={investigationPath(id, 'evidence')}>
              Go to Evidence
            </Link>
          }
        >
          A session is built from detection groups. Run the analysis on evidence, and if no rule matched, there is nothing to reconstruct.
        </EmptyState>
      ) : null}
      {sessions.length > 1 ? (
        <div className="toolbar">
          <label htmlFor="session-select" className="field-label">Attack session</label>
          <select id="session-select" className="input select" value={session.session_id} onChange={(event) => setChosen(event.target.value)}>
            {sessions.map((item) => (
              <option key={item.session_id} value={item.session_id}>
                {formatTimestamp(item.start_time)} · {item.computer} · {item.group_count} groups
              </option>
            ))}
          </select>
        </div>
      ) : null}
      {session ? <SessionView key={session.session_id} session={session} /> : null}
      <div className="step-nav">
        <Link className="btn btn-secondary" to={investigationPath(id, 'detection')}>
          <Icon name="arrow" size={18} className="flip" /> Detection & Correlation
        </Link>
        <Link className="btn" to={investigationPath(id, 'timeline')}>
          Attack Timeline <Icon name="arrow" size={18} />
        </Link>
      </div>
    </section>
  );
}
