import { useEffect, useRef, useState } from 'react';

interface FetchState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

const FETCH_TIMEOUT_MS = 45_000;

export function useFetch<T>(url: string, deps: unknown[] = []): FetchState<T> {
  const [state, setState] = useState<FetchState<T>>({ data: null, loading: true, error: null });
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setState({ data: null, loading: true, error: null });

    const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);

    fetch(url, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error(`Server returned ${res.status}`);
        return res.json() as Promise<T>;
      })
      .then((data) => {
        clearTimeout(timer);
        if (!controller.signal.aborted) setState({ data, loading: false, error: null });
      })
      .catch((err: Error) => {
        clearTimeout(timer);
        if (!controller.signal.aborted) {
          const msg = err.name === 'AbortError'
            ? 'Server is warming up — please refresh in a moment.'
            : err.message;
          setState({ data: null, loading: false, error: msg });
        }
      });

    return () => { clearTimeout(timer); controller.abort(); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, ...deps]);

  return state;
}
