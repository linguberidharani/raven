import { formatNumber } from '../utils/format';

export function Card({ title, actions, children, headingLevel = 2 }) {
  const Heading = `h${headingLevel}`;
  return (
    <section className="card">
      {(title || actions) && (
        <div className="card-header">
          {title ? <Heading>{title}</Heading> : <span />}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function StatCard({ label, value, note }) {
  return (
    <div className="stat-card">
      <span className="stat-label">{label}</span>
      <span className="stat-value">{typeof value === 'number' ? formatNumber(value) : value}</span>
      {note ? <span className="stat-note">{note}</span> : null}
    </div>
  );
}
