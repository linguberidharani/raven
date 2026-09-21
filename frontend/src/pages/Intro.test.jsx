import { act, fireEvent, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mockApi, notAuthenticated } from '../test/mockApi';
import { renderApp } from '../test/render';
import { DOTS, INTRO_MS } from './Intro';

function setReducedMotion(reduced) {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    writable: true,
    value: (query) => ({ matches: reduced && query.includes('reduce'), media: query, addEventListener() {}, removeEventListener() {} }),
  });
}

afterEach(() => {
  vi.useRealTimers();
  delete window.matchMedia;
});

describe('Intro', () => {
  beforeEach(() => {
    mockApi({ 'GET /api/auth/me': notAuthenticated });
  });

  it('names the product, has no mention of encryption, and lights five stages', () => {
    renderApp('/');
    expect(screen.getByRole('heading', { level: 1, name: 'RAVEN' })).toBeInTheDocument();
    expect(screen.getByText('Ransomware Attack Visualization and Event Navigator')).toBeInTheDocument();
    const picture = screen.getByRole('img');
    expect(picture).toHaveAccessibleName(/Telemetry, Detection, Reconstruction, Impact, Report/);
    for (const stage of ['Telemetry', 'Detection', 'Reconstruction', 'Impact', 'Report']) {
      expect(picture.textContent).toContain(stage);
    }
    expect(document.body.textContent.toLowerCase()).not.toMatch(/encrypt|decrypt/);
  });

  it('draws the same scatter every time, ending on the axis', () => {
    expect(DOTS).toHaveLength(44);
    expect(DOTS[0].x).toBe(60);
    expect(DOTS[43].x).toBe(940);
    expect(Math.max(...DOTS.map((d) => d.delay))).toBeLessThan(0.7);
  });

  it('continues to sign in by itself after about 4.8 seconds', async () => {
    vi.useFakeTimers();
    renderApp('/');
    await act(async () => { vi.advanceTimersByTime(INTRO_MS - 100); });
    expect(screen.queryByRole('heading', { name: 'Analyst sign in' })).not.toBeInTheDocument();
    await act(async () => { vi.advanceTimersByTime(200); });
    expect(screen.getByRole('heading', { name: 'Analyst sign in' })).toBeInTheDocument();
    expect(INTRO_MS).toBe(4800);
  });

  it('can be skipped', async () => {
    renderApp('/');
    fireEvent.click(screen.getByRole('button', { name: /Skip the introduction/ }));
    expect(await screen.findByRole('heading', { name: 'Analyst sign in' })).toBeInTheDocument();
  });

  it('with reduced motion shows the finished picture, waits for the reader and offers to continue', async () => {
    setReducedMotion(true);
    vi.useFakeTimers();
    renderApp('/');
    await act(async () => { vi.advanceTimersByTime(20_000); });
    expect(screen.getByRole('heading', { level: 1, name: 'RAVEN' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Skip/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Continue to sign in' }));
    expect(screen.getByRole('heading', { name: 'Analyst sign in' })).toBeInTheDocument();
  });
});
