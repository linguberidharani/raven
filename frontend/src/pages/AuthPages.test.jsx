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
    expect(document.title).toBe('Sign in | RAVEN');
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
    renderApp('/login?next=%2Fprofile');
    const user = userEvent.setup();
    await fillLogin(user);
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Profile' })).toBeInTheDocument();
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

  it('links to the forgot-password page', async () => {
    mockApi(signedOut);
    renderApp('/login');
    await userEvent.setup().click(await screen.findByRole('link', { name: 'Forgot password?' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Reset your password' })).toBeInTheDocument();
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

describe('forgot password', () => {
  it('checks the email before asking the server', async () => {
    const { calls } = mockApi(signedOut);
    renderApp('/forgot-password');
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Send reset link' }));
    const email = screen.getByLabelText('Email');
    expect(email).toHaveAttribute('aria-invalid', 'true');
    expect(email).toHaveAccessibleDescription('Enter your email address.');
    expect(email).toHaveFocus();
    expect(calls.some((c) => c.path === '/api/auth/forgot-password')).toBe(false);
  });

  it('rejects an address that is not an email address', async () => {
    mockApi(signedOut);
    renderApp('/forgot-password');
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Email'), 'not-an-email');
    await user.click(screen.getByRole('button', { name: 'Send reset link' }));
    expect(screen.getByLabelText('Email')).toHaveAccessibleDescription('Enter a valid email address.');
  });

  it('shows the same neutral message for a real and an unknown address, repeating what was typed', async () => {
    const { calls } = mockApi({ ...signedOut, 'POST /api/auth/forgot-password': { status: 202, body: { detail: 'If an account exists for that address, a password reset email has been sent.' } } });
    renderApp('/forgot-password');
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Email'), 'ada@example.com');
    await user.click(screen.getByRole('button', { name: 'Send reset link' }));
    expect(await screen.findByRole('heading', { name: 'Check your email' })).toBeInTheDocument();
    expect(screen.getByText('ada@example.com')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to sign in' })).toHaveAttribute('href', '/login');
    expect(calls.find((c) => c.path === '/api/auth/forgot-password').body).toEqual({ email: 'ada@example.com' });
  });

  it('trims the email before sending it', async () => {
    const { calls } = mockApi({ ...signedOut, 'POST /api/auth/forgot-password': { status: 202, body: { detail: 'ok' } } });
    renderApp('/forgot-password');
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Email'), '  ada@example.com  ');
    await user.click(screen.getByRole('button', { name: 'Send reset link' }));
    await screen.findByRole('heading', { name: 'Check your email' });
    expect(calls.find((c) => c.path === '/api/auth/forgot-password').body).toEqual({ email: 'ada@example.com' });
  });

  it('shows a network error and lets the analyst try again', async () => {
    mockApi({ ...signedOut, 'POST /api/auth/forgot-password': new TypeError('Failed to fetch') });
    renderApp('/forgot-password');
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Email'), 'ada@example.com');
    await user.click(screen.getByRole('button', { name: 'Send reset link' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('The RAVEN server cannot be reached. Check that the backend is running.');
    expect(screen.queryByRole('heading', { name: 'Check your email' })).not.toBeInTheDocument();
  });

  it('sends someone who is already signed in straight to the dashboard', async () => {
    mockApi({ ...signedOut, 'GET /api/auth/me': { body: USER } });
    renderApp('/forgot-password');
    expect(await screen.findByRole('heading', { level: 1, name: 'Dashboard' })).toBeInTheDocument();
  });

  it('sets the tab title', async () => {
    mockApi(signedOut);
    renderApp('/forgot-password');
    await screen.findByRole('heading', { level: 1, name: 'Reset your password' });
    expect(document.title).toBe('Reset your password | RAVEN');
  });
});

describe('reset password', () => {
  const OK = { status: 200, body: { detail: 'Your password has been updated. Sign in with your new password.' } };

  it('says the link is incomplete when there is no token in the address', async () => {
    mockApi(signedOut);
    renderApp('/reset-password');
    expect(await screen.findByRole('heading', { name: 'This link is not complete' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Request a new link' })).toHaveAttribute('href', '/forgot-password');
    expect(screen.queryByRole('button', { name: 'Update password' })).not.toBeInTheDocument();
  });

  it('checks the new password before asking the server', async () => {
    const { calls } = mockApi(signedOut);
    renderApp('/reset-password?token=abc123');
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Update password' }));
    expect(screen.getByLabelText('New password')).toHaveAccessibleDescription(/Choose a new password\./);
    expect(calls.some((c) => c.path === '/api/auth/reset-password')).toBe(false);
  });

  it('requires the two passwords to match', async () => {
    mockApi(signedOut);
    renderApp('/reset-password?token=abc123');
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('New password'), 'a brand new password');
    await user.type(screen.getByLabelText('Confirm new password'), 'a different password');
    await user.click(screen.getByRole('button', { name: 'Update password' }));
    expect(screen.getByLabelText('Confirm new password')).toHaveAccessibleDescription('The two passwords are not the same.');
  });

  it('updates the password and sends the token from the address', async () => {
    const { calls } = mockApi({ ...signedOut, 'POST /api/auth/reset-password': OK });
    renderApp('/reset-password?token=abc123');
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('New password'), 'a brand new password');
    await user.type(screen.getByLabelText('Confirm new password'), 'a brand new password');
    await user.click(screen.getByRole('button', { name: 'Update password' }));
    expect(await screen.findByRole('heading', { name: 'Password updated' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Go to sign in' })).toHaveAttribute('href', '/login');
    expect(calls.find((c) => c.path === '/api/auth/reset-password').body).toEqual({ token: 'abc123', password: 'a brand new password' });
  });

  it('shows an invalid-or-expired token as a banner with a way to request a new one', async () => {
    mockApi({
      ...signedOut,
      'POST /api/auth/reset-password': { status: 400, body: { detail: 'This password reset link is invalid or has expired. Request a new one.', code: 'invalid_reset_token', request_id: 'req-1' } },
    });
    renderApp('/reset-password?token=expired');
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('New password'), 'a brand new password');
    await user.type(screen.getByLabelText('Confirm new password'), 'a brand new password');
    await user.click(screen.getByRole('button', { name: 'Update password' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('This password reset link is invalid or has expired.');
    expect(within(alert).getByRole('link', { name: 'Request a new link' })).toHaveAttribute('href', '/forgot-password');
    expect(screen.queryByRole('heading', { name: 'Password updated' })).not.toBeInTheDocument();
  });

  it('shows the server-side password rule on the field when the server rejects it', async () => {
    mockApi({
      ...signedOut,
      'POST /api/auth/reset-password': { status: 422, body: { detail: [{ loc: ['body', 'password'], msg: 'password must have 10 to 128 characters' }], code: 'validation_error', request_id: 'req-2' } },
    });
    renderApp('/reset-password?token=abc123');
    const user = userEvent.setup();
    // 10 characters exactly passes the client check but this server response still exercises the field-error path
    await user.type(screen.getByLabelText('New password'), '1234567890');
    await user.type(screen.getByLabelText('Confirm new password'), '1234567890');
    await user.click(screen.getByRole('button', { name: 'Update password' }));
    await screen.findByLabelText('New password');
    expect(screen.getByText('password must have 10 to 128 characters')).toBeInTheDocument();
  });

  it('sends someone who is already signed in straight to the dashboard', async () => {
    mockApi({ ...signedOut, 'GET /api/auth/me': { body: USER } });
    renderApp('/reset-password?token=abc123');
    expect(await screen.findByRole('heading', { level: 1, name: 'Dashboard' })).toBeInTheDocument();
  });

  it('sets the tab title', async () => {
    mockApi(signedOut);
    renderApp('/reset-password?token=abc123');
    await screen.findByRole('heading', { level: 1, name: 'Choose a new password' });
    expect(document.title).toBe('Choose a new password | RAVEN');
  });
});
