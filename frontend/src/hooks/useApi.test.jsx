import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useApi } from './useApi';

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('useApi', () => {
  it('starts loading and then has the data', async () => {
    const { result } = renderHook(() => useApi(async () => ({ a: 1 }), []));
    expect(result.current).toMatchObject({ data: null, loading: true, error: null });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current).toMatchObject({ data: { a: 1 }, error: null });
  });

  it('has the error when the request fails', async () => {
    const failure = new Error('nope');
    const { result } = renderHook(() => useApi(async () => { throw failure; }, []));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current).toMatchObject({ data: null, error: failure });
  });

  it('gives the fetcher an abort signal that is aborted when the component leaves', async () => {
    const wait = deferred();
    let seen;
    const { unmount } = renderHook(() => useApi((signal) => { seen = signal; return wait.promise; }, []));
    await waitFor(() => expect(seen).toBeDefined());
    expect(seen.aborted).toBe(false);
    unmount();
    expect(seen.aborted).toBe(true);
    wait.resolve('late');
  });

  it('reloads on request and keeps the old data meanwhile', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce('first');
    const second = deferred();
    fetcher.mockReturnValueOnce(second.promise);
    const { result } = renderHook(() => useApi(fetcher, []));
    await waitFor(() => expect(result.current.data).toBe('first'));
    act(() => result.current.reload());
    await waitFor(() => expect(result.current.loading).toBe(true));
    expect(result.current.data).toBe('first');
    await act(async () => second.resolve('second'));
    await waitFor(() => expect(result.current.data).toBe('second'));
    expect(result.current.loading).toBe(false);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('clears an old error when it reloads', async () => {
    const fetcher = vi.fn().mockRejectedValueOnce(new Error('first failure')).mockResolvedValueOnce('fine');
    const { result } = renderHook(() => useApi(fetcher, []));
    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
    act(() => result.current.reload());
    await waitFor(() => expect(result.current.data).toBe('fine'));
    expect(result.current.error).toBeNull();
  });

  it('asks again when the inputs change and ignores the answer of the old inputs', async () => {
    const slow = deferred();
    const fetcher = vi.fn((signal, id) => (id === 1 ? slow.promise : Promise.resolve(`answer ${id}`)));
    const { result, rerender } = renderHook(({ id }) => useApi((signal) => fetcher(signal, id), [id]), { initialProps: { id: 1 } });
    rerender({ id: 2 });
    await waitFor(() => expect(result.current.data).toBe('answer 2'));
    await act(async () => slow.resolve('answer 1'));
    expect(result.current.data).toBe('answer 2');
  });

  it('ignores an abort error', async () => {
    const { result, unmount } = renderHook(() => useApi(async () => { throw new DOMException('Aborted', 'AbortError'); }, []));
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(result.current.error).toBeNull();
    unmount();
  });
});
