// Demo data for design work and screenshots (VITE_DATA_SOURCE=demo). It is invented on purpose, is labelled as such
// on every screen, and is never used unless demo mode is switched on. It is NOT telemetry.

import { ApiError } from '../api/errors';

const NOW = '2026-01-01T00:00:00.000Z';

export const DEMO_USER = { id: 0, name: 'Demo Analyst', email: 'demo@example.invalid', organization: 'Demo organization', created_at: NOW };

const investigation = (id, code, title, status, severity, stage) => ({
  id,
  code,
  title,
  description: null,
  host: 'DEMO-HOST',
  status,
  severity,
  stage,
  analysis_status: stage ? 'completed' : null,
  analyst: { id: 0, name: DEMO_USER.name },
  counts: { evidence: 1, detections: severity ? 12 : 0, sessions: severity ? 1 : 0, timeline_events: severity ? 120 : 0 },
  created_at: NOW,
  updated_at: NOW,
});

export const DEMO_DASHBOARD = {
  totals: { investigations: 2, active_investigations: 1, open_cases: 1, evidence_items: 2, sessions: 1, high_severity_findings: 8 },
  cases_by_severity: { HIGH: 1, MEDIUM: 0, LOW: 0, INFO: 0, none: 1 },
  cases_by_status: { open: 1, active: 1, closed: 0 },
  findings_by_severity: { HIGH: 8, MEDIUM: 4, LOW: 0, INFO: 0 },
  evidence_by_status: { uploaded: 1, processing: 0, ready: 1, failed: 0 },
  recent_investigations: [
    investigation(2, 'DEMO-002', 'Demo case without analysis', 'open', null, null),
    investigation(1, 'DEMO-001', 'Demo case with an analysed session', 'active', 'HIGH', 'report'),
  ],
  latest_session: null,
  alerts: [],
  recent_activity: [],
  evidence_queue: [],
};

export const DEMO_HEALTH = { status: 'ok', service: 'raven-api', version: 'demo', environment: 'demo', registry: 'ok', rules_loaded: 3, rarf_version: '1.0' };

const ROUTES = {
  'GET /api/auth/me': () => DEMO_USER,
  'POST /api/auth/login': () => DEMO_USER,
  'POST /api/auth/register': () => DEMO_USER,
  'POST /api/auth/logout': () => null,
  'GET /api/dashboard': () => DEMO_DASHBOARD,
  'GET /api/health': () => DEMO_HEALTH,
};

export async function demoRequest(method, path) {
  const handler = ROUTES[`${method} ${path.split('?')[0]}`];
  if (!handler) throw new ApiError({ status: 404, code: 'demo_not_available', detail: 'There is no demo data for this page.' });
  return handler();
}
