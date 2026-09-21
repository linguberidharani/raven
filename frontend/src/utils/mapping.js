// Data-mapping helpers: API values -> labels and badge tones. They only name what the API says;
// they never compute a severity, a status or a finding.

export const SEVERITY_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];

const SEVERITY = {
  CRITICAL: { key: 'critical', label: 'Critical' },
  HIGH: { key: 'high', label: 'High' },
  MEDIUM: { key: 'medium', label: 'Medium' },
  LOW: { key: 'low', label: 'Low' },
  INFO: { key: 'info', label: 'Info' },
};

/** A severity as sent by the API (HIGH, MEDIUM, ...) or null (not analysed yet). */
export function severityInfo(value) {
  if (typeof value === 'string' && SEVERITY[value.toUpperCase()]) return SEVERITY[value.toUpperCase()];
  return { key: 'none', label: 'None' };
}

const STATUS = {
  open: { label: 'Open', tone: 'accent' },
  active: { label: 'Active', tone: 'success' },
  closed: { label: 'Closed', tone: 'neutral' },
  uploaded: { label: 'Uploaded', tone: 'neutral' },
  processing: { label: 'Processing', tone: 'accent' },
  ready: { label: 'Ready', tone: 'success' },
  failed: { label: 'Failed', tone: 'danger' },
  queued: { label: 'Queued', tone: 'neutral' },
  running: { label: 'Running', tone: 'accent' },
  completed: { label: 'Completed', tone: 'success' },
};

export function statusInfo(value) {
  if (typeof value === 'string' && STATUS[value]) return STATUS[value];
  return { label: typeof value === 'string' && value ? value : 'Not started', tone: 'neutral' };
}

const BASIS = {
  observed: { key: 'observed', label: 'Observed evidence' },
  derived: { key: 'derived', label: 'Derived / interpreted' },
};

/** "observed" (recorded in the telemetry) or "derived" (calculated or interpreted). */
export function basisInfo(value) {
  return BASIS[value] ?? null;
}

export function initials(name) {
  if (typeof name !== 'string') return '?';
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  const letters = parts.length === 1 ? parts[0].slice(0, 2) : parts[0][0] + parts[parts.length - 1][0];
  return letters.toUpperCase();
}

export function plural(count, one, many = `${one}s`) {
  return `${count} ${count === 1 ? one : many}`;
}
