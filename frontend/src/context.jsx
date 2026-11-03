import { createContext, useContext, useEffect, useMemo, useState, useCallback } from 'react';
import { makeFmt } from './format';

const Ctx = createContext(null);
export const useApp = () => useContext(Ctx);
export const useFmt = () => useContext(Ctx).fmt;

const read = (k, d) => { try { return localStorage.getItem(k) || d; } catch { return d; } };
const write = (k, v) => { try { localStorage.setItem(k, v); } catch { /* ignore */ } };

export function AppProvider({ children }) {
  const [theme, setTheme] = useState(() => read('horizon.theme', 'dark'));
  const [currency, setCurrency] = useState(() => read('horizon.currency', 'USD'));
  const [refreshKey, setRefreshKey] = useState(0);
  const [updatedAt, setUpdatedAt] = useState(null);
  const [palette, setPalette] = useState(false);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    write('horizon.theme', theme);
  }, [theme]);
  useEffect(() => write('horizon.currency', currency), [currency]);

  const fmt = useMemo(() => makeFmt(currency), [currency]);
  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);
  const toggleTheme = useCallback(() => setTheme((t) => (t === 'dark' ? 'light' : 'dark')), []);

  const value = { theme, toggleTheme, currency, setCurrency, fmt, refreshKey, refresh, updatedAt, setUpdatedAt, palette, setPalette };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
