import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Moon, RefreshCw } from 'lucide-react';
import { useApp } from '../context';
import { NAV } from '../nav';

export default function CommandPalette() {
  const { palette, setPalette, toggleTheme, refresh } = useApp();
  const nav = useNavigate();
  const [q, setQ] = useState('');
  const [i, setI] = useState(0);
  const ref = useRef();

  const items = useMemo(() => [
    ...NAV.map((n) => ({ label: `Go to ${n.label}`, icon: n.icon, hint: 'Navigate', run: () => nav(n.to) })),
    { label: 'Toggle light / dark theme', icon: Moon, hint: 'Action', run: toggleTheme },
    { label: 'Refresh all data', icon: RefreshCw, hint: 'Action', run: refresh }
  ].filter((x) => x.label.toLowerCase().includes(q.toLowerCase())), [q, nav, toggleTheme, refresh]);

  useEffect(() => {
    const h = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPalette((p) => !p); }
      if (e.key === 'Escape') setPalette(false);
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [setPalette]);
  useEffect(() => { if (palette) { setQ(''); setI(0); setTimeout(() => ref.current?.focus(), 30); } }, [palette]);
  useEffect(() => setI(0), [q]);
  if (!palette) return null;

  const go = (it) => { setPalette(false); it?.run(); };
  const onKey = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setI((x) => Math.min(x + 1, items.length - 1)); }
    if (e.key === 'ArrowUp') { e.preventDefault(); setI((x) => Math.max(x - 1, 0)); }
    if (e.key === 'Enter') go(items[i]);
  };
  return (
    <>
      <div className="overlay" onClick={() => setPalette(false)} />
      <div className="palette" role="dialog" aria-label="Command palette">
        <input ref={ref} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onKey} placeholder="Search pages and actions…" />
        <ul>
          {items.map((it, idx) => <li key={it.label} className={idx === i ? 'on' : ''} onMouseEnter={() => setI(idx)} onClick={() => go(it)}><it.icon size={16} />{it.label}<small>{it.hint}</small></li>)}
          {!items.length && <li><Search size={16} /> No results</li>}
        </ul>
      </div>
    </>
  );
}
