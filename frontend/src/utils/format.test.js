import { describe, expect, it } from 'vitest';
import { formatBytes, formatDuration, formatNumber, formatTimestamp, shortHash } from './format';

describe('formatTimestamp', () => {
  it('shows UTC time from an ISO timestamp', () => {
    expect(formatTimestamp('2026-09-13T08:39:49.545Z')).toBe('2026-09-13 08:39:49 UTC');
  });
  it('can show milliseconds', () => {
    expect(formatTimestamp('2026-09-13T08:39:49.545Z', { millis: true })).toBe('2026-09-13 08:39:49.545 UTC');
    expect(formatTimestamp('2026-09-13T08:39:49.5Z', { millis: true })).toBe('2026-09-13 08:39:49.500 UTC');
    expect(formatTimestamp('2026-09-13T08:39:49Z', { millis: true })).toBe('2026-09-13 08:39:49.000 UTC');
  });
  it('shows a dash for anything else', () => {
    for (const value of [null, undefined, '', 'yesterday', '2026-09-13 08:39:49', 5]) {
      expect(formatTimestamp(value)).toBe('\u2014');
    }
  });
});

describe('formatBytes', () => {
  it('uses 1024-based units', () => {
    expect(formatBytes(0)).toBe('0 B');
    expect(formatBytes(1023)).toBe('1023 B');
    expect(formatBytes(1024)).toBe('1.00 KB');
    expect(formatBytes(3215360)).toBe('3.07 MB');
    expect(formatBytes(200 * 1024 * 1024)).toBe('200.0 MB');
    expect(formatBytes(5 * 1024 ** 3)).toBe('5.00 GB');
  });
  it('rejects values that are not sizes', () => {
    for (const value of [-1, NaN, Infinity, '5', null]) expect(formatBytes(value)).toBe('\u2014');
  });
});

describe('formatDuration', () => {
  it('chooses a readable unit', () => {
    expect(formatDuration(0)).toBe('0 ms');
    expect(formatDuration(999)).toBe('999 ms');
    expect(formatDuration(1500)).toBe('1.5 s');
    expect(formatDuration(199943)).toBe('3 min 19.9 s');
    expect(formatDuration(3_720_000)).toBe('1 h 2 min');
  });
  it('rejects values that are not durations', () => {
    for (const value of [-5, NaN, undefined, '10']) expect(formatDuration(value)).toBe('\u2014');
  });
});

describe('formatNumber and shortHash', () => {
  it('groups thousands', () => {
    expect(formatNumber(2816)).toBe('2,816');
    expect(formatNumber(NaN)).toBe('\u2014');
    expect(formatNumber('5')).toBe('\u2014');
  });
  it('shortens a hash', () => {
    expect(shortHash('845724C83763D2B12B98247C64F67830DEF4BB0B9E3E8923C051B887E70B210B')).toBe('845724C83763\u2026');
    expect(shortHash('abc')).toBe('abc');
    expect(shortHash('')).toBe('\u2014');
    expect(shortHash(null)).toBe('\u2014');
  });
});

import { formatClock, formatWindow } from './format';

describe('formatWindow and formatClock', () => {
  it('writes a rule window', () => {
    expect(formatWindow(60)).toBe('1 min');
    expect(formatWindow(45)).toBe('45 s');
    expect(formatWindow(120)).toBe('2 min');
    expect(formatWindow(90)).toBe('1 min 30 s');
    expect(formatWindow(-1)).toBe('\u2014');
    expect(formatWindow(null)).toBe('\u2014');
  });
  it('writes the time of day with milliseconds', () => {
    expect(formatClock('2026-09-13T08:39:49.545Z')).toBe('08:39:49.545');
    expect(formatClock('2026-09-13T08:39:49Z')).toBe('08:39:49.000');
    expect(formatClock('nope')).toBe('\u2014');
    expect(formatClock(undefined)).toBe('\u2014');
  });
});
