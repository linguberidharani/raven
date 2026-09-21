import { afterEach, describe, expect, it, vi } from 'vitest';
import { buildUrl, dataSource, get, patch, post, request, setUnauthorizedHandler } from './client';
import { ApiError } from './errors';
import { DEMO_USER } from '../demo';
import { jsonResponse, mockApi } from '../test/mockApi';

afterEach(() => setUnauthorizedHandler(null));

describe('buildUrl', () => {
  it('adds the parameters that have a value', () => {
    expect(buildUrl('/api/x')).toBe('/api/x');
    expect(buildUrl('/api/x', {})).toBe('/api/x');
    expect(buildUrl('/api/x', { page: 2, q: 'a b', empty: '', none: null, missing: undefined, zero: 0, no: false })).toBe('/api/x?page=2&q=a+b&zero=0&no=false');
    expect(buildUrl('/api/x?a=1', { b: 2 })).toBe('/api/x?a=1&b=2');
  });
});

describe('request', () => {
  it('sends a same-origin JSON request with a request ID and returns the parsed answer', async () => {
    const { fetchMock } = mockApi({ 'GET /api/dashboard': { body: { totals: { investigations: 1 } } } });
    const answer = await get('/api/dashboard', { params: { page: 1 } });
    expect(answer).toEqual({ totals: { investigations: 1 } });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/dashboard?page=1');
    expect(init).toMatchObject({ method: 'GET', credentials: 'same-origin' });
    expect(init.headers.Accept).toBe('application/json');
    expect(init.headers['X-Request-ID']).toMatch(/^[A-Za-z0-9._-]{1,64}$/);
    expect(init.body).toBeUndefined();
    expect(init.headers['Content-Type']).toBeUndefined();
  });

  it('sends a JSON body with POST and PATCH', async () => {
    const { calls } = mockApi({ 'POST /api/things': { status: 201, body: { id: 1 } }, 'PATCH /api/things/1': { body: { id: 1 } } });
    expect(await post('/api/things', { title: 'x' })).toEqual({ id: 1 });
    expect(await patch('/api/things/1', { status: 'active' })).toEqual({ id: 1 });
    expect(calls[0].body).toEqual({ title: 'x' });
    expect(calls[0].init.headers['Content-Type']).toBe('application/json');
    expect(calls[1]).toMatchObject({ method: 'PATCH', body: { status: 'active' } });
  });

  it('returns null for 204', async () => {
    mockApi({ 'POST /api/auth/logout': { status: 204 } });
    expect(await post('/api/auth/logout')).toBeNull();
  });

  it('turns an error answer into an ApiError with detail, code and request ID', async () => {
    mockApi({ 'GET /api/x': { status: 404, body: { detail: 'No such thing.', code: 'investigation_not_found', request_id: 'req-9' } } });
    const error = await get('/api/x').catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 404, code: 'investigation_not_found', detail: 'No such thing.', requestId: 'req-9' });
  });

  it('maps validation errors to fields', async () => {
    mockApi({ 'POST /api/auth/register': { status: 422, body: { detail: [{ loc: ['body', 'email'], msg: 'bad' }], code: 'validation_error', request_id: 'r' } } });
    const error = await post('/api/auth/register', {}).catch((e) => e);
    expect(error.fields).toEqual({ email: 'bad' });
  });

  it('copes with an error page that is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('<html>Bad gateway</html>', { status: 502 })));
    const error = await get('/api/x').catch((e) => e);
    expect(error).toMatchObject({ status: 502, code: 'http_error', detail: 'The server answered with an error (HTTP 502).' });
  });

  it('rejects a good status with a body that is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('not json', { status: 200 })));
    const error = await get('/api/x').catch((e) => e);
    expect(error).toMatchObject({ code: 'invalid_response', status: 200 });
  });

  it('says clearly when the server cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch'); }));
    const error = await get('/api/x').catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 0, code: 'network_error' });
    expect(error.detail).toContain('cannot be reached');
  });

  it('passes an aborted request on unchanged', async () => {
    const abort = new DOMException('Aborted', 'AbortError');
    vi.stubGlobal('fetch', vi.fn(async () => { throw abort; }));
    await expect(get('/api/x')).rejects.toBe(abort);
  });

  it('tells the auth provider when the session is gone, but not for silent requests or other 401 codes', async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    mockApi({
      'GET /api/a': { status: 401, body: { detail: 'Not signed in.', code: 'not_authenticated', request_id: 'r' } },
      'POST /api/auth/login': { status: 401, body: { detail: 'Wrong.', code: 'invalid_credentials', request_id: 'r' } },
    });
    await get('/api/a').catch(() => {});
    expect(handler).toHaveBeenCalledTimes(1);
    await get('/api/a', { silent401: true }).catch(() => {});
    await post('/api/auth/login', {}).catch(() => {});
    expect(handler).toHaveBeenCalledTimes(1);
  });
});

describe('demo data source', () => {
  it('is off by default and uses the network', async () => {
    expect(dataSource()).toBe('api');
    const { fetchMock } = mockApi({ 'GET /api/auth/me': { body: { id: 1 } } });
    await get('/api/auth/me');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('answers from the demo data without any network request when switched on', async () => {
    vi.stubEnv('VITE_DATA_SOURCE', 'demo');
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    expect(dataSource()).toBe('demo');
    expect(await request('GET', '/api/auth/me')).toEqual(DEMO_USER);
    expect((await get('/api/dashboard')).totals.investigations).toBe(2);
    expect(await post('/api/auth/logout')).toBeNull();
    const error = await get('/api/investigations/1/timeline').catch((e) => e);
    expect(error).toMatchObject({ status: 404, code: 'demo_not_available' });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('treats any other value as the real API', () => {
    vi.stubEnv('VITE_DATA_SOURCE', 'mock');
    expect(dataSource()).toBe('api');
  });
});

describe('jsonResponse helper', () => {
  it('builds a JSON response', async () => {
    expect(await jsonResponse(200, { a: 1 }).json()).toEqual({ a: 1 });
  });
});
