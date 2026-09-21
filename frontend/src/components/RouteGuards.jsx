import { Navigate, useLocation, useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { safeNextPath } from '../utils/validation';
import { ErrorBanner, FullScreenMessage, LoadingBlock } from './States';

/** Signed-in pages: wait for the server, show a clear error when it cannot be asked, send anonymous visitors to sign in. */
export function RequireAuth({ children }) {
  const { status, error, reload } = useAuth();
  const location = useLocation();
  if (status === 'loading') {
    return (
      <FullScreenMessage>
        <LoadingBlock label="Checking your session" />
      </FullScreenMessage>
    );
  }
  if (status === 'error') {
    return (
      <FullScreenMessage>
        <ErrorBanner error={error} onRetry={reload} title="The RAVEN server could not be reached" />
      </FullScreenMessage>
    );
  }
  if (status === 'anonymous') {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return children;
}

/** Sign-in and registration: someone who is already signed in goes on to where they wanted to go. */
export function PublicOnly({ children }) {
  const { status } = useAuth();
  const [params] = useSearchParams();
  if (status === 'authenticated') return <Navigate to={safeNextPath(params.get('next'))} replace />;
  return children;
}
