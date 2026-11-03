import { Component } from 'react';
import { AlertTriangle, ArrowDownRight, ArrowUpRight, ChevronLeft, ChevronRight, Inbox, Info, RefreshCw } from 'lucide-react';
import { useApp } from '../context';

export const Card = ({ children, className = '', ...p }) => <section className={`card ${className}`} {...p}>{children}</section>;

export function CardHead({ title, sub, right }) {
  return (
    <div className="card-head">
      <div><h3>{title}</h3>{sub && <p>{sub}</p>}</div>
      {right}
    </div>
  );
}

export function Panel({ title, sub, right, children, busy }) {
  return (
    <Card>
      <CardHead title={title} sub={sub} right={right} />
      <div className={`card-body fade ${busy ? 'busy' : ''}`}>{children}</div>
    </Card>
  );
}

export function PageHeader({ eyebrow = 'CUSTOMER RETENTION & REVENUE INTELLIGENCE', title, sub, right }) {
  const { updatedAt } = useApp();
  return (
    <div className="page-head">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{sub}</p>
      </div>
      <div style={{ textAlign: 'right' }}>
        {right}
        {updatedAt && <div className="updated">Updated {updatedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div>}
      </div>
    </div>
  );
}

export const SectionLabel = ({ children, tag }) => <div className="section-label">{children}{tag && <span>{tag}</span>}</div>;

export function Spark({ values = [], color = 'var(--accent)' }) {
  const v = values.map(Number).filter((x) => Number.isFinite(x));
  if (v.length < 2) return null;
  const min = Math.min(...v), max = Math.max(...v), span = max - min || 1;
  const pts = v.map((y, i) => [(i / (v.length - 1)) * 100, 34 - ((y - min) / span) * 30]);
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');
  const id = 'sp' + Math.abs(v.reduce((a, b, i) => a + b * (i + 1), 0) | 0);
  return (
    <svg className="spark" viewBox="0 0 100 40" preserveAspectRatio="none" aria-hidden>
      <defs><linearGradient id={id} x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor={color} stopOpacity=".3" /><stop offset="1" stopColor={color} stopOpacity="0" /></linearGradient></defs>
      <path d={`${line} L100,40 L0,40 Z`} fill={`url(#${id})`} />
      <path d={line} fill="none" stroke={color} strokeWidth="1.8" vectorEffect="non-scaling-stroke" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

const TONE_COLOR = { blue: 'var(--accent)', green: 'var(--good)', amber: 'var(--warn)', purple: 'var(--purple)', red: 'var(--bad)' };

export function Metric({ label, value, note, icon: Icon, tone = 'blue', change, spark, loading }) {
  if (loading) return <Card className="metric"><div className="sk" style={{ height: 14, width: '50%' }} /><div className="sk" style={{ height: 30, width: '70%', margin: '14px 0 10px' }} /><div className="sk" style={{ height: 12, width: '60%' }} /></Card>;
  return (
    <Card className="metric">
      <div className="metric-top"><span>{label}</span>{Icon && <span className={`mi ${tone}`}><Icon size={17} /></span>}</div>
      <div className="metric-value">{value}</div>
      <div className="metric-foot">
        <span>{note}</span>
        {change != null && Number.isFinite(change) && (
          <span className={`delta ${change >= 0 ? 'up' : 'down'}`} title="vs previous month">
            {change >= 0 ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}{Math.abs(change).toFixed(1)}%
          </span>
        )}
      </div>
      <Spark values={spark} color={TONE_COLOR[tone]} />
    </Card>
  );
}

export const Skeleton = ({ h = 280 }) => <div className="sk" style={{ height: h, margin: '6px 4px' }} />;

export function ErrorState({ message, onRetry }) {
  if (!message) return null;
  return (
    <div className="err" role="alert">
      <AlertTriangle size={22} />
      <div><b>Couldn't load data</b>{message}</div>
      {onRetry && <button className="btn" onClick={onRetry}><RefreshCw size={14} /> Retry</button>}
    </div>
  );
}

export const Note = ({ children, warn }) => <div className={`note ${warn ? 'warn' : ''}`}>{warn ? <AlertTriangle size={17} /> : <Info size={17} />}<span>{children}</span></div>;

export const Badge = ({ tier, children }) => <span className={`badge b-${String(tier).toLowerCase()}`}>{children ?? tier}</span>;

export function Segmented({ options, value, onChange }) {
  return (
    <div className="seg" role="tablist">
      {options.map((o) => {
        const [v, label, Icon] = Array.isArray(o) ? o : [o, o];
        return <button key={v} role="tab" aria-selected={value === v} className={value === v ? 'on' : ''} onClick={() => onChange(v)}>{Icon && <Icon size={14} />}{label}</button>;
      })}
    </div>
  );
}

export function DataTable({ columns, rows, onRowClick, loading, empty = 'No records found.' }) {
  if (loading && !rows?.length) return <div style={{ padding: 16 }}>{[...Array(6)].map((_, i) => <div key={i} className="sk" style={{ height: 38, marginBottom: 8 }} />)}</div>;
  if (!rows?.length) return <div className="empty"><Inbox size={28} /><div>{empty}</div></div>;
  return (
    <div className="tbl-wrap">
      <table>
        <thead><tr>{columns.map((c) => <th key={c.key} className={c.right ? 'r' : ''}>{c.label}</th>)}</tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.id ?? i} className={onRowClick ? 'click' : ''} onClick={onRowClick ? () => onRowClick(r) : undefined}>
              {columns.map((c) => <td key={c.key} className={c.right ? 'r' : c.mono ? 'mono' : ''}>{c.render ? c.render(r) : r[c.key]}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Pager({ page, hasNext, onPage, size, onSize, count, unit = 'records' }) {
  return (
    <div className="pager">
      <span>{count ? `Showing ${page * size + 1}–${page * size + count} ${unit}` : `No ${unit}`}</span>
      <div>
        {onSize && <select className="select-sm" value={size} onChange={(e) => onSize(+e.target.value)} aria-label="Rows per page">{[10, 15, 25, 50].map((n) => <option key={n} value={n}>{n} / page</option>)}</select>}
        <button className="ibtn" disabled={page === 0} onClick={() => onPage(page - 1)} aria-label="Previous page"><ChevronLeft size={16} /></button>
        <span>Page {page + 1}</span>
        <button className="ibtn" disabled={!hasNext} onClick={() => onPage(page + 1)} aria-label="Next page"><ChevronRight size={16} /></button>
      </div>
    </div>
  );
}

export class ErrorBoundary extends Component {
  state = { err: null };
  static getDerivedStateFromError(err) { return { err }; }
  componentDidUpdate(prev) { if (prev.resetKey !== this.props.resetKey && this.state.err) this.setState({ err: null }); }
  render() {
    return this.state.err ? <div className="page"><ErrorState message={`This page hit an unexpected error: ${this.state.err.message}`} onRetry={() => this.setState({ err: null })} /></div> : this.props.children;
  }
}
