import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import ActivityChart from './ActivityChart';

const BUCKETS = [
  { start: '2026-09-13T08:39:40.000Z', file_create: 3, network_connection: 0, process_creation: 1, total: 4 },
  { start: '2026-09-13T08:39:50.000Z', file_create: 10, network_connection: 2, process_creation: 0, total: 12 },
];

describe('ActivityChart', () => {
  // The first import of the chart library can take a while on a slow disk.
  it('describes the chart in words and draws it', { timeout: 120000 }, () => {
    const { container } = render(<ActivityChart buckets={BUCKETS} bucketSeconds={10} />);
    expect(screen.getByRole('img', { name: /Events over time in buckets of 10 seconds, by event type/ })).toBeInTheDocument();
    expect(container.querySelector('.recharts-responsive-container')).not.toBeNull();
  });

  it('accepts an empty list of buckets', () => {
    render(<ActivityChart buckets={[]} bucketSeconds={10} />);
    expect(screen.getByRole('img')).toBeInTheDocument();
  });
});
