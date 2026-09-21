import { NavLink } from 'react-router-dom';
import { WORKFLOW, investigationPath } from '../utils/navigation';
import { stepStates } from '../utils/mapping';
import { Icon } from './Icons';

/** The seven steps of an investigation. A step is marked when the API says its data exists. */
export function InvestigationTabs({ investigation }) {
  const states = stepStates(investigation);
  return (
    <nav className="steps" aria-label="Investigation steps">
      <ol>
        {WORKFLOW.map((step, index) => (
          <li key={step.key}>
            <NavLink to={investigationPath(investigation.id, step.key)} className={({ isActive }) => `step${isActive ? ' active' : ''}${states[step.key] ? ' ready' : ''}`}>
              <span className="step-mark" aria-hidden="true">
                {states[step.key] ? <Icon name="check" size={14} /> : index + 1}
              </span>
              <span>{step.short}</span>
              <span className="sr-only">{states[step.key] ? ' (has data)' : ' (no data yet)'}</span>
            </NavLink>
          </li>
        ))}
      </ol>
    </nav>
  );
}
