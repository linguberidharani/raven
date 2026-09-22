import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError } from '../api/errors';
import { getAnalysis, getCollector, linkCollectorFile, listEvidence, startAnalysis, uploadEvidence } from '../api/investigations';
import { listInbox, pollInbox } from '../api/inbox';
import { Badge, StatusBadge } from '../components/Badge';
import { Card } from '../components/Card';
import { Icon } from '../components/Icons';
import { SectionHeader } from '../components/PageHeader';
import { EmptyState, ErrorBanner, Skeleton } from '../components/States';
import { useCase } from '../cases/CaseContext';
import { useApi } from '../hooks/useApi';
import { useInterval } from '../hooks/useInterval';
import { formatBytes, formatDuration, formatNumber, formatTimestamp, shortHash } from '../utils/format';
import { ANALYSIS_STAGES, eventTypeLabel, isRunActive, sourceTypeLabel, stageStatusInfo } from '../utils/mapping';
import { investigationPath } from '../utils/navigation';

const REFRESH_MS = 3000;

function sum(items, field) {
  return items.reduce((total, item) => total + (typeof item[field] === 'number' ? item[field] : 0), 0);
}

/** From evidence to investigation: four counts that come straight from the API. */
function Pipeline({ items, breakdown }) {
  const ready = items.filter((item) => item.status === 'ready').length;
  const stored = breakdown.length > 0 ? sum(breakdown, 'count') : null;
  const cells = [
    { label: 'Evidence files', value: formatNumber(items.length), note: 'EVTX uploads and VM collector sources' },
    { label: 'Raw records', value: formatNumber(sum(items, 'events_total')), note: 'Read from the files' },
    { label: 'Stored events', value: stored === null ? '\u2014' : formatNumber(stored), note: stored === null ? 'Available after an analysis' : 'After removing duplicates' },
    { label: 'Ready for investigation', value: `${ready} of ${items.length} files`, note: 'Available to detection and reconstruction' },
  ];
  return (
    <Card title="From evidence to investigation">
      <dl className="pipeline">
        {cells.map((cell) => (
          <div key={cell.label} className="pipeline-cell">
            <dt>{cell.label}</dt>
            <dd className="pipeline-value">{cell.value}</dd>
            <dd className="stat-note">{cell.note}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}

/** Choose or drop .evtx files. Each file is sent on its own and gets its own result line. */
function Dropzone({ investigationId, onUploaded }) {
  const input = useRef(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState([]);

  const send = async (files) => {
    if (files.length === 0) return;
    setBusy(true);
    const outcome = [];
    for (const file of files) {
      if (!/\.evtx$/i.test(file.name)) {
        outcome.push({ name: file.name, ok: false, message: 'Only .evtx files are accepted.' });
        continue;
      }
      try {
        await uploadEvidence(investigationId, file);
        outcome.push({ name: file.name, ok: true, message: 'Uploaded.' });
      } catch (error) {
        outcome.push({ name: file.name, ok: false, message: error instanceof ApiError ? error.detail : 'The upload failed.' });
      }
    }
    setResults(outcome);
    setBusy(false);
    onUploaded();
  };

  return (
    <div>
      <div
        className={`dropzone${dragging ? ' dragging' : ''}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          send(Array.from(event.dataTransfer.files));
        }}
      >
        <Icon name="upload" size={28} />
        <strong>Upload evidence</strong>
        <p className="muted">Drop Windows event log files here, or choose them. Only .evtx files are accepted.</p>
        <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => input.current?.click()}>
          {busy ? 'Uploading\u2026' : 'Choose files'}
        </button>
        <input
          ref={input}
          type="file"
          accept=".evtx"
          multiple
          hidden
          aria-label="EVTX files"
          onChange={(event) => {
            send(Array.from(event.target.files));
            event.target.value = '';
          }}
        />
      </div>
      <div role="status" aria-live="polite">
        <ul className="upload-results">
          {results.map((result, index) => (
            <li key={`${result.name}-${index}`} className={result.ok ? 'ok' : 'bad'}>
              <span className="mono">{result.name}</span>
              <span>{result.ok ? 'Uploaded' : result.message}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function EvidenceTable({ items }) {
  if (items.length === 0) {
    return (
      <EmptyState title="No evidence yet">
        Add an .evtx file above, or link a file from the VM collector below.
      </EmptyState>
    );
  }
  return (
    <div className="card table-card">
      <div className="card-header padded">
        <h3>Evidence items</h3>
      </div>
      <table className="table table-stack">
        <caption className="sr-only">Evidence items of this investigation</caption>
        <thead>
          <tr>
            <th scope="col">File</th>
            <th scope="col">Source</th>
            <th scope="col" className="num">Records</th>
            <th scope="col" className="num">Size</th>
            <th scope="col">SHA-256</th>
            <th scope="col">Status</th>
            <th scope="col">Added (UTC)</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td data-label="File">
                <span className="mono">{item.filename}</span>
                <div className="mono faint">EV-{String(item.id).padStart(2, '0')}</div>
              </td>
              <td data-label="Source">{sourceTypeLabel(item.source_type)}</td>
              <td data-label="Records" className="num">{formatNumber(item.events_total)}</td>
              <td data-label="Size" className="num">{formatBytes(item.size_bytes)}</td>
              <td data-label="SHA-256" className="mono" title={item.sha256}>{shortHash(item.sha256)}</td>
              <td data-label="Status">
                <StatusBadge value={item.status} />
                {item.error ? <div className="field-error">{item.error}</div> : null}
              </td>
              <td data-label="Added (UTC)">{formatTimestamp(item.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function stageRows(run) {
  const known = new Map((run?.stages ?? []).map((stage) => [stage.name, stage]));
  return ANALYSIS_STAGES.map((stage) => ({ ...stage, ...(known.get(stage.name) ?? { status: 'pending' }) }));
}

function AnalysisCard({ run, canRun, onRun, starting, failure }) {
  const active = isRunActive(run);
  const rows = stageRows(run);
  const done = rows.filter((row) => row.status === 'completed').length;
  const duration = run?.started_at && run?.finished_at ? Date.parse(run.finished_at) - Date.parse(run.started_at) : null;
  return (
    <Card
      title="Analysis"
      actions={
        <button type="button" className="btn" disabled={!canRun || active || starting} onClick={onRun}>
          {active || starting ? 'Analysis is running\u2026' : 'Run analysis'}
        </button>
      }
    >
      {failure ? <ErrorBanner error={failure} title="The analysis could not be started" /> : null}
      {!run ? (
        <p className="muted">No analysis has run yet. Add evidence, then run the analysis to detect, correlate and reconstruct.</p>
      ) : (
        <>
          <div className="run-summary">
            <StatusBadge value={run.status} />
            <span className="muted">Started {formatTimestamp(run.started_at)}</span>
            {duration !== null ? <span className="muted">Took {formatDuration(duration)}</span> : null}
          </div>
          {run.error ? <ErrorBanner error={new ApiError({ detail: run.error })} title="The analysis failed" /> : null}
          <div className="progress" role="progressbar" aria-label="Analysis progress" aria-valuemin={0} aria-valuemax={rows.length} aria-valuenow={done} aria-valuetext={`${done} of ${rows.length} stages done`}>
            <span style={{ width: `${(done / rows.length) * 100}%` }} />
          </div>
          <ol className="stage-list">
            {rows.map((row) => {
              const info = stageStatusInfo(row.status);
              return (
                <li key={row.name}>
                  <span>{row.label}</span>
                  <Badge tone={info.tone}>{info.label}</Badge>
                </li>
              );
            })}
          </ol>
        </>
      )}
    </Card>
  );
}

function CollectorCard({ investigationId, collector, onChanged }) {
  const inbox = useApi(listInbox, []);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [failure, setFailure] = useState(null);
  const linked = collector.data?.items ?? [];

  const run = async (action) => {
    setBusy(true);
    setFailure(null);
    setMessage('');
    try {
      await action();
    } catch (error) {
      setFailure(error);
    } finally {
      setBusy(false);
    }
  };

  const link = (name) =>
    run(async () => {
      await linkCollectorFile(investigationId, name);
      setMessage(`${name} is linked. New events are read and analysed automatically.`);
      inbox.reload();
      onChanged();
    });

  const check = () =>
    run(async () => {
      const result = await pollInbox();
      const added = sum(result.results ?? [], 'records_added');
      setMessage(`Checked the inbox: ${formatNumber(added)} new records, ${result.analyses_started?.length ?? 0} analysis started.`);
      inbox.reload();
      onChanged();
    });

  return (
    <Card
      title="VM collector"
      actions={
        <button type="button" className="btn btn-secondary" disabled={busy} onClick={check}>
          Check the inbox now
        </button>
      }
    >
      <p className="muted">
        The collector in the lab VM writes Sysmon events to a shared folder. Link a file to this investigation and RAVEN reads its new events and runs the analysis by itself.
      </p>
      {failure ? <ErrorBanner error={failure} title="The collector action failed" /> : null}
      <p role="status" className="muted">{message}</p>
      {inbox.error ? <ErrorBanner error={inbox.error} onRetry={inbox.reload} title="The inbox could not be read" /> : null}
      {inbox.data && inbox.data.items.length === 0 ? <p className="faint">The inbox has no collector files.</p> : null}
      {inbox.data && inbox.data.items.length > 0 ? (
        <ul className="list">
          {inbox.data.items.map((item) => {
            const here = item.investigation_id === investigationId;
            const other = item.investigation_id !== null && !here;
            const state = linked.find((entry) => entry.source_name === item.source_name);
            return (
              <li className="list-row" key={item.source_name}>
                <div className="list-main">
                  <div className="list-title mono">{item.source_name}</div>
                  <div className="faint">
                    {formatBytes(item.size_bytes)}, changed {formatTimestamp(item.modified_at)}
                    {state ? `, ${formatNumber(state.events_total)} records taken over` : ''}
                  </div>
                </div>
                {here ? <Badge tone="success">Linked here</Badge> : null}
                {other ? <Badge tone="neutral">{`Linked to ${item.investigation_code}`}</Badge> : null}
                {!here && !other ? (
                  <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => link(item.source_name)} aria-label={`Link ${item.source_name} to this investigation`}>
                    Link to this investigation
                  </button>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </Card>
  );
}

function Breakdown({ breakdown }) {
  const rows = [...breakdown].sort((a, b) => b.count - a.count);
  const max = Math.max(...rows.map((row) => row.count), 1);
  return (
    <Card title="Telemetry by Sysmon event" headingLevel={3}>
      <p className="muted">Stored events by Sysmon event ID, after de-duplication. Events RAVEN does not use are counted too.</p>
      <ul className="bars">
        {rows.map((row) => (
          <li key={row.event_id}>
            <div className="bar-label">
              <span>Event {row.event_id} · {eventTypeLabel(row.event_type)}</span>
              <span className="mono">{formatNumber(row.count)}</span>
            </div>
            <div className="bar-track" aria-hidden="true">
              <span style={{ width: `${(row.count / max) * 100}%` }} />
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

/** Step 1: add evidence, run the analysis, watch it, and link the VM collector. */
export default function Evidence() {
  const { id, investigation, reload: reloadCase } = useCase();
  const evidence = useApi((signal) => listEvidence(id, signal), [id]);
  const analysis = useApi((signal) => getAnalysis(id, signal), [id]);
  const collector = useApi((signal) => getCollector(id, signal), [id]);
  const [starting, setStarting] = useState(false);
  const [startFailure, setStartFailure] = useState(null);
  const { reload: reloadEvidence } = evidence;
  const { reload: reloadAnalysis } = analysis;
  const { reload: reloadCollector } = collector;

  const run = analysis.data ?? null;
  const active = isRunActive(run);
  const items = evidence.data?.items ?? [];
  const hasCollector = (collector.data?.items?.length ?? 0) > 0;

  // Keep the page current while a run is going or a VM file feeds this investigation.
  useInterval(
    () => {
      reloadAnalysis();
      if (hasCollector) {
        reloadCollector();
        reloadEvidence();
      }
    },
    active || hasCollector ? REFRESH_MS : null,
  );

  // A run has just finished: the counts of the investigation and the evidence changed.
  const wasActive = useRef(false);
  useEffect(() => {
    if (wasActive.current && !active) {
      reloadEvidence();
      reloadCollector();
      reloadCase();
    }
    wasActive.current = active;
  }, [active, reloadEvidence, reloadCollector, reloadCase]);

  const refreshAll = () => {
    reloadEvidence();
    reloadCollector();
    reloadAnalysis();
    reloadCase();
  };

  const runAnalysis = async () => {
    setStarting(true);
    setStartFailure(null);
    try {
      await startAnalysis(id);
    } catch (error) {
      if (!(error instanceof ApiError && error.code === 'analysis_already_running')) setStartFailure(error);
    } finally {
      setStarting(false);
      reloadAnalysis();
    }
  };

  return (
    <section className="stack">
      <SectionHeader
        title="Evidence & Log Upload"
        subtitle={`Sysmon telemetry attached to ${investigation?.code ?? 'this investigation'}. It is read, normalized and de-duplicated before detection can use it.`}
      />
      {evidence.error ? <ErrorBanner error={evidence.error} onRetry={evidence.reload} title="The evidence could not be loaded" /> : null}
      {!evidence.error && evidence.loading && !evidence.data ? (
        <div className="card" aria-busy="true" aria-label="Loading the evidence">
          <Skeleton height={18} width="40%" />
          <div style={{ height: 12 }} />
          <Skeleton height={40} />
        </div>
      ) : null}
      {evidence.data ? <Pipeline items={items} breakdown={evidence.data.event_breakdown ?? []} /> : null}
      <Dropzone investigationId={id} onUploaded={refreshAll} />
      <AnalysisCard run={run} canRun={items.length > 0} onRun={runAnalysis} starting={starting} failure={startFailure} />
      {analysis.error ? <ErrorBanner error={analysis.error} onRetry={analysis.reload} title="The analysis status could not be loaded" /> : null}
      {evidence.data ? <EvidenceTable items={items} /> : null}
      <CollectorCard investigationId={id} collector={collector} onChanged={refreshAll} />
      {(evidence.data?.event_breakdown ?? []).length > 0 ? <Breakdown breakdown={evidence.data.event_breakdown} /> : null}
      <div className="step-nav">
        <span />
        <Link className="btn" to={investigationPath(id, 'detection')}>
          Detection & Correlation <Icon name="arrow" size={18} />
        </Link>
      </div>
    </section>
  );
}
