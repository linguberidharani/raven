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

export const RULES = [
  {
    rule_id: 'RAVEN-R001',
    rule_name: 'Mass File Modification Burst',
    description: 'A process is created and, within 60 seconds, five or more file creation events are recorded for the same process ID.',
    severity: 'HIGH',
    confidence: 85,
    match_key: 'process_id',
    time_window_seconds: 60,
    steps: [{ event_type: 'process_creation', min_count: 1 }, { event_type: 'file_create', min_count: 5 }],
    enabled: true,
    groups: 19,
  },
  {
    rule_id: 'RAVEN-R002',
    rule_name: 'Process Network File Stager Pattern',
    description: 'A process is created, then makes a network connection, then a file creation event follows.',
    severity: 'MEDIUM',
    confidence: 75,
    match_key: 'process_id',
    time_window_seconds: 120,
    steps: [{ event_type: 'process_creation', min_count: 1 }, { event_type: 'network_connection', min_count: 1 }, { event_type: 'file_create', min_count: 1 }],
    enabled: true,
    groups: 0,
  },
  {
    rule_id: 'RAVEN-R003',
    rule_name: 'Sustained File Creation Burst',
    description: 'Ten or more file creation events are recorded for the same process ID.',
    severity: 'HIGH',
    confidence: 80,
    match_key: 'process_id',
    time_window_seconds: 60,
    steps: [{ event_type: 'file_create', min_count: 10 }],
    enabled: true,
    groups: 54,
  },
];

export function detectionGroup(number, rule = RULES[0], refs = ['1:1', '1:2', '1:3']) {
  return {
    group_id: `${rule.rule_id}:${1000 + number}:2026-09-13T08:39:49.545Z`,
    rule_id: rule.rule_id,
    rule_name: rule.rule_name,
    severity: rule.severity,
    confidence: rule.confidence,
    match_key: 'process_id',
    match_value: String(1000 + number),
    time_window_seconds: rule.time_window_seconds,
    window_start: '2026-09-13T08:39:49.545Z',
    window_end: '2026-09-13T08:39:54.545Z',
    event_count: refs.length,
    why: {
      basis: 'derived',
      text: `For process ID ${1000 + number}, the recorded events satisfy rule ${rule.rule_id}.`,
      steps: rule.steps.map((step) => ({ event_type: step.event_type, required: step.min_count, found: step.min_count })),
    },
    interpretation: { basis: 'derived', text: `The recorded events match the pattern of ${rule.rule_name}. A matching pattern alone does not show the purpose of the activity.` },
    evidence: { event_ids: refs.map((_, index) => index + 1), raw_event_refs: refs },
  };
}

export const DETECTIONS = {
  analysed: true,
  rules: RULES,
  counts: { total_groups: 73, by_rule: { 'RAVEN-R001': 19, 'RAVEN-R003': 54 }, by_severity: { HIGH: 73 } },
  groups: [detectionGroup(1), detectionGroup(2, RULES[2], ['1:10', '1:11'])],
  total: 73,
  page: 1,
  page_size: 20,
};

const chainEntry = (number, rule, events) => ({
  group_id: detectionGroup(number, rule).group_id,
  rule_id: rule.rule_id,
  rule_name: rule.rule_name,
  severity: rule.severity,
  match_value: String(1000 + number),
  start_time: `2026-09-13T08:39:${40 + number}.545Z`,
  end_time: `2026-09-13T08:39:${45 + number}.545Z`,
  event_count: events.length,
  events,
  interpretation: { basis: 'derived', text: `Interpretation of group ${number}.` },
});

const anEvent = (id, type, text) => ({ event_id: id, raw_event_ref: `1:${id}`, timestamp: `2026-09-13T08:39:49.${500 + id}Z`, event_type: type, description: text });

export function chainOf(count) {
  return Array.from({ length: count }, (_, index) => chainEntry(index + 1, index % 2 === 0 ? RULES[0] : RULES[2], [anEvent(index + 1, 'file_create', `File created: C:\\Temp\\file_${index}.txt`)]));
}

const node = (guid, pid, image, extra = {}) => ({
  process_guid: guid,
  process_id: pid,
  image,
  user: 'LAB\\tester',
  parent_process_guid: null,
  parent_process_id: null,
  parent_image: null,
  first_seen: '2026-09-13T08:39:49.545Z',
  last_seen: '2026-09-13T08:43:09.488Z',
  event_counts: { file_create: 20 },
  group_ids: ['g1', 'g2'],
  in_session: true,
  basis: 'observed',
  child_guids: [],
  ...extra,
});

export const SESSION = {
  session_id: 'RAVEN-SESSION-LAB-R001-1001',
  computer: 'LAB-HOST',
  start_time: '2026-09-13T08:39:49.545Z',
  end_time: '2026-09-13T08:43:09.488Z',
  duration_ms: 199943,
  severity: 'HIGH',
  confidence: null,
  description: 'Reconstructed attack session containing 3 correlation group(s) from rule(s): RAVEN-R001, RAVEN-R003.',
  group_count: 3,
  rule_ids: ['RAVEN-R001', 'RAVEN-R003'],
  chain: [
    chainEntry(1, RULES[0], [anEvent(1, 'process_creation', 'Process created: C:\\Test\\a.exe (PID 1001)'), anEvent(2, 'file_create', 'File created: C:\\Temp\\one.txt')]),
    chainEntry(2, RULES[2], [anEvent(3, 'file_create', 'File created: C:\\Temp\\two.txt')]),
    chainEntry(3, RULES[2], [anEvent(4, 'file_create', 'File created: C:\\Temp\\three.txt')]),
  ],
  process_tree: {
    nodes: [
      node('{P1}', 1001, 'C:\\Test\\a.exe', { parent_process_guid: '{P0}', child_guids: ['{P2}'] }),
      node('{P0}', 900, 'C:\\Windows\\explorer.exe', { in_session: false, first_seen: null, last_seen: null, user: null, event_counts: {}, group_ids: [], child_guids: ['{P1}'] }),
      node('{P2}', 1002, 'C:\\Windows\\System32\\cmd.exe', { parent_process_guid: '{P1}', event_counts: { process_creation: 1 }, group_ids: ['g3'] }),
    ],
    roots: ['{P0}'],
  },
};

export const RECONSTRUCTION = { sessions: [SESSION] };

export const EVENT_DETAIL = {
  raw_event_ref: '1:1',
  event: {
    id: 1,
    raw_event_ref: '1:1',
    event_id: 1,
    event_type: 'process_creation',
    timestamp: '2026-09-13T08:39:49.545Z',
    computer: 'LAB-HOST',
    process_id: 1001,
    process_name: 'C:\\Test\\a.exe',
    command_line: 'a.exe --run',
    hash_md5: null,
    normalization_status: 'OK',
  },
  raw: { event_id: 1, time_created: '2026-09-13 08:39:49.545000+00:00', computer: 'LAB-HOST', record_id: 1, event_data: { ProcessId: '1001', Image: 'C:\\Test\\a.exe' } },
  raw_xml: '<Event><System><EventID>1</EventID></System></Event>',
  groups: [{ group_id: 'RAVEN-R001:1001:2026-09-13T08:39:49.545Z', rule_id: 'RAVEN-R001', basis: 'derived' }],
  timeline: { session_id: 'RAVEN-SESSION-LAB-R001-1001', sequence_number: 4, description: 'Process created: C:\\Test\\a.exe' },
};
