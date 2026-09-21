import { EmptyState } from '../components/States';
import { PageHeader } from '../components/PageHeader';

/** A page of the signed-in area whose screen is built in the next stage. It says so, and names the API it will use. */
export default function Planned({ title, subtitle, endpoints = [] }) {
  return (
    <div className="page">
      <PageHeader title={title} subtitle={subtitle} />
      <EmptyState icon="info" title="This screen is not built yet">
        It is added in the next stage. The data behind it is already served by the API:
        {endpoints.length > 0 ? (
          <>
            {' '}
            {endpoints.map((endpoint, index) => (
              <span key={endpoint}>
                {index > 0 ? ', ' : ''}
                <code>{endpoint}</code>
              </span>
            ))}
            .
          </>
        ) : null}
      </EmptyState>
    </div>
  );
}
