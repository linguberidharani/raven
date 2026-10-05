// The routes of the signed-in area and the workflow of one investigation (spec 9.3).

export const WORKFLOW = [
  { key: 'evidence', short: 'Evidence', label: 'Evidence & Log Upload', icon: 'upload' },
  { key: 'detection', short: 'Detection', label: 'Detection & Correlation', icon: 'shield' },
  { key: 'reconstruction', short: 'Reconstruction', label: 'Attack Reconstruction', icon: 'branch' },
  { key: 'timeline', short: 'Timeline', label: 'Attack Timeline', icon: 'clock' },
  { key: 'impact', short: 'Impact', label: 'Impact Analysis', icon: 'chart' },
  { key: 'rarf', short: 'RARF', label: 'RARF', icon: 'braces' },
  { key: 'report', short: 'Report', label: 'Investigation Report', icon: 'file' },
];

const WORKFLOW_LABELS = Object.fromEntries(WORKFLOW.map((step) => [step.key, step.label]));

export function investigationPath(id, step) {
  return step ? `/investigations/${id}/${step}` : `/investigations/${id}`;
}

/** { id, step } for /investigations/12/timeline, or null for any other path. */
export function matchInvestigation(pathname) {
  const match = /^\/investigations\/(\d+)(?:\/([a-z]+))?\/?$/.exec(pathname);
  if (!match || Number(match[1]) < 1) return null;
  const step = match[2] && WORKFLOW_LABELS[match[2]] ? match[2] : null;
  if (match[2] && !step) return null;
  return { id: Number(match[1]), step };
}

/** Breadcrumb items for a path: [{ label, to? }]. The last item has no link. */
export function breadcrumbsFor(pathname, caseCode = null) {
  if (pathname === '/dashboard') return [{ label: 'Dashboard' }];
  if (pathname === '/investigations') return [{ label: 'Investigations' }];
  if (pathname === '/profile') return [{ label: 'Profile' }];
  const found = matchInvestigation(pathname);
  if (found) {
    const items = [{ label: 'Investigations', to: '/investigations' }];
    const label = caseCode || `Investigation ${found.id}`;
    if (!found.step) return [...items, { label }];
    return [...items, { label, to: investigationPath(found.id) }, { label: WORKFLOW_LABELS[found.step] }];
  }
  return [{ label: 'Not found' }];
}

export function stepIndex(step) {
  return WORKFLOW.findIndex((item) => item.key === step);
}
