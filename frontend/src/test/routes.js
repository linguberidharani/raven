import { BREAKDOWN, DASHBOARD, EVIDENCE_ITEM, HEALTH, INVESTIGATION, USER } from './fixtures';

export const me = { 'GET /api/auth/me': { body: USER } };

/** The answers of a signed-in user who opens one investigation. `overrides` replace single routes. */
export function caseRoutes(investigation = INVESTIGATION, overrides = {}) {
  const base = `/api/investigations/${investigation.id}`;
  return {
    ...me,
    [`GET ${base}`]: { body: investigation },
    [`GET ${base}/evidence`]: { body: { items: [EVIDENCE_ITEM], event_breakdown: BREAKDOWN } },
    [`GET ${base}/analysis`]: { body: null },
    [`GET ${base}/collector`]: { body: { items: [] } },
    'GET /api/inbox': { body: { items: [] } },
    'GET /api/dashboard': { body: DASHBOARD },
    'GET /api/health': { body: HEALTH },
    'GET /api/investigations': { body: { items: [investigation], total: 1, page: 1, page_size: 20 } },
    ...overrides,
  };
}
