import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ApiError } from '../api/errors';
import { createInvestigation, listInvestigations } from '../api/investigations';
import { SeverityBadge, StatusBadge } from '../components/Badge';
import { TextArea, TextField } from '../components/FormField';
import { Icon } from '../components/Icons';
import { PageHeader } from '../components/PageHeader';
import { Pagination } from '../components/Pagination';
import { EmptyState, ErrorBanner, Skeleton } from '../components/States';
import { useApi } from '../hooks/useApi';
import { useDebounced } from '../hooks/useDebounced';
import { formatNumber, formatTimestamp } from '../utils/format';
import { investigationPath } from '../utils/navigation';

export const PAGE_SIZE = 20;
const STATUSES = [
  { value: '', label: 'All' },
  { value: 'active', label: 'Active' },
  { value: 'open', label: 'Open' },
  { value: 'closed', label: 'Closed' },
];
const SEVERITIES = [
  { value: '', label: 'All severities' },
  { value: 'HIGH', label: 'High' },
  { value: 'MEDIUM', label: 'Medium' },
  { value: 'LOW', label: 'Low' },
  { value: 'INFO', label: 'Info' },
];

function validate({ title, host, description }) {
  const errors = {};
  if (!title.trim()) errors.title = 'Enter a title.';
  else if (title.trim().length > 200) errors.title = 'Use at most 200 characters.';
  if (host.trim().length > 100) errors.host = 'Use at most 100 characters.';
  if (description.trim().length > 5000) errors.description = 'Use at most 5000 characters.';
  return errors;
}

function NewInvestigation({ onCancel, onCreated }) {
  const [values, setValues] = useState({ title: '', host: '', description: '' });
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState(null);
  const [busy, setBusy] = useState(false);
  const form = useRef(null);
  const set = (name) => (value) => setValues((previous) => ({ ...previous, [name]: value }));

  useEffect(() => {
    form.current?.querySelector('[aria-invalid="true"]')?.focus();
  }, [errors]);

  const submit = async (event) => {
    event.preventDefault();
    if (busy) return;
    const found = validate(values);
    setErrors(found);
    setFormError(null);
    if (Object.keys(found).length > 0) return;
    const body = { title: values.title.trim() };
    if (values.host.trim()) body.host = values.host.trim();
    if (values.description.trim()) body.description = values.description.trim();
    setBusy(true);
    try {
      onCreated(await createInvestigation(body));
    } catch (error) {
      setBusy(false);
      if (error instanceof ApiError && error.code === 'validation_error' && ['title', 'host', 'description'].some((name) => error.fields[name])) {
        setErrors({ title: error.fields.title, host: error.fields.host, description: error.fields.description });
      } else {
        setFormError(error);
      }
    }
  };

  return (
    <section className="card" aria-labelledby="new-investigation-title">
      <div className="card-header">
        <h2 id="new-investigation-title">New investigation</h2>
      </div>
      {formError ? <ErrorBanner error={formError} title="The investigation could not be created" /> : null}
      <form className="stack" onSubmit={submit} noValidate ref={form}>
        <TextField label="Title" value={values.title} onChange={set('title')} error={errors.title} maxLength={220} autoFocus />
        <TextField label="Host" optional value={values.host} onChange={set('host')} error={errors.host} hint="The computer the telemetry comes from." />
        <TextArea label="Description" optional value={values.description} onChange={set('description')} error={errors.description} />
        <div className="actions">
          <button type="submit" className="btn" disabled={busy}>
            {busy ? 'Creating\u2026' : 'Create investigation'}
          </button>
          <button type="button" className="btn btn-ghost" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </form>
    </section>
  );
}

function AnalysisCell({ status }) {
  if (!status) return <span className="faint">Not analysed</span>;
  return <StatusBadge value={status} />;
}

/** All investigations, with search, filters and paging. Every value comes from the API. */
export default function Investigations() {
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('');
  const [severity, setSeverity] = useState('');
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const opener = useRef(null);
  const search = useDebounced(q.trim(), 300);
  const { data, loading, error, reload } = useApi((signal) => listInvestigations({ q: search, status, severity, page, page_size: PAGE_SIZE }, signal), [search, status, severity, page]);
  const filtered = Boolean(search || status || severity);

  const clearFilters = () => {
    setQ('');
    setStatus('');
    setSeverity('');
    setPage(1);
  };

  return (
    <div className="page">
      <PageHeader
        title="Investigations"
        subtitle="Each investigation holds its evidence, findings and report."
        actions={
          <button type="button" className="btn" ref={opener} aria-expanded={creating} onClick={() => setCreating((open) => !open)}>
            <Icon name="cases" size={18} /> New investigation
          </button>
        }
      />
      {creating ? (
        <NewInvestigation
          onCancel={() => {
            setCreating(false);
            opener.current?.focus();
          }}
          onCreated={(created) => navigate(investigationPath(created.id, 'evidence'))}
        />
      ) : null}
      <div className="toolbar">
        <div className="search">
          <Icon name="search" size={18} />
          <input
            type="search"
            className="input"
            aria-label="Search investigations"
            placeholder="Search by code, title or description"
            value={q}
            maxLength={100}
            onChange={(event) => {
              setQ(event.target.value);
              setPage(1);
            }}
          />
        </div>
        <div className="segmented" role="group" aria-label="Filter by status">
          {STATUSES.map((item) => (
            <button
              key={item.value}
              type="button"
              aria-pressed={status === item.value}
              onClick={() => {
                setStatus(item.value);
                setPage(1);
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
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
      </div>
      {error ? <ErrorBanner error={error} onRetry={reload} title="The investigations could not be loaded" /> : null}
      {!error && loading && !data ? (
        <div className="card" aria-busy="true" aria-label="Loading the investigations">
          <Skeleton height={18} width="40%" />
          <div style={{ height: 12 }} />
          <Skeleton height={18} />
          <div style={{ height: 12 }} />
          <Skeleton height={18} />
        </div>
      ) : null}
      {data && data.items.length === 0 && filtered ? (
        <EmptyState
          icon="search"
          title="No investigation matches these filters"
          action={
            <button type="button" className="btn btn-secondary" onClick={clearFilters}>
              Clear filters
            </button>
          }
        >
          Try another search text, or show all statuses and severities.
        </EmptyState>
      ) : null}
      {data && data.items.length === 0 && !filtered ? (
        <EmptyState
          title="No investigations yet"
          action={
            <button type="button" className="btn" onClick={() => setCreating(true)}>
              Create the first investigation
            </button>
          }
        >
          An investigation holds the evidence files of one incident and everything RAVEN finds in them.
        </EmptyState>
      ) : null}
      {data && data.items.length > 0 ? (
        <div className="card table-card">
          <table className="table table-stack">
            <caption className="sr-only">Investigations</caption>
            <thead>
              <tr>
                <th scope="col">Case</th>
                <th scope="col">Host</th>
                <th scope="col">Severity</th>
                <th scope="col">Status</th>
                <th scope="col">Analysis</th>
                <th scope="col" className="num">Evidence</th>
                <th scope="col" className="num">Detections</th>
                <th scope="col">Updated (UTC)</th>
                <th scope="col"><span className="sr-only">Open</span></th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((item) => (
                <tr
                  key={item.id}
                  className="row-link"
                  onClick={(event) => {
                    if (!event.target.closest('a, button')) navigate(investigationPath(item.id, 'evidence'));
                  }}
                >
                  <td data-label="Case">
                    <Link to={investigationPath(item.id, 'evidence')} className="case-link">
                      {item.title}
                    </Link>
                    <div className="mono faint">{item.code}</div>
                  </td>
                  <td data-label="Host" className="mono">{item.host ?? '\u2014'}</td>
                  <td data-label="Severity"><SeverityBadge value={item.severity} /></td>
                  <td data-label="Status"><StatusBadge value={item.status} /></td>
                  <td data-label="Analysis"><AnalysisCell status={item.analysis_status} /></td>
                  <td data-label="Evidence" className="num">{formatNumber(item.counts.evidence)}</td>
                  <td data-label="Detections" className="num">{formatNumber(item.counts.detections)}</td>
                  <td data-label="Updated (UTC)" className="nowrap">{formatTimestamp(item.updated_at)}</td>
                  <td data-label="" className="open-cell">
                    <Link className="btn btn-secondary small" to={investigationPath(item.id, 'evidence')} aria-label={`Open ${item.title}`}>
                      Open <Icon name="arrow" size={16} />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} />
        </div>
      ) : null}
    </div>
  );
}
