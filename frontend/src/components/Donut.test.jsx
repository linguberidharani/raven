import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Donut } from './Donut';

const segments = (values) => values.map(([label, value], index) => ({ key: label, label, value, color: `var(--c${index})` }));

describe('Donut', () => {
  it('describes the ring in words and draws a segment for each value', () => {
    const { container } = render(<Donut segments={segments([['High', 3], ['Low', 1], ['None', 0]])} centerLabel="cases" />);
    expect(screen.getByRole('img', { name: 'cases: 4 in total. High 3, Low 1.' })).toBeInTheDocument();
    expect(container.querySelectorAll('.donut-segment')).toHaveLength(2);
    expect(container.querySelector('.donut-total').textContent).toBe('4');
  });

  it('gives each segment a share of the ring that matches its value', () => {
    const { container } = render(<Donut segments={segments([['A', 1], ['B', 3]])} centerLabel="things" />);
    const [a, b] = [...container.querySelectorAll('.donut-segment')].map((c) => Number(c.getAttribute('stroke-dasharray').split(' ')[0]));
    expect(b / a).toBeGreaterThan(2.5);
    expect(b / a).toBeLessThan(3.3);
  });

  it('draws no segment and says None when everything is zero', () => {
    const { container } = render(<Donut segments={segments([['A', 0], ['B', 0]])} centerLabel="cases" />);
    expect(container.querySelectorAll('.donut-segment')).toHaveLength(0);
    expect(screen.getByRole('img', { name: 'cases: 0 in total. None.' })).toBeInTheDocument();
  });

  it('does not leave a gap when there is a single segment', () => {
    const { container } = render(<Donut segments={segments([['A', 5]])} centerLabel="cases" />);
    const dash = container.querySelector('.donut-segment').getAttribute('stroke-dasharray').split(' ').map(Number);
    expect(dash[0] + dash[1]).toBeCloseTo(2 * Math.PI * 52, 1);
    expect(dash[1]).toBeLessThan(1);
  });
});
