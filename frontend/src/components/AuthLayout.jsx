import { Brand } from './Brand';

const POINTS = [
  { color: 'var(--observed)', title: 'Observed and derived, kept apart', text: 'Every statement is labelled as recorded evidence or as an interpretation.' },
  { color: 'var(--accent)', title: 'Traceable to the raw record', text: 'Follow a finding back to the Sysmon event it came from.' },
  { color: 'var(--derived)', title: 'Real data only', text: 'When there is no data, RAVEN says so instead of filling the screen.' },
];

/** Two panels: what RAVEN is (hidden on small screens) and the form. The form page supplies its own h1. */
export default function AuthLayout({ children }) {
  return (
    <div className="auth">
      <aside className="auth-brand" aria-label="About RAVEN">
        <div>
          <Brand size={34} />
          <p className="auth-headline">Ransomware Attack Visualization and Event Navigator</p>
          <p>Turns Sysmon telemetry into an investigation that an analyst can follow from the report back to the raw record.</p>
        </div>
        <ul className="auth-points">
          {POINTS.map((point) => (
            <li key={point.title}>
              <span className="auth-mark" style={{ background: point.color }} aria-hidden="true" />
              <div>
                <strong>{point.title}</strong>
                <span>{point.text}</span>
              </div>
            </li>
          ))}
        </ul>
      </aside>
      <main className="auth-panel" id="main">
        <div className="auth-card">
          <div className="auth-card-brand">
            <Brand size={30} />
          </div>
          {children}
        </div>
      </main>
    </div>
  );
}
