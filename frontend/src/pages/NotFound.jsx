import { Link } from 'react-router-dom';
import { EmptyState } from '../components/States';
import { PageHeader } from '../components/PageHeader';

export default function NotFound() {
  return (
    <div className="page">
      <PageHeader title="Page not found" />
      <EmptyState
        icon="alert"
        title="There is nothing at this address"
        action={
          <Link className="btn" to="/dashboard">
            Go to the dashboard
          </Link>
        }
      >
        The page may have moved, or the address may be mistyped.
      </EmptyState>
    </div>
  );
}
