import { useEffect, useState } from 'react';
import { useReducedMotion } from '../hooks/useReducedMotion';
import { formatNumber } from '../utils/format';

const DURATION_MS = 700;

/** A number that counts up to its value when it appears. With reduced motion, and in tests, it shows the value at once. */
export function CountUp({ value }) {
  const reduced = useReducedMotion();
  const instant = reduced || import.meta.env.MODE === 'test' || typeof value !== 'number';
  const [shown, setShown] = useState(0);

  useEffect(() => {
    if (instant) return undefined;
    let frame = 0;
    const start = performance.now();
    const tick = (now) => {
      const progress = Math.min(1, (now - start) / DURATION_MS);
      setShown(Math.round(value * (1 - (1 - progress) ** 3)));
      if (progress < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value, instant]);

  return instant ? (typeof value === 'number' ? formatNumber(value) : value) : formatNumber(shown);
}
