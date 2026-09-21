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

import { ANALYSIS_STAGES, analysisStageLabel, eventTypeLabel, isRunActive, readySteps, sourceTypeLabel, stageStatusInfo, stepStates } from './mapping';

const CASE = { analysis_status: 'completed', counts: { evidence: 1, detections: 87, sessions: 1, timeline_events: 597 } };

describe('stepStates and readySteps', () => {
  it('marks every step ready for an analysed investigation with a session', () => {
    expect(stepStates(CASE)).toEqual({ evidence: true, detection: true, reconstruction: true, timeline: true, impact: true, rarf: true, report: true });
    expect(readySteps(CASE)).toBe(7);
  });
  it('has only the evidence step before an analysis', () => {
    const fresh = { analysis_status: null, counts: { evidence: 1, detections: 0, sessions: 0, timeline_events: 0 } };
    expect(readySteps(fresh)).toBe(1);
    expect(stepStates(fresh).detection).toBe(false);
  });
  it('has no step for an empty investigation, and copes with a missing object', () => {
    expect(readySteps({ analysis_status: null, counts: { evidence: 0 } })).toBe(0);
    expect(readySteps(null)).toBe(0);
    expect(readySteps(undefined)).toBe(0);
  });
  it('counts detection as ready when an analysis found nothing, but not the session steps', () => {
    const empty = { analysis_status: 'completed', counts: { evidence: 1, detections: 0, sessions: 0, timeline_events: 0 } };
    expect(stepStates(empty)).toMatchObject({ evidence: true, detection: true, reconstruction: false, timeline: false, report: false });
    expect(readySteps(empty)).toBe(2);
  });
  it('does not count a run that is still going', () => {
    expect(stepStates({ analysis_status: 'running', counts: { evidence: 1, sessions: 1, timeline_events: 5 } }).detection).toBe(false);
  });
});

describe('labels for events, sources and analysis stages', () => {
  it('names the event types', () => {
    expect(eventTypeLabel('process_creation')).toBe('Process created');
    expect(eventTypeLabel('file_create')).toBe('File created');
    expect(eventTypeLabel('network_connection')).toBe('Network connection');
    expect(eventTypeLabel('unsupported')).toBe('Not supported by RAVEN');
    expect(eventTypeLabel('other')).toBe('other');
    expect(eventTypeLabel(null)).toBe('Unknown');
  });
  it('names the source types', () => {
    expect(sourceTypeLabel('evtx_upload')).toBe('EVTX upload');
    expect(sourceTypeLabel('vm_collector')).toBe('VM collector');
    expect(sourceTypeLabel('x')).toBe('x');
  });
  it('has the ten stages of the pipeline in order', () => {
    expect(ANALYSIS_STAGES.map((s) => s.name)).toEqual(['collect', 'normalize', 'deduplicate', 'ingest', 'correlate', 'reconstruct', 'timeline', 'impact', 'rarf', 'report']);
    expect(analysisStageLabel('correlate')).toBe('Detect and correlate');
    expect(analysisStageLabel('new_stage')).toBe('new_stage');
  });
  it('maps stage statuses and finds an active run', () => {
    expect(stageStatusInfo('completed')).toEqual({ label: 'Done', tone: 'success' });
    expect(stageStatusInfo('failed').tone).toBe('danger');
    expect(stageStatusInfo(undefined).label).toBe('Waiting');
    expect(isRunActive({ status: 'queued' })).toBe(true);
    expect(isRunActive({ status: 'running' })).toBe(true);
    expect(isRunActive({ status: 'completed' })).toBe(false);
    expect(isRunActive(null)).toBe(false);
  });
});
