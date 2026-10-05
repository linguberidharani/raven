import { get, post } from './client';

/** The signed-in user, or an ApiError with status 401. A 401 here is normal (nobody is signed in), so it stays quiet. */
export function getMe(signal) {
  return get('/api/auth/me', { signal, silent401: true });
}

export function login({ email, password }) {
  return post('/api/auth/login', { email: email.trim(), password }, { silent401: true });
}

export function register({ name, email, organization, password }) {
  const clean = (organization ?? '').trim();
  return post('/api/auth/register', { name: name.trim(), email: email.trim(), organization: clean === '' ? null : clean, password }, { silent401: true });
}

export function forgotPassword({ email }) {
  return post('/api/auth/forgot-password', { email: email.trim() }, { silent401: true });
}

export function resetPassword({ token, password }) {
  return post('/api/auth/reset-password', { token, password }, { silent401: true });
}

export function logout() {
  return post('/api/auth/logout', undefined, { silent401: true });
}
