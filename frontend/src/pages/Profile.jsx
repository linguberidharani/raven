import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { useCase } from '../cases/CaseContext';
import { SeverityBadge } from '../components/Badge';
import { Card } from '../components/Card';
import { PageHeader } from '../components/PageHeader';
import { ErrorBanner } from '../components/States';
import { formatTimestamp } from '../utils/format';
import { initials } from '../utils/mapping';
import { investigationPath } from '../utils/navigation';

export default function Profile() {
  const { user, logout } = useAuth();
  const { id, investigation } = useCase();
  const navigate = useNavigate();
  const [error, setError] = useState(null);

  const signOut = async () => {
    setError(null);
    try {
      await logout();
      navigate('/login', { replace: true });
    } catch (failure) {
      setError(failure);
    }
  };

  return (
    <div className="page">
      <PageHeader title="Profile" subtitle="Your analyst account on this RAVEN installation." />
      {error ? <ErrorBanner error={error} title="Signing out failed" /> : null}
      <Card>
        <div className="profile-hero">
          <span className="avatar-large" aria-hidden="true">
            {initials(user.name)}
          </span>
          <div>
            <h2>{user.name}</h2>
            <p className="muted">{user.email}</p>
          </div>
        </div>
        <dl className="kv" style={{ marginTop: 20 }}>
          <dt>Name</dt>
          <dd>{user.name}</dd>
          <dt>Email</dt>
          <dd>{user.email}</dd>
          <dt>Organization</dt>
          <dd>{user.organization ?? '\u2014'}</dd>
          <dt>Account created</dt>
          <dd>{formatTimestamp(user.created_at)}</dd>
        </dl>
      </Card>
      <Card title="Current investigation">
        {id === null ? (
          <p className="muted">
            No investigation is open. <Link to="/investigations">Choose an investigation</Link> to see its workflow in the sidebar.
          </p>
        ) : investigation ? (
          <div className="list-row" style={{ borderTop: 0, padding: 0 }}>
            <div className="list-main">
              <div className="mono faint">{investigation.code}</div>
              <div className="list-title">{investigation.title}</div>
            </div>
            <SeverityBadge value={investigation.severity} />
            <div className="actions">
              <Link className="btn" to={investigationPath(investigation.id, 'evidence')}>
                Continue investigation
              </Link>
              <Link className="btn btn-secondary" to="/investigations">
                Choose another case
              </Link>
            </div>
          </div>
        ) : (
          <p className="muted">Loading the investigation.</p>
        )}
      </Card>
      <div>
        <button type="button" className="btn btn-danger" onClick={signOut}>
          Sign out
        </button>
      </div>
    </div>
  );
}
