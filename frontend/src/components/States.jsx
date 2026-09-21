import { ApiError } from '../api/errors';
import { Icon } from './Icons';

export function EmptyState({ icon = 'inbox', title, children, action }) {
  return (
    <div className="empty">
      <Icon name={icon} size={32} />
      <h2>{title}</h2>
      {children ? <p>{children}</p> : null}
      {action}
    </div>
  );
}

/** A failed request: what the server said, the request ID for the logs, and a retry button. */
export function ErrorBanner({ error, onRetry, title = 'This could not be loaded' }) {
  const isApi = error instanceof ApiError;
  const message = isApi ? error.detail : 'Something went wrong in the page. Reload it and try again.';
  return (
    <div className="banner banner-error" role="alert">
      <Icon name="alert" />
      <div className="banner-body">
        <div className="banner-title">{title}</div>
        <div>{message}</div>
        {isApi && error.requestId ? <div className="banner-meta">Request ID: <span className="mono">{error.requestId}</span></div> : null}
        {onRetry ? (
          <div className="banner-actions">
            <button type="button" className="btn btn-secondary" onClick={onRetry}>
              Try again
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function Skeleton({ height = 16, width = '100%' }) {
  return <span className="skeleton" style={{ height, width }} aria-hidden="true" />;
}

export function LoadingBlock({ label = 'Loading' }) {
  return (
    <div role="status" style={{ display: 'flex', alignItems: 'center', gap: 12 }} className="muted">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function FullScreenMessage({ children }) {
  return (
    <div className="centered-screen">
      <div>{children}</div>
    </div>
  );
}
