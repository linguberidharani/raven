import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { Card } from '../components/Card';
import { ErrorBanner } from '../components/States';
import { PageHeader } from '../components/PageHeader';
import { formatTimestamp } from '../utils/format';

export default function Profile() {
  const { user, logout } = useAuth();
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
      <Card title="Account">
        <dl className="kv">
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
      <div>
        <button type="button" className="btn btn-danger" onClick={signOut}>
          Sign out
        </button>
      </div>
    </div>
  );
}
