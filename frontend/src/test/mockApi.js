import { vi } from 'vitest';

export function jsonResponse(status, body) {
  const empty = body === null || body === undefined || status === 204;
  return new Response(empty ? null : JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

/**
 * Replaces fetch with a table of answers keyed "METHOD /path" (the query string is ignored for the match).
 * A handler is { status, body }, or a function returning one (or an Error to simulate a network failure).
 */
export function mockApi(routes) {
  const calls = [];
  const fetchMock = vi.fn(async (url, init = {}) => {
    const method = (init.method ?? 'GET').toUpperCase();
    const path = String(url).split('?')[0];
    const call = { method, url: String(url), path, body: typeof init.body === 'string' ? JSON.parse(init.body) : init.body, init };
    calls.push(call);
    const handler = routes[`${method} ${path}`];
    if (!handler) return jsonResponse(404, { detail: `no mock for ${method} ${path}`, code: 'not_found', request_id: 'test' });
    const result = typeof handler === 'function' ? await handler(call) : handler;
    if (result instanceof Error) throw result;
    return jsonResponse(result.status ?? 200, result.body ?? null);
  });
  vi.stubGlobal('fetch', fetchMock);
  return { calls, fetchMock };
}

export const notAuthenticated = { status: 401, body: { detail: 'Not signed in.', code: 'not_authenticated', request_id: 'req-401' } };
