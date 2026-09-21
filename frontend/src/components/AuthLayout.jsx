import { Brand } from './Brand';
import { Icon } from './Icons';

const POINTS = [
  { icon: 'search', title: 'Correlated activity', text: 'Related events from Sysmon evidence are grouped into one attack session.' },
  { icon: 'branch', title: 'Reconstructed attack chain', text: 'Follow process, network and file activity from first execution to observed impact.' },
  { icon: 'shield', title: 'Observed and derived, kept apart', text: 'Every statement in a report shows whether it is evidence or interpretation.' },
];

/** Two panels: what RAVEN is (hidden on small screens) and the form. The form page supplies its own h1. */
export default function AuthLayout({ children }) {
  return (
    <div className="auth">
      <aside className="auth-brand" aria-label="About RAVEN">
        <div className="auth-brand-top">
          <Brand size={34} />
          <p className="auth-headline">Investigate ransomware incidents from evidence.</p>
        </div>
        <ul className="auth-points">
          {POINTS.map((point, index) => (
            <li key={point.title} style={{ animationDelay: `${0.25 + index * 0.12}s` }}>
              <span className="auth-icon" aria-hidden="true">
                <Icon name={point.icon} size={20} />
              </span>
              <div>
                <strong>{point.title}</strong>
                <span>{point.text}</span>
              </div>
            </li>
          ))}
        </ul>
        <p className="auth-foot">RAVEN, Ransomware Attack Visualization and Event Navigator. Trace the Attack. Measure the Impact.</p>
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
