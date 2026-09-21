import { NavLink } from 'react-router-dom';
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

/** Dashboard, Investigations, the workflow of the current case (when one is open), Profile, Settings, Sign out. */
export function Sidebar({ open, onClose, investigationId, onSignOut, id }) {
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
        {investigationId !== null ? (
          <nav className="nav-section" aria-label={`Investigation ${investigationId}`}>
            <div className="nav-heading">Investigation {investigationId}</div>
            {WORKFLOW.map((step) => (
              <Item key={step.key} to={investigationPath(investigationId, step.key)} icon={step.icon}>
                {step.label}
              </Item>
            ))}
          </nav>
        ) : null}
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
