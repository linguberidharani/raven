import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { cleanup, configure } from '@testing-library/react';

// findBy and waitFor wait up to 10 s instead of 1 s.
configure({ asyncUtilTimeout: 10000 });

// jsdom has no ResizeObserver; the charts of Recharts need one.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  window.sessionStorage.clear();
});
