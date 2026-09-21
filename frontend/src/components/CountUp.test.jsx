import { act, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CountUp } from './CountUp';

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
  delete window.matchMedia;
});

describe('CountUp', () => {
  it('shows the value at once in tests', () => {
    render(<CountUp value={2816} />);
    expect(screen.getByText('2,816')).toBeInTheDocument();
  });

  it('shows text that is not a number as it is', () => {
    render(<CountUp value="n/a" />);
    expect(screen.getByText('n/a')).toBeInTheDocument();
  });

  it('shows the value at once when the reader prefers reduced motion', () => {
    vi.stubEnv('MODE', 'production');
    window.matchMedia = (query) => ({ matches: query.includes('reduce'), media: query, addEventListener() {}, removeEventListener() {} });
    render(<CountUp value={104} />);
    expect(screen.getByText('104')).toBeInTheDocument();
  });

  it('counts up to the value when motion is allowed', async () => {
    vi.stubEnv('MODE', 'production');
    vi.useFakeTimers({ toFake: ['requestAnimationFrame', 'cancelAnimationFrame', 'performance'] });
    render(<CountUp value={1000} />);
    expect(screen.getByText('0')).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(screen.getByText('1,000')).toBeInTheDocument();
  });
});
