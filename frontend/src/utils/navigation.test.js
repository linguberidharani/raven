import { describe, expect, it } from 'vitest';
import { WORKFLOW, breadcrumbsFor, investigationPath, matchInvestigation, stepIndex } from './navigation';

describe('workflow', () => {
  it('has the seven steps of the investigation in order', () => {
    expect(WORKFLOW.map((s) => s.key)).toEqual(['evidence', 'detection', 'reconstruction', 'timeline', 'impact', 'rarf', 'report']);
    expect(WORKFLOW.map((s) => s.label)).toEqual([
      'Evidence & Log Upload', 'Detection & Correlation', 'Attack Reconstruction', 'Attack Timeline', 'Impact Analysis', 'RARF', 'Investigation Report',
    ]);
  });
  it('builds paths and finds positions', () => {
    expect(investigationPath(3)).toBe('/investigations/3');
    expect(investigationPath(3, 'timeline')).toBe('/investigations/3/timeline');
    expect(stepIndex('impact')).toBe(4);
    expect(stepIndex('nothing')).toBe(-1);
  });
});

describe('matchInvestigation', () => {
  it('finds the investigation and the step', () => {
    expect(matchInvestigation('/investigations/12')).toEqual({ id: 12, step: null });
    expect(matchInvestigation('/investigations/12/report')).toEqual({ id: 12, step: 'report' });
    expect(matchInvestigation('/investigations/12/report/')).toEqual({ id: 12, step: 'report' });
  });
  it('ignores everything else', () => {
    for (const path of ['/investigations', '/investigations/x', '/investigations/1/unknown', '/investigations/1/report/extra', '/dashboard']) {
      expect(matchInvestigation(path)).toBeNull();
    }
  });
});

describe('breadcrumbsFor', () => {
  it('has one item for the top-level pages', () => {
    expect(breadcrumbsFor('/dashboard')).toEqual([{ label: 'Dashboard' }]);
    expect(breadcrumbsFor('/investigations')).toEqual([{ label: 'Investigations' }]);
    expect(breadcrumbsFor('/profile')).toEqual([{ label: 'Profile' }]);
    expect(breadcrumbsFor('/settings')).toEqual([{ label: 'Settings' }]);
  });
  it('links the parents of an investigation page', () => {
    expect(breadcrumbsFor('/investigations/4/timeline')).toEqual([
      { label: 'Investigations', to: '/investigations' },
      { label: 'Investigation 4', to: '/investigations/4' },
      { label: 'Attack Timeline' },
    ]);
    expect(breadcrumbsFor('/investigations/4')).toEqual([{ label: 'Investigations', to: '/investigations' }, { label: 'Investigation 4' }]);
  });
  it('names an unknown path', () => {
    expect(breadcrumbsFor('/nowhere')).toEqual([{ label: 'Not found' }]);
  });
});
