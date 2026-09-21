// The error of a failed request. The API answers with { detail, code, request_id }; a 422 has a list in detail.

export class ApiError extends Error {
  constructor({ status = 0, code = 'error', detail = 'The request failed.', requestId = null, fields = {} } = {}) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.requestId = requestId;
    this.fields = fields;
  }
}

/** Turns the JSON body of an error response into an ApiError. Anything unexpected still gives a clear message. */
export function errorFromResponse(status, payload) {
  const body = payload !== null && typeof payload === 'object' && !Array.isArray(payload) ? payload : {};
  const requestId = typeof body.request_id === 'string' ? body.request_id : null;
  const code = typeof body.code === 'string' ? body.code : 'http_error';
  let detail = `The server answered with an error (HTTP ${status}).`;
  const fields = {};
  if (typeof body.detail === 'string' && body.detail) {
    detail = body.detail;
  } else if (Array.isArray(body.detail) && body.detail.length > 0) {
    const messages = [];
    for (const item of body.detail) {
      const message = typeof item?.msg === 'string' ? item.msg : 'Invalid value';
      const loc = Array.isArray(item?.loc) ? item.loc.filter((part) => typeof part === 'string' && part !== 'body') : [];
      const field = loc.length > 0 ? loc[loc.length - 1] : null;
      if (field && !(field in fields)) fields[field] = message;
      messages.push(field ? `${field}: ${message}` : message);
    }
    detail = messages.join('; ');
  }
  return new ApiError({ status, code, detail, requestId, fields });
}
