import { useLocation } from 'react-router-dom';
import { breadcrumbsFor } from '../utils/navigation';
import { Breadcrumbs } from './Breadcrumbs';

/** Breadcrumbs, the page title (the one h1 of the page) and an optional subtitle and actions. */
export function PageHeader({ title, subtitle, actions }) {
  const { pathname } = useLocation();
  return (
    <div className="page-header">
      <Breadcrumbs items={breadcrumbsFor(pathname)} />
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
        <div style={{ minWidth: 0 }}>
          <h1>{title}</h1>
          {subtitle ? <p className="page-subtitle">{subtitle}</p> : null}
        </div>
        {actions}
      </div>
    </div>
  );
}
