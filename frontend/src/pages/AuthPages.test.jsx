import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { DASHBOARD, USER } from '../test/fixtures';
import { mockApi, notAuthenticated } from '../test/mockApi';
import { renderApp } from '../test/render';

const signedOut = { 'GET /api/auth/me': notAuthenticated, 'GET /api/dashboard': { body: DASHBOARD }, 'GET /api/health': { body: {} } };

async function fillLogin(user, email = 'ada@example.com', password = 'correct horse') {
  if (email) await user.type(screen.getByLabelText('Email'), email);
  if (password) await user.type(screen.getByLabelText('Password'), password);
}

describe('signed-out access', () => {
  it('sends a visitor of a signed-in page to sign in and remembers where they wanted to go', async () => {
    mockApi(signedOut);
    renderApp('/investigations/3/timeline');
    expect(await screen.findByRole('heading', { level: 1, name: 'Analyst sign in' })).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('/login?next=%2Finvestigations%2F3%2Ftimeline');
    expect(screen.getByText('Access your investigation workspace.')).toBeInTheDocument();
  });

  it('shows a clear error page when the server cannot be reached, with a retry', async () => {
    let up = false;
    mockApi({ 'GET /api/auth/me': () => (up ? notAuthenticated : new TypeError('Failed to fetch')), 'GET /api/dashboard': { body: DASHBOARD } });
    renderApp('/dashboard');
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('The RAVEN server could not be reached');
    expect(alert).toHaveTextContent('The RAVEN server cannot be reached. Check that the backend is running.');
    up = true;
    await userEvent.setup().click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('heading', { name: 'Analyst sign in' })).toBeInTheDocument();
  });
});

describe('sign in', () => {
  it('checks the fields before asking the server and puts the focus on the first problem', async () => {
    const { calls } = mockApi(signedOut);
    renderApp('/login');
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Sign in' }));
    const email = screen.getByLabelText('Email');
    expect(email).toHaveAttribute('aria-invalid', 'true');
    expect(email).toHaveAccessibleDescription('Enter your email address.');
    expect(screen.getByLabelText('Password')).toHaveAccessibleDescription('Enter your password.');
    expect(email).toHaveFocus();
    expect(calls.some((c) => c.path === '/api/auth/login')).toBe(false);
  });

  it('rejects an address that is not an email address', async () => {
    mockApi(signedOut);
    renderApp('/login');
    const user = userEvent.setup();
    await fillLogin(user, 'not-an-email');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(screen.getByLabelText('Email')).toHaveAccessibleDescription('Enter a valid email address.');
  });

  it('signs in and shows the dashboard', async () => {
    const { calls } = mockApi({ ...signedOut, 'POST /api/auth/login': { body: USER } });
    renderApp('/login');
    const user = userEvent.setup();
    await fillLogin(user);
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Dashboard' })).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/dashboard$/);
    expect(calls.find((c) => c.path === '/api/auth/login').body).toEqual({ email: 'ada@example.com', password: 'correct horse' });
    expect(within(screen.getByRole('banner')).getByText('Ada Lovelace')).toBeInTheDocument();
  });

  it('goes back to the page the visitor wanted', async () => {
    mockApi({ ...signedOut, 'POST /api/auth/login': { body: USER } });
    renderApp('/login?next=%2Fsettings');
    const user = userEvent.setup();
    await fillLogin(user);
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Settings' })).toBeInTheDocument();
  });

  it.each(['https://evil.example', '//evil.example', 'javascript:alert(1)'])('ignores an unsafe next address (%s)', async (next) => {
    mockApi({ ...signedOut, 'POST /api/auth/login': { body: USER } });
    renderApp(`/login?next=${encodeURIComponent(next)}`);
    const user = userEvent.setup();
    await fillLogin(user);
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Dashboard' })).toBeInTheDocument();
  });

  it('says so when the email or the password is wrong', async () => {
    mockApi({ ...signedOut, 'POST /api/auth/login': { status: 401, body: { detail: 'Invalid email or password.', code: 'invalid_credentials', request_id: 'r' } } });
    renderApp('/login');
    const user = userEvent.setup();
    await fillLogin(user, 'ada@example.com', 'wrong password');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('The email or the password is not correct.');
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled();
    expect(screen.getByLabelText('Password')).toHaveValue('wrong password');
  });

  it('shows the message of the server when it cannot be reached', async () => {
    mockApi({ ...signedOut, 'POST /api/auth/login': () => new TypeError('Failed to fetch') });
    renderApp('/login');
    const user = userEvent.setup();
    await fillLogin(user);
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('cannot be reached');
  });

  it('shows the fields that the server refused', async () => {
    mockApi({
      ...signedOut,
      'POST /api/auth/login': { status: 422, body: { detail: [{ loc: ['body', 'email'], msg: 'Refused by the server' }], code: 'validation_error', request_id: 'r' } },
    });
    renderApp('/login');
    const user = userEvent.setup();
    await fillLogin(user);
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    await waitFor(() => expect(screen.getByLabelText('Email')).toHaveAccessibleDescription('Refused by the server'));
  });

  it('can show and hide the password', async () => {
    mockApi(signedOut);
    renderApp('/login');
    const user = userEvent.setup();
    const input = await screen.findByLabelText('Password');
    expect(input).toHaveAttribute('type', 'password');
    await user.click(screen.getByRole('button', { name: 'Show password' }));
    expect(input).toHaveAttribute('type', 'text');
    expect(screen.getByRole('button', { name: 'Hide password' })).toHaveAttribute('aria-pressed', 'true');
    await user.click(screen.getByRole('button', { name: 'Hide password' }));
    expect(input).toHaveAttribute('type', 'password');
  });

  it('sends someone who is already signed in straight to the dashboard', async () => {
    mockApi({ ...signedOut, 'GET /api/auth/me': { body: USER } });
    renderApp('/login');
    expect(await screen.findByRole('heading', { level: 1, name: 'Dashboard' })).toBeInTheDocument();
  });

  it('links to registration', async () => {
    mockApi(signedOut);
    renderApp('/login');
    await userEvent.setup().click(await screen.findByRole('link', { name: 'Create an account' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Create an analyst account' })).toBeInTheDocument();
  });
});

describe('registration', () => {
  async function fillRegister(user, overrides = {}) {
    const values = { name: 'Ada Lovelace', email: 'ada@example.com', password: 'a long password', confirm: 'a long password', ...overrides };
    if (values.name) await user.type(screen.getByLabelText('Name'), values.name);
    if (values.email) await user.type(screen.getByLabelText('Email'), values.email);
    if (values.password) await user.type(screen.getByLabelText('Password'), values.password);
    if (values.confirm) await user.type(screen.getByLabelText('Confirm password'), values.confirm);
  }

  it('checks every field and explains the password rule', async () => {
    const { calls } = mockApi(signedOut);
    renderApp('/register');
    const user = userEvent.setup();
    expect(await screen.findByLabelText('Password')).toHaveAccessibleDescription('10 to 128 characters.');
    await user.click(screen.getByRole('button', { name: 'Create account' }));
    expect(screen.getByLabelText('Name')).toHaveAccessibleDescription('Enter your name.');
    expect(screen.getByLabelText('Email')).toHaveAccessibleDescription('Enter your email address.');
    expect(screen.getByLabelText('Password')).toHaveAccessibleDescription('10 to 128 characters. Choose a password.');
    expect(screen.getByLabelText(/Organization/)).toBeInTheDocument();
    expect(calls.some((c) => c.path === '/api/auth/register')).toBe(false);
  });

  it('needs the same password twice', async () => {
    mockApi(signedOut);
    renderApp('/register');
    const user = userEvent.setup();
    await screen.findByLabelText('Name');
    await fillRegister(user, { confirm: 'another password' });
    await user.click(screen.getByRole('button', { name: 'Create account' }));
    expect(screen.getByLabelText('Confirm password')).toHaveAccessibleDescription('The two passwords are not the same.');
  });

  it('creates the account, signs in and shows the dashboard', async () => {
    const { calls } = mockApi({ ...signedOut, 'POST /api/auth/register': { status: 201, body: USER }, 'POST /api/auth/login': { body: USER } });
    renderApp('/register');
    const user = userEvent.setup();
    await screen.findByLabelText('Name');
    await fillRegister(user);
    await user.type(screen.getByLabelText(/Organization/), 'Analytical Engines');
    await user.click(screen.getByRole('button', { name: 'Create account' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Dashboard' })).toBeInTheDocument();
    expect(calls.find((c) => c.path === '/api/auth/register').body).toEqual({ name: 'Ada Lovelace', email: 'ada@example.com', organization: 'Analytical Engines', password: 'a long password' });
  });

  it('says when the email already has an account', async () => {
    mockApi({ ...signedOut, 'POST /api/auth/register': { status: 409, body: { detail: 'Taken.', code: 'email_already_registered', request_id: 'r' } } });
    renderApp('/register');
    const user = userEvent.setup();
    await screen.findByLabelText('Name');
    await fillRegister(user);
    await user.click(screen.getByRole('button', { name: 'Create account' }));
    await waitFor(() => expect(screen.getByLabelText('Email')).toHaveAccessibleDescription('An account with this email address already exists. Sign in instead.'));
  });

  it('shows other refusals of the server in the form', async () => {
    mockApi({ ...signedOut, 'POST /api/auth/register': { status: 500, body: { detail: 'Internal server error', code: 'internal_error', request_id: 'r-1' } } });
    renderApp('/register');
    const user = userEvent.setup();
    await screen.findByLabelText('Name');
    await fillRegister(user);
    await user.click(screen.getByRole('button', { name: 'Create account' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Internal server error');
  });
});
