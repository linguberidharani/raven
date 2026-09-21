import { EmptyState } from '../components/States';
import { SectionHeader } from '../components/PageHeader';

/** A step of an investigation whose screen is built in a later stage. It says so and names the API it will use. */
export default function Planned({ title, subtitle, endpoints = [] }) {
  return (
    <section className="stack">
      <SectionHeader title={title} subtitle={subtitle} />
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
    </section>
  );
}
