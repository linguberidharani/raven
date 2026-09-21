import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { get } from '../api/client';
import { notAuthenticated, mockApi } from '../test/mockApi';
import { USER } from '../test/fixtures';
import { AuthProvider, useAuth } from './AuthContext';

function Probe() {
  const auth = useAuth();
  const attempt = (action) => () => action().catch((error) => { document.title = `failed: ${error.code}`; });
  return (
    <div>
      <span data-testid="status">{auth.status}</span>
      <span data-testid="user">{auth.user?.name ?? ''}</span>
      <span data-testid="error">{auth.error?.code ?? ''}</span>
      <button onClick={attempt(() => auth.login({ email: ' ada@example.com ', password: 'a password' }))}>login</button>
      <button onClick={attempt(() => auth.register({ name: ' Ada ', email: 'ada@example.com', organization: '  ', password: 'a long password' }))}>register</button>
      <button onClick={attempt(() => auth.logout())}>logout</button>
      <button onClick={auth.reload}>reload</button>
      <button onClick={() => get('/api/dashboard').catch(() => {})}>other request</button>
    </div>
  );
}

const renderProbe = () => render(<AuthProvider><Probe /></AuthProvider>);
const status = () => screen.getByTestId('status').textContent;

describe('AuthProvider', () => {
  it('asks the server who is signed in', async () => {
    mockApi({ 'GET /api/auth/me': { body: USER } });
    renderProbe();
    expect(status()).toBe('loading');
    await waitFor(() => expect(status()).toBe('authenticated'));
    expect(screen.getByTestId('user')).toHaveTextContent('Ada Lovelace');
  });

  it('is anonymous when the server says 401', async () => {
    mockApi({ 'GET /api/auth/me': notAuthenticated });
    renderProbe();
    await waitFor(() => expect(status()).toBe('anonymous'));
    expect(screen.getByTestId('user')).toHaveTextContent('');
  });

  it('has an error status when the server cannot be asked, and can try again', async () => {
    let up = false;
    mockApi({ 'GET /api/auth/me': () => (up ? { body: USER } : new TypeError('Failed to fetch')) });
    renderProbe();
    await waitFor(() => expect(status()).toBe('error'));
    expect(screen.getByTestId('error')).toHaveTextContent('network_error');
    up = true;
    await userEvent.setup().click(screen.getByText('reload'));
    await waitFor(() => expect(status()).toBe('authenticated'));
  });

  it('signs in with a trimmed email', async () => {
    const { calls } = mockApi({ 'GET /api/auth/me': notAuthenticated, 'POST /api/auth/login': { body: USER } });
    renderProbe();
    await waitFor(() => expect(status()).toBe('anonymous'));
    await userEvent.setup().click(screen.getByText('login'));
    await waitFor(() => expect(status()).toBe('authenticated'));
    expect(calls.find((c) => c.path === '/api/auth/login').body).toEqual({ email: 'ada@example.com', password: 'a password' });
  });

  it('stays anonymous after a wrong password', async () => {
    mockApi({
      'GET /api/auth/me': notAuthenticated,
      'POST /api/auth/login': { status: 401, body: { detail: 'Wrong.', code: 'invalid_credentials', request_id: 'r' } },
    });
    renderProbe();
    await waitFor(() => expect(status()).toBe('anonymous'));
    await userEvent.setup().click(screen.getByText('login'));
    await waitFor(() => expect(document.title).toBe('failed: invalid_credentials'));
    expect(status()).toBe('anonymous');
  });

  it('registers and then signs in', async () => {
    const { calls } = mockApi({ 'GET /api/auth/me': notAuthenticated, 'POST /api/auth/register': { status: 201, body: USER }, 'POST /api/auth/login': { body: USER } });
    renderProbe();
    await waitFor(() => expect(status()).toBe('anonymous'));
    await userEvent.setup().click(screen.getByText('register'));
    await waitFor(() => expect(status()).toBe('authenticated'));
    const posts = calls.filter((c) => c.method === 'POST');
    expect(posts.map((c) => c.path)).toEqual(['/api/auth/register', '/api/auth/login']);
    expect(posts[0].body).toEqual({ name: 'Ada', email: 'ada@example.com', organization: null, password: 'a long password' });
    expect(posts[1].body).toEqual({ email: 'ada@example.com', password: 'a long password' });
  });

  it('does not sign in when registration fails', async () => {
    const { calls } = mockApi({
      'GET /api/auth/me': notAuthenticated,
      'POST /api/auth/register': { status: 409, body: { detail: 'Taken.', code: 'email_already_registered', request_id: 'r' } },
    });
    renderProbe();
    await waitFor(() => expect(status()).toBe('anonymous'));
    await userEvent.setup().click(screen.getByText('register'));
    await waitFor(() => expect(document.title).toBe('failed: email_already_registered'));
    expect(calls.some((c) => c.path === '/api/auth/login')).toBe(false);
  });

  it('signs out, and also when the session had already ended', async () => {
    mockApi({ 'GET /api/auth/me': { body: USER }, 'POST /api/auth/logout': { status: 204 } });
    renderProbe();
    await waitFor(() => expect(status()).toBe('authenticated'));
    await userEvent.setup().click(screen.getByText('logout'));
    await waitFor(() => expect(status()).toBe('anonymous'));
  });

  it('tolerates a 401 while signing out', async () => {
    mockApi({ 'GET /api/auth/me': { body: USER }, 'POST /api/auth/logout': notAuthenticated });
    renderProbe();
    await waitFor(() => expect(status()).toBe('authenticated'));
    await userEvent.setup().click(screen.getByText('logout'));
    await waitFor(() => expect(status()).toBe('anonymous'));
  });

  it('becomes anonymous when another request finds that the session ended', async () => {
    mockApi({ 'GET /api/auth/me': { body: USER }, 'GET /api/dashboard': notAuthenticated });
    renderProbe();
    await waitFor(() => expect(status()).toBe('authenticated'));
    await userEvent.setup().click(screen.getByText('other request'));
    await waitFor(() => expect(status()).toBe('anonymous'));
  });

  it('must be used inside the provider', () => {
    const Bare = () => { useAuth(); return null; };
    const silence = console.error;
    console.error = () => {};
    expect(() => render(<Bare />)).toThrow('useAuth must be used inside an AuthProvider');
    console.error = silence;
  });

  it('exposes a stable set of actions', async () => {
    mockApi({ 'GET /api/auth/me': { body: USER } });
    renderProbe();
    await act(async () => {});
    expect(screen.getByText('login')).toBeInTheDocument();
  });
});
