import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import { DASHBOARD, INVESTIGATION, USER } from '../test/fixtures';
import { caseRoutes } from '../test/routes';
import { mockApi, notAuthenticated } from '../test/mockApi';
import { renderApp } from '../test/render';

const signedIn = { 'GET /api/auth/me': { body: USER }, 'GET /api/dashboard': { body: DASHBOARD }, 'POST /api/auth/logout': { status: 204 } };

describe('the signed-in frame', () => {
  beforeEach(() => {
    mockApi(signedIn);
  });

  it('has a skip link, the landmarks, and the user in the top bar', async () => {
    renderApp('/dashboard');
    await screen.findByRole('heading', { level: 1, name: 'Dashboard' });
    expect(screen.getByRole('link', { name: 'Skip to content' })).toHaveAttribute('href', '#main');
    const banner = screen.getByRole('banner');
    expect(within(banner).getByRole('link', { name: 'Profile of Ada Lovelace' })).toHaveAttribute('href', '/profile');
    expect(within(banner).getByText('AL')).toBeInTheDocument();
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main');
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Breadcrumb' })).toBeInTheDocument();
  });

  it('has exactly one h1 per page', async () => {
    renderApp('/dashboard');
    await screen.findByRole('heading', { level: 1, name: 'Dashboard' });
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
  });

  it('links the top-level pages and marks the current one', async () => {
    renderApp('/dashboard');
    await screen.findByRole('heading', { level: 1, name: 'Dashboard' });
    const main = screen.getByRole('navigation', { name: 'Main' });
    expect(within(main).getByRole('link', { name: 'Dashboard' })).toHaveAttribute('aria-current', 'page');
    expect(within(main).getByRole('link', { name: 'Investigations' })).toHaveAttribute('href', '/investigations');
    const account = screen.getByRole('navigation', { name: 'Account' });
    expect(within(account).getByRole('link', { name: 'Profile' })).toHaveAttribute('href', '/profile');
    expect(within(account).getByRole('link', { name: 'Settings' })).toHaveAttribute('href', '/settings');
    expect(within(account).getByRole('button', { name: 'Sign out' })).toBeInTheDocument();
  });

  it('shows a hint instead of the workflow while no investigation is open', async () => {
    renderApp('/dashboard');
    await screen.findByRole('heading', { level: 1, name: 'Dashboard' });
    expect(screen.getByText('Open an investigation to see its workflow.')).toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: 'Investigation workflow' })).not.toBeInTheDocument();
  });

  it('shows the current case and its workflow, in order, and marks the current step', async () => {
    mockApi(caseRoutes({ ...INVESTIGATION, id: 7, code: 'INV-2026-007' }));
    renderApp('/investigations/7/timeline');
    await screen.findByRole('heading', { level: 1, name: 'Boot activity' });
    const sidebar = screen.getByRole('complementary', { name: 'Sidebar' });
    expect(within(sidebar).getByText('INV-2026-007')).toBeInTheDocument();
    expect(within(sidebar).getByText('Boot activity')).toBeInTheDocument();
    expect(within(sidebar).getByRole('link', { name: 'Change case' })).toHaveAttribute('href', '/investigations');
    const workflow = within(sidebar).getByRole('navigation', { name: 'Investigation workflow' });
    const links = within(workflow).getAllByRole('link');
    expect(links.map((link) => link.textContent)).toEqual([
      'Evidence & Log Upload', 'Detection & Correlation', 'Attack Reconstruction', 'Attack Timeline', 'Impact Analysis', 'RARF', 'Investigation Report',
    ]);
    expect(links.map((link) => link.getAttribute('href'))).toEqual(
      ['evidence', 'detection', 'reconstruction', 'timeline', 'impact', 'rarf', 'report'].map((step) => `/investigations/7/${step}`),
    );
    expect(within(workflow).getByRole('link', { name: 'Attack Timeline' })).toHaveAttribute('aria-current', 'page');
  });

  it('puts the code of the investigation in the breadcrumbs of the top bar', async () => {
    mockApi(caseRoutes({ ...INVESTIGATION, id: 7, code: 'INV-2026-007' }));
    renderApp('/investigations/7/rarf');
    await screen.findByRole('heading', { level: 1, name: 'Boot activity' });
    const crumbs = within(within(screen.getByRole('banner')).getByRole('navigation', { name: 'Breadcrumb' })).getAllByRole('listitem');
    expect(crumbs.map((item) => item.textContent)).toEqual(['Investigations', 'INV-2026-007', 'RARF']);
  });

  it('keeps the last opened case in the sidebar on other pages', async () => {
    mockApi(caseRoutes({ ...INVESTIGATION, id: 7, code: 'INV-2026-007' }));
    renderApp('/investigations/7/timeline');
    await screen.findByRole('heading', { level: 1, name: 'Boot activity' });
    const user = userEvent.setup();
    await user.click(within(screen.getByRole('complementary', { name: 'Sidebar' })).getByRole('link', { name: 'Dashboard' }));
    await screen.findByRole('heading', { level: 1, name: 'Dashboard' });
    expect(window.localStorage.getItem('raven.currentInvestigation')).toBe('7');
    expect(await within(screen.getByRole('complementary', { name: 'Sidebar' })).findByText('INV-2026-007')).toBeInTheDocument();
    expect(within(screen.getByRole('complementary', { name: 'Sidebar' })).getByRole('link', { name: 'Attack Timeline' })).toHaveAttribute('href', '/investigations/7/timeline');
  });

  it('forgets a remembered case that no longer exists', async () => {
    window.localStorage.setItem('raven.currentInvestigation', '99');
    mockApi({ ...caseRoutes(), 'GET /api/investigations/99': { status: 404, body: { detail: 'Investigation not found.', code: 'investigation_not_found', request_id: 'r' } } });
    renderApp('/dashboard');
    await screen.findByRole('heading', { level: 1, name: 'Dashboard' });
    await waitFor(() => expect(screen.getByText('Open an investigation to see its workflow.')).toBeInTheDocument());
    expect(window.localStorage.getItem('raven.currentInvestigation')).toBeNull();
  });

  it('every link of the sidebar leads to a page that exists', async () => {
    mockApi(caseRoutes({ ...INVESTIGATION, id: 7, code: 'INV-2026-007' }));
    renderApp('/investigations/7/evidence');
    await screen.findByRole('heading', { level: 1, name: 'Boot activity' });
    const user = userEvent.setup();
    const targets = ['Detection & Correlation', 'Attack Reconstruction', 'Attack Timeline', 'Impact Analysis', 'RARF', 'Investigation Report', 'Evidence & Log Upload', 'Investigations', 'Settings', 'Profile', 'Dashboard'];
    for (const name of targets) {
      await user.click(within(screen.getByRole('complementary', { name: 'Sidebar' })).getByRole('link', { name }));
      await waitFor(() => expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1));
      expect(screen.queryByRole('heading', { name: 'Page not found' })).not.toBeInTheDocument();
    }
  });

  it('moves the focus to the page after a navigation', async () => {
    renderApp('/dashboard');
    await screen.findByRole('heading', { level: 1, name: 'Dashboard' });
    await userEvent.setup().click(screen.getByRole('link', { name: 'Settings' }));
    await screen.findByRole('heading', { level: 1, name: 'Settings' });
    expect(screen.getByRole('main')).toHaveFocus();
  });

  it('opens and closes the menu drawer with the button, the backdrop and Escape', async () => {
    renderApp('/dashboard');
    await screen.findByRole('heading', { level: 1, name: 'Dashboard' });
    const user = userEvent.setup();
    const sidebar = screen.getByRole('complementary', { name: 'Sidebar' });
    const opener = screen.getByRole('button', { name: 'Open menu' });
    expect(opener).toHaveAttribute('aria-expanded', 'false');
    expect(opener).toHaveAttribute('aria-controls', 'sidebar');
    expect(sidebar).not.toHaveClass('open');
    await user.click(opener);
    expect(sidebar).toHaveClass('open');
    expect(opener).toHaveAttribute('aria-expanded', 'true');
    await user.keyboard('{Escape}');
    expect(sidebar).not.toHaveClass('open');
    await user.click(opener);
    await user.click(screen.getByRole('button', { name: 'Close menu' }));
    expect(sidebar).not.toHaveClass('open');
    await user.click(opener);
    fireEvent.click(document.querySelector('.sidebar-backdrop'));
    expect(sidebar).not.toHaveClass('open');
  });

  it('closes the drawer when a page is chosen', async () => {
    renderApp('/dashboard');
    await screen.findByRole('heading', { level: 1, name: 'Dashboard' });
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Open menu' }));
    await user.click(within(screen.getByRole('complementary', { name: 'Sidebar' })).getByRole('link', { name: 'Settings' }));
    expect(screen.getByRole('complementary', { name: 'Sidebar' })).not.toHaveClass('open');
  });

  it('signs out from the sidebar and returns to sign in', async () => {
    renderApp('/dashboard');
    await screen.findByRole('heading', { level: 1, name: 'Dashboard' });
    await userEvent.setup().click(screen.getByRole('button', { name: 'Sign out' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Analyst sign in' })).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/login$/);
  });

  it('returns to sign in when the session ends while a page loads', async () => {
    mockApi({ 'GET /api/auth/me': { body: USER }, 'GET /api/dashboard': notAuthenticated });
    renderApp('/dashboard');
    expect(await screen.findByRole('heading', { level: 1, name: 'Analyst sign in' })).toBeInTheDocument();
  });
});
