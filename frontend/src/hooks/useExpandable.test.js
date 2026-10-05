import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useExpandable } from './useExpandable';

describe('useExpandable', () => {
  it('shows only the first items until opened', () => {
    const { result } = renderHook(() => useExpandable([1, 2, 3, 4, 5], 2));
    expect(result.current.shown).toEqual([1, 2]);
    expect(result.current.hidden).toBe(3);
    expect(result.current.open).toBe(false);
    act(() => result.current.toggle());
    expect(result.current.shown).toEqual([1, 2, 3, 4, 5]);
    expect(result.current.open).toBe(true);
    act(() => result.current.toggle());
    expect(result.current.shown).toEqual([1, 2]);
  });

  it('has nothing hidden when there are not more than the initial count', () => {
    const { result } = renderHook(() => useExpandable([1, 2], 3));
    expect(result.current.shown).toEqual([1, 2]);
    expect(result.current.hidden).toBe(0);
  });
});
