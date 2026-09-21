// Local UI state lives under keys that start with "raven." and can be cleared from the Settings page.

export const STORAGE_PREFIX = 'raven.';

function ownKeys(storage) {
  const keys = [];
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index);
    if (key && key.startsWith(STORAGE_PREFIX)) keys.push(key);
  }
  return keys;
}

export function clearLocalUiState() {
  let removed = 0;
  for (const storage of [window.localStorage, window.sessionStorage]) {
    for (const key of ownKeys(storage)) {
      storage.removeItem(key);
      removed += 1;
    }
  }
  return removed;
}
