// SYNTHETIC values with the shape of the real API answers (docs/api-contract.md).

export const USER = { id: 1, name: 'Ada Lovelace', email: 'ada@example.com', organization: 'Analytical Engines', created_at: '2026-09-21T10:15:30.123Z' };

export const HEALTH = { status: 'ok', service: 'raven-api', version: '0.1.0', environment: 'development', registry: 'ok', rules_loaded: 3, rarf_version: '1.0' };

export const INVESTIGATION = {
  id: 1,
  code: 'INV-2026-001',
  title: 'Boot activity',
  description: null,
  host: 'HOST-1',
  status: 'open',
  severity: 'HIGH',
  stage: 'report',
  analysis_status: 'completed',
  analyst: { id: 1, name: 'Ada Lovelace' },
  counts: { evidence: 1, detections: 87, sessions: 1, timeline_events: 597 },
  created_at: '2026-09-21T10:15:30.123Z',
  updated_at: '2026-09-21T10:16:30.123Z',
};

export const DASHBOARD = {
  totals: { investigations: 2, active_investigations: 1, open_cases: 1, evidence_items: 3, sessions: 1, high_severity_findings: 73 },
  cases_by_severity: { HIGH: 1, MEDIUM: 0, LOW: 0, INFO: 0, none: 1 },
  cases_by_status: { open: 1, active: 1, closed: 0 },
  findings_by_severity: { HIGH: 73, MEDIUM: 14, LOW: 0, INFO: 0 },
  evidence_by_status: { uploaded: 1, processing: 0, ready: 2, failed: 0 },
  recent_investigations: [
    { ...INVESTIGATION, id: 2, code: 'INV-2026-002', title: 'Waiting for evidence', severity: null, status: 'active', counts: { evidence: 0, detections: 0, sessions: 0, timeline_events: 0 } },
    INVESTIGATION,
  ],
  latest_session: null,
  alerts: [],
  recent_activity: [],
  evidence_queue: [],
};

export const EMPTY_DASHBOARD = {
  ...DASHBOARD,
  totals: { investigations: 0, active_investigations: 0, open_cases: 0, evidence_items: 0, sessions: 0, high_severity_findings: 0 },
  recent_investigations: [],
};

export const EVIDENCE_ITEM = {
  id: 1,
  investigation_id: 1,
  filename: 'sysmon_export.evtx',
  sha256: '4F2F825EF88B6E7B79C61BB15D5C55EAB05B5017ABE064146AA5B69DECBE5708',
  size_bytes: 3215360,
  source_type: 'evtx_upload',
  status: 'ready',
  events_total: 2816,
  error: null,
  created_at: '2026-09-21T10:16:00.000Z',
  ingested_at: '2026-09-21T10:17:10.000Z',
};

// counts that add up to 2719 stored events
export const BREAKDOWN = [
  { event_id: 1, event_type: 'process_creation', count: 500 },
  { event_id: 11, event_type: 'file_create', count: 2000 },
  { event_id: 7, event_type: 'unsupported', count: 219 },
];

const STAGE_NAMES = ['collect', 'normalize', 'deduplicate', 'ingest', 'correlate', 'reconstruct', 'timeline', 'impact', 'rarf', 'report'];

export function analysisRun(status, completed = 0, extra = {}) {
  return {
    id: 1,
    investigation_id: 1,
    status,
    stage: status === 'completed' ? 'report' : STAGE_NAMES[Math.min(completed, 9)],
    error: null,
    started_at: '2026-09-21T10:16:05.000Z',
    finished_at: status === 'completed' || status === 'failed' ? '2026-09-21T10:16:25.300Z' : null,
    stages: STAGE_NAMES.slice(0, status === 'completed' ? 10 : Math.min(completed + 1, 10)).map((name, index) => ({
      name,
      status: index < completed || status === 'completed' ? 'completed' : 'running',
      started_at: '2026-09-21T10:16:05.000Z',
      finished_at: null,
      summary: null,
      error: null,
    })),
    ...extra,
  };
}
