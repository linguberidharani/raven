import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { INVESTIGATION } from './test/fixtures';
import { mockApi, notAuthenticated } from './test/mockApi';
import { caseRoutes } from './test/routes';
import { renderApp } from './test/render';
import { expectNoViolations } from './test/a11y';

vi.mock('./components/ActivityChart', async () => {
  const React = await import('react');
  return { default: () => React.createElement('div', { role: 'img', 'aria-label': 'Events over time in buckets of 10 seconds, by event type. The data is also available as a table.' }, 'chart') };
});

const TIMEOUT = 60000;

async function check(path, ready, routes = {}) {
  mockApi(caseRoutes(INVESTIGATION, routes));
  renderApp(path);
  await ready();
  await expectNoViolations();
}

describe('accessibility (axe) of the signed-out pages', () => {
  it('sign in', { timeout: TIMEOUT }, async () => {
    mockApi({ 'GET /api/auth/me': notAuthenticated });
    renderApp('/login');
    await screen.findByRole('heading', { name: 'Analyst sign in' });
    await expectNoViolations();
  });

  it('sign in with errors shown', { timeout: TIMEOUT }, async () => {
    mockApi({ 'GET /api/auth/me': notAuthenticated });
    renderApp('/login');
    await userEvent.setup().click(await screen.findByRole('button', { name: 'Sign in' }));
    expect(screen.getByLabelText('Email')).toHaveAttribute('aria-invalid', 'true');
    await expectNoViolations();
  });

  it('registration', { timeout: TIMEOUT }, async () => {
    mockApi({ 'GET /api/auth/me': notAuthenticated });
    renderApp('/register');
    await screen.findByRole('heading', { name: 'Create an analyst account' });
    await expectNoViolations();
  });

  it('forgot password', { timeout: TIMEOUT }, async () => {
    mockApi({ 'GET /api/auth/me': notAuthenticated });
    renderApp('/forgot-password');
    await screen.findByRole('heading', { name: 'Reset your password' });
    await expectNoViolations();
  });

  it('reset password', { timeout: TIMEOUT }, async () => {
    mockApi({ 'GET /api/auth/me': notAuthenticated });
    renderApp('/reset-password?token=abc123');
    await screen.findByRole('heading', { name: 'Choose a new password' });
    await expectNoViolations();
  });

  it('intro', { timeout: TIMEOUT }, async () => {
    mockApi({ 'GET /api/auth/me': notAuthenticated });
    renderApp('/');
    await screen.findByRole('heading', { level: 1, name: 'RAVEN' });
    await expectNoViolations();
  });
});

describe('accessibility (axe) of the signed-in pages', () => {
  it('dashboard', { timeout: TIMEOUT }, () => check('/dashboard', () => screen.findByText('Latest attack session')));
  it('investigations', { timeout: TIMEOUT }, () => check('/investigations', () => screen.findByRole('table', { name: 'Investigations' })));
  it('profile', { timeout: TIMEOUT }, () => check('/profile', () => screen.findByRole('heading', { level: 1, name: 'Profile' })));
  it('page not found', { timeout: TIMEOUT }, () => check('/nowhere', () => screen.findByRole('heading', { level: 1, name: 'Page not found' })));
});

describe('accessibility (axe) of the seven steps of an investigation', () => {
  it('evidence', { timeout: TIMEOUT }, () => check('/investigations/1/evidence', () => screen.findByRole('table', { name: 'Evidence items of this investigation' })));
  it('detection', { timeout: TIMEOUT }, () => check('/investigations/1/detection', () => screen.findByText('detection groups from 2 of 3 rules')));
  it('reconstruction', { timeout: TIMEOUT }, () => check('/investigations/1/reconstruction', () => screen.findByRole('heading', { name: 'Process tree' })));
  it('timeline', { timeout: TIMEOUT }, () => check('/investigations/1/timeline', () => screen.findByText('3 events in the timeline.')));
  it('impact', { timeout: TIMEOUT }, () => check('/investigations/1/impact', () => screen.findByRole('heading', { name: 'Observed impact' })));
  it('rarf', { timeout: TIMEOUT }, () => check('/investigations/1/rarf', () => screen.findByRole('heading', { name: 'Structured record' })));
  it('report', { timeout: TIMEOUT }, () => check('/investigations/1/report', () => screen.findByRole('article', { name: 'Investigation report' })));
});

describe('accessibility (axe) of overlays and open states', () => {
  it('the event details panel', { timeout: TIMEOUT }, async () => {
    mockApi(caseRoutes(INVESTIGATION));
    renderApp('/investigations/1/detection');
    const user = userEvent.setup();
    await user.click((await screen.findAllByRole('button', { name: 'View details' }))[0]);
    await user.click((await screen.findAllByRole('button', { name: 'Open event 1:1' }))[0]);
    const dialog = await screen.findByRole('dialog');
    await screen.findByText('Normalized record');
    await expectNoViolations(dialog);
  });

  it('the new investigation form', { timeout: TIMEOUT }, async () => {
    mockApi(caseRoutes(INVESTIGATION));
    renderApp('/investigations');
    await userEvent.setup().click(await screen.findByRole('button', { name: 'New investigation' }));
    await screen.findByRole('heading', { name: 'New investigation' });
    await expectNoViolations();
  });

  it('the navigation drawer opened', { timeout: TIMEOUT }, async () => {
    mockApi(caseRoutes(INVESTIGATION));
    renderApp('/dashboard');
    await screen.findByText('Latest attack session');
    await userEvent.setup().click(screen.getByRole('button', { name: 'Open menu' }));
    await waitFor(() => expect(screen.getByRole('complementary', { name: 'Sidebar' })).toHaveClass('open'));
    await expectNoViolations();
  });
});
