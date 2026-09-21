import { useCallback, useEffect, useState } from 'react';

/**
 * Runs fetcher(signal) when the component mounts and whenever `deps` change.
 * Returns { data, loading, error, reload }. The previous data stays while a reload is running.
 * An answer that arrives after the component left or the inputs changed is ignored.
 */
export function useApi(fetcher, deps = []) {
  const [state, setState] = useState({ data: null, loading: true, error: null });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState((previous) => ({ ...previous, loading: true, error: null }));
    Promise.resolve()
      .then(() => fetcher(controller.signal))
      .then((data) => {
        if (!controller.signal.aborted) setState({ data, loading: false, error: null });
      })
      .catch((error) => {
        if (controller.signal.aborted || error?.name === 'AbortError') return;
        setState({ data: null, loading: false, error });
      });
    return () => controller.abort();
    // The caller lists what the fetcher depends on.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, attempt]);

  const reload = useCallback(() => setAttempt((count) => count + 1), []);
  return { data: state.data, loading: state.loading, error: state.error, reload };
}
