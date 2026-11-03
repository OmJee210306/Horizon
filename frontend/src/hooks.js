import { useEffect, useRef, useState } from 'react';
import { useApp } from './context';
import { errorMessage } from './api';

const cache = new Map();

/** Stale-while-revalidate data hook. `key` must change whenever the request changes. */
export function useApi(key, fn) {
  const { refreshKey, setUpdatedAt } = useApp();
  const [state, setState] = useState(() => ({ data: cache.get(key) ?? null, loading: !cache.has(key), error: '' }));
  const [tick, setTick] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    let live = true;
    setState((s) => ({ data: cache.get(key) ?? s.data, loading: true, error: '' }));
    fnRef.current()
      .then((data) => {
        cache.set(key, data);
        if (live) { setState({ data, loading: false, error: '' }); setUpdatedAt(new Date()); }
      })
      .catch((e) => live && setState((s) => ({ data: s.data, loading: false, error: errorMessage(e) })));
    return () => { live = false; };
  }, [key, refreshKey, tick, setUpdatedAt]);

  return { ...state, reload: () => setTick((t) => t + 1) };
}

export function useDebounce(value, ms = 350) {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t); }, [value, ms]);
  return v;
}

export function useTitle(t) {
  useEffect(() => { document.title = `${t} · HORIZON`; }, [t]);
}
