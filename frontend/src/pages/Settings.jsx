import { useState } from 'react';
import { Link } from 'react-router-dom';
import { getHealth } from '../api/health';
import { dataSource } from '../api/client';
import { Card } from '../components/Card';
import { ErrorBanner, LoadingBlock } from '../components/States';
import { PageHeader } from '../components/PageHeader';
import { useApi } from '../hooks/useApi';
import { clearLocalUiState } from '../utils/storage';
import { plural } from '../utils/mapping';

/** Only real settings: what the interface is connected to, the backend status, and clearing local UI state. */
export default function Settings() {
  const { data, loading, error, reload } = useApi(getHealth, []);
  const [message, setMessage] = useState('');

  const clear = () => {
    const count = clearLocalUiState();
    setMessage(count === 0 ? 'There was no local interface state to clear.' : `Cleared ${plural(count, 'stored item')}.`);
  };

  return (
    <div className="page">
      <PageHeader title="Settings" subtitle="How this interface is connected, and what it keeps in the browser." />
      <div className="two-col">
        <Card title="Connection">
          <dl className="kv">
            <dt>Data source</dt>
            <dd>{dataSource() === 'demo' ? 'Demo data (not real telemetry)' : 'RAVEN backend (real data)'}</dd>
            <dt>Appearance</dt>
            <dd>Dark</dd>
            <dt>Time</dt>
            <dd>All timestamps are shown in UTC.</dd>
          </dl>
        </Card>
        <Card title="Backend status">
          {loading && !data ? <LoadingBlock label="Checking the backend" /> : null}
          {error ? <ErrorBanner error={error} onRetry={reload} title="The backend status could not be read" /> : null}
          {data ? (
            <dl className="kv">
              <dt>Status</dt>
              <dd>{data.status}</dd>
              <dt>Service</dt>
              <dd>{data.service} {data.version}</dd>
              <dt>Environment</dt>
              <dd>{data.environment}</dd>
              <dt>Registry</dt>
              <dd>{data.registry}</dd>
              <dt>Correlation rules loaded</dt>
              <dd>{data.rules_loaded}</dd>
              <dt>RARF version</dt>
              <dd>{data.rarf_version}</dd>
            </dl>
          ) : null}
        </Card>
      </div>
      <Card title="Local interface state">
        <p className="muted">RAVEN keeps only small interface preferences in this browser. Clearing them does not touch any investigation or your account.</p>
        <div style={{ marginTop: 14, display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
          <Link className="btn btn-secondary" to="/">
            Replay intro
          </Link>
          <button type="button" className="btn btn-secondary" onClick={clear}>
            Clear local UI state
          </button>
          <span role="status" className="muted">
            {message}
          </span>
        </div>
      </Card>
    </div>
  );
}
