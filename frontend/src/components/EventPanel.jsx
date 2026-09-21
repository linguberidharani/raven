import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { ApiError } from '../api/errors';
import { getEvent } from '../api/investigations';
import { useApi } from '../hooks/useApi';
import { formatTimestamp } from '../utils/format';
import { eventTypeLabel, fieldLabel } from '../utils/mapping';
import { BasisBadge } from './Badge';
import { Icon } from './Icons';
import { ErrorBanner, Skeleton } from './States';

const EventPanelContext = createContext(null);

const HIDDEN_FIELDS = new Set(['raven_event_ref', 'raw_event_ref']);

function Fields({ values, labels = true }) {
  const rows = Object.entries(values).filter(([name, value]) => !HIDDEN_FIELDS.has(name) && value !== null && value !== undefined && value !== '');
  if (rows.length === 0) return <p className="faint">No values recorded.</p>;
  return (
    <dl className="kv event-fields">
      {rows.map(([name, value]) => (
        <div key={name} style={{ display: 'contents' }}>
          <dt>{labels ? fieldLabel(name) : name}</dt>
          <dd className="mono">{typeof value === 'object' ? JSON.stringify(value) : String(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function PanelBody({ data }) {
  const { event, raw, raw_xml: xml, groups, timeline } = data;
  return (
    <>
      <div className="panel-lead">
        <BasisBadge basis="observed" />
        <span>{eventTypeLabel(event.event_type)}</span>
        <span className="faint">Sysmon event {event.event_id}</span>
        <span className="mono faint">{formatTimestamp(event.timestamp, { millis: true })}</span>
      </div>
      <section className="panel-section">
        <h3>Normalized record</h3>
        <p className="faint">The fields RAVEN reads from the original record.</p>
        <Fields values={event} />
      </section>
      <section className="panel-section">
        <h3>Original Sysmon record</h3>
        <p className="faint">
          Record {raw.record_id} on {raw.computer}, created {raw.time_created}.
        </p>
        <Fields values={raw.event_data ?? {}} labels={false} />
      </section>
      <section className="panel-section">
        <details>
          <summary>Original XML</summary>
          <pre className="xml">{xml}</pre>
        </details>
      </section>
      <section className="panel-section">
        <h3>Correlation</h3>
        {groups.length === 0 ? (
          <p className="faint">This event is not part of a correlation group.</p>
        ) : (
          <ul className="list">
            {groups.map((group) => (
              <li key={group.group_id} className="list-row">
                <span className="mono">{group.group_id}</span>
                <BasisBadge basis={group.basis} />
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="panel-section">
        <h3>Attack timeline</h3>
        {timeline ? (
          <p>
            Position <strong>{timeline.sequence_number}</strong> of session <span className="mono">{timeline.session_id}</span>: {timeline.description}
          </p>
        ) : (
          <p className="faint">This event is not part of an attack session.</p>
        )}
      </section>
    </>
  );
}

function focusable(root) {
  return Array.from(root.querySelectorAll('button, [href], summary, input, select, textarea, [tabindex]:not([tabindex="-1"])')).filter((element) => !element.disabled);
}

function EventPanel({ investigationId, eventRef, onClose }) {
  const { data, loading, error, reload } = useApi((signal) => getEvent(investigationId, eventRef, signal), [investigationId, eventRef]);
  const panel = useRef(null);
  const closeButton = useRef(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    closeButton.current?.focus();
  }, []);

  useEffect(() => {
    const onKey = (event) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const trap = (event) => {
    if (event.key !== 'Tab' || !panel.current) return;
    const items = focusable(panel.current);
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(eventRef);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  const missing = error instanceof ApiError && error.code === 'event_not_found';

  return (
    <>
      <div className="panel-backdrop" onClick={onClose} aria-hidden="true" />
      <aside className="event-panel" role="dialog" aria-modal="true" aria-labelledby="event-panel-title" ref={panel} onKeyDown={trap}>
        <div className="panel-header">
          <div>
            <h2 id="event-panel-title">
              Event <span className="mono">{eventRef}</span>
            </h2>
            <p className="faint">Evidence file and record number in the original log.</p>
          </div>
          <div className="panel-actions">
            <button type="button" className="btn btn-secondary" onClick={copy}>
              {copied ? 'Copied' : 'Copy reference'}
            </button>
            <button type="button" className="icon-btn" onClick={onClose} aria-label="Close event details" ref={closeButton}>
              <Icon name="close" />
            </button>
          </div>
        </div>
        <div className="panel-body">
          {loading && !data ? (
            <div aria-busy="true" aria-label="Loading the event">
              <Skeleton height={18} width="50%" />
              <div style={{ height: 12 }} />
              <Skeleton height={120} />
            </div>
          ) : null}
          {error ? (
            <ErrorBanner
              error={error}
              onRetry={missing ? undefined : reload}
              title={missing ? 'This event is not stored' : 'The event could not be loaded'}
            />
          ) : null}
          {missing ? <p className="faint">Records that were removed as duplicates are not stored, so they have no details.</p> : null}
          {data ? <PanelBody data={data} /> : null}
        </div>
      </aside>
    </>
  );
}

/** Lets any page of an investigation open the details of one event with useEventPanel().open(reference). */
export function EventPanelProvider({ investigationId, children }) {
  const [eventRef, setEventRef] = useState(null);
  const opener = useRef(null);

  const open = useCallback((reference, trigger) => {
    opener.current = trigger ?? document.activeElement;
    setEventRef(reference);
  }, []);

  const close = useCallback(() => {
    setEventRef(null);
    const trigger = opener.current;
    if (trigger && typeof trigger.focus === 'function') setTimeout(() => trigger.focus(), 0);
  }, []);

  const value = useMemo(() => ({ open }), [open]);
  return (
    <EventPanelContext.Provider value={value}>
      {children}
      {eventRef ? <EventPanel investigationId={investigationId} eventRef={eventRef} onClose={close} /> : null}
    </EventPanelContext.Provider>
  );
}

export function useEventPanel() {
  return useContext(EventPanelContext);
}

/** A reference like 1:1475 that opens the event details when clicked (plain text outside a panel provider). */
export function EventRef({ reference }) {
  const panel = useEventPanel();
  if (!panel) return <span className="ref-chip mono">{reference}</span>;
  return (
    <button type="button" className="ref-chip mono" onClick={(event) => panel.open(reference, event.currentTarget)} aria-label={`Open event ${reference}`}>
      {reference}
    </button>
  );
}

/** Many references: the first ones, and a button for the rest. */
export function EventRefList({ references, limit = 12, label = 'evidence events' }) {
  const [all, setAll] = useState(false);
  const shown = all ? references : references.slice(0, limit);
  return (
    <div className="ref-list">
      {shown.map((reference) => (
        <EventRef key={reference} reference={reference} />
      ))}
      {references.length > limit ? (
        <button type="button" className="btn btn-ghost small" onClick={() => setAll((value) => !value)} aria-expanded={all}>
          {all ? 'Show fewer' : `Show all ${references.length} ${label}`}
        </button>
      ) : null}
    </div>
  );
}
