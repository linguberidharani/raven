import { describe, expect, it } from 'vitest';
import { ApiError, errorFromResponse } from './errors';

describe('errorFromResponse', () => {
  it('reads detail, code and request ID', () => {
    const error = errorFromResponse(401, { detail: 'Wrong.', code: 'invalid_credentials', request_id: 'abc' });
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 401, code: 'invalid_credentials', detail: 'Wrong.', requestId: 'abc', message: 'Wrong.', name: 'ApiError' });
    expect(error.fields).toEqual({});
  });
  it('turns the list of a 422 into field messages', () => {
    const error = errorFromResponse(422, {
      detail: [
        { loc: ['body', 'password'], msg: 'String should have at least 10 characters' },
        { loc: ['body', 'email'], msg: 'Not a valid email address' },
        { loc: ['body', 'password'], msg: 'A second message' },
        { loc: [], msg: 'General problem' },
      ],
      code: 'validation_error',
      request_id: 'r',
    });
    expect(error.fields).toEqual({ password: 'String should have at least 10 characters', email: 'Not a valid email address' });
    expect(error.detail).toBe('password: String should have at least 10 characters; email: Not a valid email address; password: A second message; General problem');
    expect(error.code).toBe('validation_error');
  });
  it('still gives a clear message for a body that is not the API shape', () => {
    for (const payload of [null, undefined, 'text', [1], {}, { detail: '' }, { detail: 5 }, { detail: [] }]) {
      const error = errorFromResponse(502, payload);
      expect(error).toMatchObject({ status: 502, code: 'http_error', requestId: null });
      expect(error.detail).toBe('The server answered with an error (HTTP 502).');
    }
  });
  it('ignores a request ID that is not text', () => {
    expect(errorFromResponse(500, { detail: 'x', code: 'internal_error', request_id: 5 }).requestId).toBeNull();
  });
});
