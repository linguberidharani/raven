import { describe, expect, it } from 'vitest';
import { basisInfo, initials, plural, severityInfo, statusInfo } from './mapping';

describe('severityInfo', () => {
  it('names the severities the API sends', () => {
    expect(severityInfo('HIGH')).toEqual({ key: 'high', label: 'High' });
    expect(severityInfo('medium')).toEqual({ key: 'medium', label: 'Medium' });
    expect(severityInfo('LOW').label).toBe('Low');
    expect(severityInfo('INFO').key).toBe('info');
    expect(severityInfo('CRITICAL').key).toBe('critical');
  });
  it('says None before an analysis and for anything unknown', () => {
    for (const value of [null, undefined, '', 'SEVERE', 5]) expect(severityInfo(value)).toEqual({ key: 'none', label: 'None' });
  });
});

describe('statusInfo', () => {
  it('maps investigation, evidence and run statuses', () => {
    expect(statusInfo('open')).toEqual({ label: 'Open', tone: 'accent' });
    expect(statusInfo('ready').tone).toBe('success');
    expect(statusInfo('failed').tone).toBe('danger');
    expect(statusInfo('running').label).toBe('Running');
    expect(statusInfo('completed').label).toBe('Completed');
  });
  it('is honest about a missing or unknown status', () => {
    expect(statusInfo(null)).toEqual({ label: 'Not started', tone: 'neutral' });
    expect(statusInfo('paused')).toEqual({ label: 'paused', tone: 'neutral' });
  });
});

describe('basisInfo', () => {
  it('labels observed and derived content', () => {
    expect(basisInfo('observed')).toEqual({ key: 'observed', label: 'Observed evidence' });
    expect(basisInfo('derived').label).toBe('Derived / interpreted');
    expect(basisInfo('guess')).toBeNull();
    expect(basisInfo(undefined)).toBeNull();
  });
});

describe('initials and plural', () => {
  it('makes initials', () => {
    expect(initials('Ada Lovelace')).toBe('AL');
    expect(initials('  grace   brewster   hopper ')).toBe('GH');
    expect(initials('Dharani')).toBe('DH');
    expect(initials('')).toBe('?');
    expect(initials(null)).toBe('?');
  });
  it('counts', () => {
    expect(plural(1, 'event')).toBe('1 event');
    expect(plural(0, 'event')).toBe('0 events');
    expect(plural(2, 'process', 'processes')).toBe('2 processes');
  });
});
