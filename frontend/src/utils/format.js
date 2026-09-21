// Display helpers. Timestamps from the API are UTC (ISO-8601 with a trailing Z) and are shown as UTC.

const EMPTY = '\u2014';

export function formatNumber(value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return EMPTY;
  return new Intl.NumberFormat('en-US').format(value);
}

/** 2026-09-13T08:39:49.545Z -> "2026-09-13 08:39:49 UTC" (with milliseconds when asked). */
export function formatTimestamp(iso, { millis = false } = {}) {
  if (typeof iso !== 'string') return EMPTY;
  const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?Z$/.exec(iso);
  if (!match) return EMPTY;
  const [, date, time, fraction] = match;
  const ms = millis ? `.${(fraction ?? '').padEnd(3, '0').slice(0, 3)}` : '';
  return `${date} ${time}${ms} UTC`;
}

/** 3215360 -> "3.07 MB" (1024-based units, like the file explorer). */
export function formatBytes(bytes) {
  if (typeof bytes !== 'number' || !Number.isFinite(bytes) || bytes < 0) return EMPTY;
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value < 10 ? 2 : 1)} ${units[unit]}`;
}

/** 199943 -> "3 min 19.9 s". */
export function formatDuration(ms) {
  if (typeof ms !== 'number' || !Number.isFinite(ms) || ms < 0) return EMPTY;
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const totalMinutes = Math.floor(seconds / 60);
  const rest = (seconds - totalMinutes * 60).toFixed(1);
  if (totalMinutes < 60) return `${totalMinutes} min ${rest} s`;
  const hours = Math.floor(totalMinutes / 60);
  return `${hours} h ${totalMinutes - hours * 60} min`;
}

export function shortHash(value, length = 12) {
  if (typeof value !== 'string' || value.length === 0) return EMPTY;
  return value.length <= length ? value : `${value.slice(0, length)}\u2026`;
}

/** 60 -> "60 s", 120 -> "2 min", 90 -> "1 min 30 s". For the time window of a rule. */
export function formatWindow(seconds) {
  if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds < 0) return EMPTY;
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds - minutes * 60;
  return rest === 0 ? `${minutes} min` : `${minutes} min ${rest} s`;
}

/** Time of day of a UTC timestamp, with milliseconds: 08:39:49.545. */
export function formatClock(iso) {
  if (typeof iso !== 'string') return EMPTY;
  const match = /T(\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?Z$/.exec(iso);
  if (!match) return EMPTY;
  return `${match[1]}.${(match[2] ?? '').padEnd(3, '0').slice(0, 3)}`;
}
