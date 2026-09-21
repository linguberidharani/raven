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
  latest_session: {
    investigation_id: 1,
    code: 'INV-2026-001',
    session_id: 'RAVEN-SESSION-LAB-R001-1001',
    start_time: '2026-09-13T08:39:49.545Z',
    end_time: '2026-09-13T08:43:09.488Z',
    severity: 'HIGH',
    chain: [
      { rule_id: 'RAVEN-R003', rule_name: 'Sustained File Creation Burst', severity: 'HIGH', groups: 54, first_start: '2026-09-13T08:39:49.545Z' },
      { rule_id: 'RAVEN-R001', rule_name: 'Mass File Modification Burst', severity: 'HIGH', groups: 19, first_start: '2026-09-13T08:39:52.100Z' },
      { rule_id: 'RAVEN-R002', rule_name: 'Process Network File Stager Pattern', severity: 'MEDIUM', groups: 1, first_start: '2026-09-13T08:40:10.000Z' },
    ],
  },
  alerts: [
    { investigation_id: 1, code: 'INV-2026-001', group_id: 'RAVEN-R003:4:2026-09-13T08:39:49.545Z', rule_id: 'RAVEN-R003', rule_name: 'Sustained File Creation Burst', severity: 'HIGH', window_start: '2026-09-13T08:39:49.545Z', event_count: 10 },
  ],
  recent_activity: [
    { time: '2026-09-21T10:20:00.000Z', kind: 'analysis_completed', investigation_id: 1, code: 'INV-2026-001', text: 'Analysis completed for INV-2026-001' },
    { time: '2026-09-21T10:16:00.000Z', kind: 'evidence_uploaded', investigation_id: 1, code: 'INV-2026-001', text: 'Evidence uploaded to INV-2026-001' },
  ],
  evidence_queue: [
    { id: 3, investigation_id: 2, code: 'INV-2026-002', filename: 'pending.evtx', status: 'uploaded', size_bytes: 100, error: null, created_at: '2026-09-21T11:00:00.000Z' },
  ],
};

export const EMPTY_DASHBOARD = {
  ...DASHBOARD,
  totals: { investigations: 0, active_investigations: 0, open_cases: 0, evidence_items: 0, sessions: 0, high_severity_findings: 0 },
  recent_investigations: [],
  latest_session: null,
  alerts: [],
  recent_activity: [],
  evidence_queue: [],
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

const tlItem = (n, type, text, time, groups = []) => ({
  timeline_event_id: n,
  session_id: 'RAVEN-SESSION-LAB-R001-1001',
  sequence_number: n,
  timestamp: time,
  description: text,
  computer: 'LAB-HOST',
  event_type: type,
  event_id: 1400 + n,
  sysmon_event_id: type === 'file_create' ? 11 : type === 'network_connection' ? 3 : 1,
  raw_event_ref: `1:${n}`,
  basis: 'observed',
  groups,
});

const grp = (rule, id) => ({ group_id: `${rule}:${id}:2026-09-13T08:39:49.545Z`, rule_id: rule, basis: 'derived' });

export const TIMELINE = {
  items: [
    tlItem(1, 'process_creation', 'Process created: C:\\Test\\a.exe (PID 1001)', '2026-09-13T08:39:49.545Z', [grp('RAVEN-R001', 1001)]),
    tlItem(2, 'file_create', 'File created: C:\\Temp\\one.txt', '2026-09-13T08:39:50.100Z', [grp('RAVEN-R001', 1001), grp('RAVEN-R003', 1001), grp('RAVEN-R003', 1002)]),
    tlItem(3, 'network_connection', 'Connection from a.exe to 203.0.113.45:443', '2026-09-13T08:40:02.250Z'),
  ],
  total: 3,
  page: 1,
  page_size: 50,
};

const category = (name, count, score, extra = {}) => ({
  category: name,
  impact_analysis_id: 1,
  observed: {
    basis: 'observed',
    event_count: count,
    affected_assets: Array.from({ length: score }, (_, i) => `asset-${i}`),
    top_assets: [{ asset: `C:\\Users\\lab\\${name}\\top.txt`, events: 3 }],
    details: { distinct_computers: 1, distinct_users: 3, distinct_processes: 16 },
    ...extra,
  },
  derived: { basis: 'derived', impact_score: score, definition: 'The number of distinct affected assets. A calculated count; it does not measure damage.' },
  evidence: { event_ids: [1, 2], raw_event_refs: ['1:1', '1:2'] },
});

export const IMPACT = {
  sessions: [
    {
      session_id: 'RAVEN-SESSION-LAB-R001-1001',
      categories: [category('files_affected', 558, 475), category('network_activity', 14, 12), category('process_activity', 25, 14), category('unsupported_events', 0, 0, { top_assets: [], affected_assets: [] })],
      activity: {
        basis: 'derived',
        bucket_seconds: 10,
        buckets: [
          { start: '2026-09-13T08:39:40.000Z', file_create: 3, network_connection: 0, process_creation: 1, total: 4 },
          { start: '2026-09-13T08:39:50.000Z', file_create: 10, network_connection: 2, process_creation: 0, total: 12 },
        ],
      },
    },
  ],
};

export const RULES_ANSWER = { rules: RULES };

const GROUP_IDS = ['RAVEN-R001:1001:2026-09-13T08:39:49.545Z', 'RAVEN-R003:1001:2026-09-13T08:39:51.545Z', 'RAVEN-R003:1001:2026-09-13T08:40:01.545Z'];

export const RARF_DOC = {
  rarf_version: '1.0',
  rarf_id: 'RARF-RAVEN-SESSION-LAB-R001-1001',
  attack_session: {
    session_id: 'RAVEN-SESSION-LAB-R001-1001',
    computer: 'LAB-HOST',
    start_time: '2026-09-13T08:39:49.545Z',
    end_time: '2026-09-13T08:43:09.488Z',
    severity: 'HIGH',
    confidence: null,
    description: 'Reconstructed attack session containing 3 correlation group(s).',
  },
  detection: {
    correlation_groups: GROUP_IDS.map((groupId, index) => ({ correlation_group_id: groupId, correlation_type: index === 0 ? 'RAVEN-R001' : 'RAVEN-R003', event_ids: [index + 1] })),
    rules: [
      { rule_database_id: 1, rule_id: 'RAVEN-R001', rule_name: 'Mass File Modification Burst', description: 'd', enabled: true, rule_definition: { severity: 'HIGH' } },
      { rule_database_id: 3, rule_id: 'RAVEN-R003', rule_name: 'Sustained File Creation Burst', description: 'd', enabled: true, rule_definition: { severity: 'HIGH' } },
    ],
    event_ids: [1, 2, 3, 4],
  },
  timeline: { events: [1, 2, 3, 4].map((n) => ({ timeline_event_id: n, event_id: n, sequence_number: n, timestamp: '2026-09-13T08:39:49.545Z', raw_event_ref: `1:${n}`, event_type: 'file_create', computer: 'LAB-HOST', user: null })) },
  impact: { categories: { files_affected: { impact_score: 3 }, network_activity: { impact_score: 0 }, process_activity: { impact_score: 1 }, unsupported_events: { impact_score: 0 } } },
  traceability: {
    event_ids: [1, 2, 3, 4],
    raw_event_refs: ['1:1', '1:2', '1:3', '1:4'],
    correlation_group_ids: GROUP_IDS,
    timeline_event_ids: [1, 2, 3, 4],
    impact_analysis_ids: [1, 2, 3, 4],
  },
};

const emptyEvidence = { event_ids: [], correlation_group_ids: [], timeline_event_ids: [], impact_analysis_ids: [], raw_event_refs: [] };
const finding = (statement, basis, evidence = {}) => ({ statement, basis, evidence: { ...emptyEvidence, ...evidence } });

export const REPORT_DOC = {
  report_title: 'Investigation Report: RAVEN-SESSION-LAB-R001-1001',
  attack_session_id: 1,
  session_id: 'RAVEN-SESSION-LAB-R001-1001',
  generated_at: '2026-09-21T18:25:36.725Z',
  sections: [
    { section_id: 'executive_summary', title: 'Executive summary', findings: [
      finding('RAVEN reconstructed one attack session on LAB-HOST.', 'observed', { raw_event_refs: ['1:1', '1:4'] }),
      finding('The session severity is HIGH: the highest severity of the matching rules.', 'derived', { correlation_group_ids: GROUP_IDS }),
    ] },
    { section_id: 'session_overview', title: 'Session overview', findings: [finding('Session ID: RAVEN-SESSION-LAB-R001-1001.', 'observed')] },
    { section_id: 'detection_evidence', title: 'Detection evidence', findings: [finding('Rule RAVEN-R001 matched 1 group.', 'derived', { correlation_group_ids: [GROUP_IDS[0]] })] },
    { section_id: 'timeline_summary', title: 'Timeline summary', findings: [finding('The timeline has 4 events.', 'observed', { raw_event_refs: ['1:1', '1:2', '1:3', '1:4'] })] },
    { section_id: 'impact_analysis', title: 'Impact analysis', findings: [finding('3 distinct files were affected.', 'derived')] },
    { section_id: 'evidence_traceability', title: 'Evidence traceability', findings: [finding('Every statement links to recorded events.', 'observed')] },
    { section_id: 'confidence_limitations', title: 'Confidence and limitations', findings: [
      finding('The telemetry does not show who carried out the activity or why.', 'derived'),
      finding('The session has no confidence value.', 'observed'),
    ] },
  ],
};
