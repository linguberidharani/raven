/** The title (the one h1 of the page) with an optional subtitle and actions. Breadcrumbs are in the top bar. */
export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="page-header">
      <div className="page-header-row">
        <div style={{ minWidth: 0 }}>
          <h1>{title}</h1>
          {subtitle ? <p className="page-subtitle">{subtitle}</p> : null}
        </div>
        {actions}
      </div>
    </div>
  );
}

/** The heading (h2) of one step of an investigation; the h1 of those pages is the investigation title. */
export function SectionHeader({ title, subtitle, actions }) {
  return (
    <div className="section-header">
      <div style={{ minWidth: 0 }}>
        <h2 className="section-title">{title}</h2>
        {subtitle ? <p className="page-subtitle">{subtitle}</p> : null}
      </div>
      {actions}
    </div>
  );
}
