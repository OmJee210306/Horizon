import { useEffect, useState } from 'react';
import { NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { Menu, Moon, PanelLeftClose, PanelLeftOpen, RefreshCw, Search, Sun } from 'lucide-react';
import { useApp } from './context';
import { useApi } from './hooks';
import { getHealth } from './api';
import { CURRENCIES } from './config';
import { NAV } from './nav';
import { ErrorBoundary } from './components/ui';
import CommandPalette from './components/CommandPalette';
import Overview from './pages/Overview';
import Revenue from './pages/Revenue';
import Churn from './pages/Churn';
import Sources from './pages/Sources';
import Methodology from './pages/Methodology';

export default function App() {
  const { theme, toggleTheme, currency, setCurrency, refresh, setPalette } = useApp();
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('horizon.collapsed') === '1');
  const [spinning, setSpinning] = useState(false);
  const health = useApi('health', getHealth);
  const online = health.data?.status === 'ok' && !health.error;
  const page = NAV.find((n) => (n.end ? pathname === n.to : pathname.startsWith(n.to)))?.label || 'Overview';

  useEffect(() => { const t = setInterval(health.reload, 30000); return () => clearInterval(t); }, []); // eslint-disable-line
  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => { localStorage.setItem('horizon.collapsed', collapsed ? '1' : '0'); }, [collapsed]);
  useEffect(() => { window.scrollTo(0, 0); }, [pathname]);

  const doRefresh = () => { refresh(); health.reload(); setSpinning(true); setTimeout(() => setSpinning(false), 900); };

  return (
    <div className={`app ${collapsed ? 'collapsed' : ''}`}>
      {open && <div className="overlay" style={{ zIndex: 35 }} onClick={() => setOpen(false)} />}
      <aside className={`sidebar ${open ? 'open' : ''}`}>
        <div className="brand">
          <div className="brand-mark"><img src="/favicon.svg" alt="" width="38" height="38" /></div>
          <div><b>HORIZON</b><small>ANALYTICS PLATFORM</small></div>
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav className="nav">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} title={label}><Icon size={18} /><span>{label}</span></NavLink>
          ))}
        </nav>
        <div className="side-bottom">
          <div className="status-card" title="API health">
            <span className={`dot ${online ? 'ok' : health.loading && !health.data ? '' : 'bad'}`} />
            <div>
              <b>{online ? 'API connected' : health.loading && !health.data ? 'Checking…' : 'API offline'}</b>
              <small>{online ? `PostgreSQL · ${health.data.latency} ms` : 'Start the FastAPI server'}</small>
            </div>
          </div>
          <button className="collapse-btn" onClick={() => setCollapsed((c) => !c)}>
            {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}<span>Collapse</span>
          </button>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="actions">
            <button className="ibtn menu-btn" onClick={() => setOpen(true)} aria-label="Open menu"><Menu size={17} /></button>
            <div className="crumb"><span>Workspace</span><i>/</i><b>{page}</b></div>
          </div>
          <div className="actions">
            <button className="ibtn" onClick={() => setPalette(true)} aria-label="Search"><Search size={16} /><span className="kbd">Ctrl K</span></button>
            <select className="select-sm" value={currency} onChange={(e) => setCurrency(e.target.value)} aria-label="Display currency" title="Display symbol only – values are not converted">
              {Object.keys(CURRENCIES).map((c) => <option key={c}>{c}</option>)}
            </select>
            <button className="ibtn" onClick={toggleTheme} aria-label="Toggle theme">{theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}</button>
            <button className="ibtn" onClick={doRefresh} aria-label="Refresh data"><RefreshCw size={16} className={spinning ? 'spin' : ''} /></button>
            <span className={`live ${online ? '' : 'off'}`}><i className={`dot ${online ? 'ok' : 'bad'}`} />{online ? 'LIVE DATA' : 'OFFLINE'}</span>
          </div>
        </header>
        <ErrorBoundary resetKey={pathname}>
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/revenue" element={<Revenue />} />
            <Route path="/churn" element={<Churn />} />
            <Route path="/sources" element={<Sources />} />
            <Route path="/methodology" element={<Methodology />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </ErrorBoundary>
      </main>
      <CommandPalette />
    </div>
  );
}
