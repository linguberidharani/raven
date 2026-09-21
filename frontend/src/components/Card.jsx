import { CountUp } from './CountUp';
import { Icon } from './Icons';

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

export function StatCard({ label, value, note, icon, tone = 'accent' }) {
  return (
    <div className={`stat-card${icon ? ' with-icon' : ''}`}>
      {icon ? (
        <span className={`stat-icon tone-${tone}`} aria-hidden="true">
          <Icon name={icon} size={20} />
        </span>
      ) : null}
      <span className="stat-body">
        <span className="stat-label">{label}</span>
        <span className="stat-value">
          <CountUp value={value} />
        </span>
        {note ? <span className="stat-note">{note}</span> : null}
      </span>
    </div>
  );
}
