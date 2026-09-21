// The only place that calls fetch. Same origin (the Vite proxy forwards /api to the backend), the session cookie
// travels by itself. Every failure becomes an ApiError; nothing else is thrown except an aborted request.

import { demoRequest } from '../demo';
import { ApiError, errorFromResponse } from './errors';

let unauthorizedHandler = null;

/** Called when a request that needed a session gets 401 (the session ended). Set by the auth provider. */
export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler;
}

export function dataSource() {
  return import.meta.env.VITE_DATA_SOURCE === 'demo' ? 'demo' : 'api';
}

export function buildUrl(path, params) {
  if (!params) return path;
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    query.append(key, String(value));
  }
  const text = query.toString();
  return text ? `${path}${path.includes('?') ? '&' : '?'}${text}` : path;
}

function requestId() {
  const crypto = globalThis.crypto;
  return crypto && typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : null;
}

export async function request(method, path, { body, form, params, signal, silent401 = false } = {}) {
  if (dataSource() === 'demo') return demoRequest(method, path, { body, params });

  const headers = { Accept: 'application/json' };
  const id = requestId();
  if (id) headers['X-Request-ID'] = id;
  const init = { method, headers, credentials: 'same-origin', signal };
  if (form !== undefined) {
    // multipart: the browser sets the Content-Type with its boundary
    init.body = form;
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(buildUrl(path, params), init);
  } catch (error) {
    if (error?.name === 'AbortError') throw error;
    throw new ApiError({ status: 0, code: 'network_error', detail: 'The RAVEN server cannot be reached. Check that the backend is running.' });
  }

  if (response.status === 204) return null;

  let text = '';
  try {
    text = await response.text();
  } catch (error) {
    if (error?.name === 'AbortError') throw error;
  }
  let payload = null;
  let parsed = true;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      parsed = false;
    }
  }

  if (!response.ok) {
    const error = errorFromResponse(response.status, parsed ? payload : null);
    if (response.status === 401 && error.code === 'not_authenticated' && !silent401 && unauthorizedHandler) unauthorizedHandler(error);
    throw error;
  }
  if (!parsed) throw new ApiError({ status: response.status, code: 'invalid_response', detail: 'The server sent an answer that is not JSON.' });
  return payload;
}

export const get = (path, options) => request('GET', path, options);
export const post = (path, body, options) => request('POST', path, { ...options, body });
export const patch = (path, body, options) => request('PATCH', path, { ...options, body });

/** Uploads one file as multipart/form-data in the field "file". */
export function upload(path, file, options) {
  const form = new FormData();
  form.append('file', file, file.name);
  return request('POST', path, { ...options, form });
}
