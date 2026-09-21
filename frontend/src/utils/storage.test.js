import { describe, expect, it } from 'vitest';
import { clearLocalUiState } from './storage';

describe('clearLocalUiState', () => {
  it('removes only the keys of this app, in both storages', () => {
    window.localStorage.setItem('raven.sidebar', '1');
    window.localStorage.setItem('other.key', 'keep');
    window.sessionStorage.setItem('raven.tab', 'timeline');
    window.sessionStorage.setItem('raven.introSeen', '1');
    expect(clearLocalUiState()).toBe(3);
    expect(window.localStorage.getItem('raven.sidebar')).toBeNull();
    expect(window.sessionStorage.getItem('raven.tab')).toBeNull();
    expect(window.localStorage.getItem('other.key')).toBe('keep');
  });
  it('says 0 when there is nothing to clear', () => {
    expect(clearLocalUiState()).toBe(0);
  });
});
