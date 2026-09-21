import { Link, NavLink } from 'react-router-dom';
import { useCase } from '../cases/CaseContext';
import { WORKFLOW, investigationPath } from '../utils/navigation';
import { Brand } from './Brand';
import { Icon } from './Icons';

function Item({ to, icon, end = false, children }) {
  return (
    <NavLink to={to} end={end} className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
      <Icon name={icon} />
      <span>{children}</span>
    </NavLink>
  );
}

/** Dashboard, Investigations, the current case with its workflow, Profile, Settings, Sign out. */
export function Sidebar({ open, onClose, onSignOut, id }) {
  const { id: caseId, investigation } = useCase();
  return (
    <>
      <div className={`sidebar-backdrop${open ? ' open' : ''}`} onClick={onClose} aria-hidden="true" />
      <aside className={`sidebar${open ? ' open' : ''}`} id={id} aria-label="Sidebar">
        <div className="sidebar-brand">
          <Brand />
          <button type="button" className="icon-btn sidebar-close" onClick={onClose} aria-label="Close menu">
            <Icon name="close" />
          </button>
        </div>
        <nav className="nav-section" aria-label="Main">
          <Item to="/dashboard" icon="dashboard">
            Dashboard
          </Item>
          <Item to="/investigations" icon="cases" end>
            Investigations
          </Item>
        </nav>
        <div className="nav-heading">Investigation workflow</div>
        {caseId === null ? (
          <p className="nav-hint">Open an investigation to see its workflow.</p>
        ) : (
          <>
            <div className="case-card">
              <span className="mono faint">{investigation?.code ?? `Investigation ${caseId}`}</span>
              {investigation ? <strong>{investigation.title}</strong> : null}
              <Link to="/investigations">Change case</Link>
            </div>
            <nav className="nav-section" aria-label="Investigation workflow">
              {WORKFLOW.map((step) => (
                <Item key={step.key} to={investigationPath(caseId, step.key)} icon={step.icon}>
                  {step.label}
                </Item>
              ))}
            </nav>
          </>
        )}
        <div className="nav-spacer" />
        <nav className="nav-section" aria-label="Account">
          <Item to="/profile" icon="user">
            Profile
          </Item>
          <Item to="/settings" icon="settings">
            Settings
          </Item>
          <button type="button" className="nav-link" onClick={onSignOut}>
            <Icon name="logout" />
            <span>Sign out</span>
          </button>
        </nav>
      </aside>
    </>
  );
}
