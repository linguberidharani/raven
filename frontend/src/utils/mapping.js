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

const STEP_KEYS = ['evidence', 'detection', 'reconstruction', 'timeline', 'impact', 'rarf', 'report'];

/**
 * Which steps of an investigation have data, from the counts and the analysis status the API sends.
 * Nothing is computed about the incident: a step is "ready" when the API says its data exists.
 */
export function stepStates(investigation) {
  const counts = investigation?.counts ?? {};
  const analysed = investigation?.analysis_status === 'completed';
  const hasSession = analysed && (counts.sessions ?? 0) > 0;
  return {
    evidence: (counts.evidence ?? 0) > 0,
    detection: analysed,
    reconstruction: hasSession,
    timeline: analysed && (counts.timeline_events ?? 0) > 0,
    impact: hasSession,
    rarf: hasSession,
    report: hasSession,
  };
}

export function readySteps(investigation) {
  const states = stepStates(investigation);
  return STEP_KEYS.filter((key) => states[key]).length;
}

const EVENT_TYPES = {
  process_creation: 'Process created',
  network_connection: 'Network connection',
  file_create: 'File created',
  unsupported: 'Not supported by RAVEN',
};

export function eventTypeLabel(type) {
  return EVENT_TYPES[type] ?? (typeof type === 'string' && type ? type : 'Unknown');
}

const SOURCE_TYPES = { evtx_upload: 'EVTX upload', vm_collector: 'VM collector' };

export function sourceTypeLabel(type) {
  return SOURCE_TYPES[type] ?? (typeof type === 'string' && type ? type : 'Unknown');
}

export const ANALYSIS_STAGES = [
  { name: 'collect', label: 'Collect records' },
  { name: 'normalize', label: 'Normalize' },
  { name: 'deduplicate', label: 'Remove duplicates' },
  { name: 'ingest', label: 'Store events' },
  { name: 'correlate', label: 'Detect and correlate' },
  { name: 'reconstruct', label: 'Reconstruct session' },
  { name: 'timeline', label: 'Build timeline' },
  { name: 'impact', label: 'Analyse impact' },
  { name: 'rarf', label: 'Write RARF' },
  { name: 'report', label: 'Generate report' },
];

export function analysisStageLabel(name) {
  return ANALYSIS_STAGES.find((stage) => stage.name === name)?.label ?? name;
}

const STAGE_STATUS = {
  pending: { label: 'Waiting', tone: 'neutral' },
  running: { label: 'Running', tone: 'accent' },
  completed: { label: 'Done', tone: 'success' },
  failed: { label: 'Failed', tone: 'danger' },
};

export function stageStatusInfo(status) {
  return STAGE_STATUS[status] ?? { label: status || 'Waiting', tone: 'neutral' };
}

export function isRunActive(run) {
  return run?.status === 'queued' || run?.status === 'running';
}

/** RAVEN-R003 -> R003 */
export function shortRuleId(ruleId) {
  return typeof ruleId === 'string' ? ruleId.replace(/^RAVEN-/, '') : '';
}

/** C:\Windows\System32\svchost.exe -> svchost.exe */
export function pathBasename(path) {
  if (typeof path !== 'string' || path === '') return '';
  const parts = path.split(/[\\/]/);
  return parts[parts.length - 1] || path;
}

const MATCH_KEYS = { process_id: 'process ID', process_guid: 'process GUID', computer: 'computer' };

export function matchKeyLabel(key) {
  return MATCH_KEYS[key] ?? (typeof key === 'string' && key ? key.replace(/_/g, ' ') : 'key');
}

const FIELD_LABELS = {
  id: 'Database ID',
  event_id: 'Sysmon event ID',
  event_type: 'Event type',
  timestamp: 'Time (UTC)',
  computer: 'Computer',
  process_guid: 'Process GUID',
  process_id: 'Process ID',
  process_name: 'Process image',
  parent_process_guid: 'Parent GUID',
  parent_process_id: 'Parent process ID',
  parent_process_name: 'Parent image',
  command_line: 'Command line',
  parent_command_line: 'Parent command line',
  user: 'User',
  integrity_level: 'Integrity level',
  hash_sha256: 'SHA-256',
  hash_md5: 'MD5',
  hash_imphash: 'Import hash',
  hashes_raw: 'Hashes as recorded',
  ip_address: 'Destination IP',
  port: 'Destination port',
  source_ip: 'Source IP',
  source_port: 'Source port',
  protocol: 'Protocol',
  initiated: 'Initiated',
  file_path: 'File path',
  normalization_status: 'Normalization',
};

export function fieldLabel(name) {
  if (FIELD_LABELS[name]) return FIELD_LABELS[name];
  const text = String(name).replace(/_/g, ' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}
