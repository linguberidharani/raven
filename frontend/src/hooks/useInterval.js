import { useEffect, useRef } from 'react';

/** Calls `callback` every `delay` milliseconds; a `null` delay switches it off. The newest callback is always used. */
export function useInterval(callback, delay) {
  const saved = useRef(callback);
  useEffect(() => {
    saved.current = callback;
  });
  useEffect(() => {
    if (delay === null) return undefined;
    const timer = setInterval(() => saved.current(), delay);
    return () => clearInterval(timer);
  }, [delay]);
}
