import { CURRENCIES } from './config';

export function makeFmt(code = 'USD') {
  const { locale, symbol } = CURRENCIES[code] || CURRENCIES.USD;
  const full = new Intl.NumberFormat(locale, { style: 'currency', currency: code, maximumFractionDigits: 0 });
  const comp = new Intl.NumberFormat(locale, { notation: 'compact', maximumFractionDigits: 1 });
  const int = new Intl.NumberFormat(locale);
  return {
    symbol,
    money: (n) => full.format(Number(n || 0)),
    moneyC: (n) => symbol + comp.format(Number(n || 0)),
    num: (n) => int.format(Number(n || 0)),
    compact: (n) => comp.format(Number(n || 0)),
    pct: (n, d = 1) => `${Number(n || 0).toFixed(d)}%`
  };
}

export const toDate = (iso) => new Date(String(iso).slice(0, 10) + 'T00:00:00');
export const monthLabel = (iso) => toDate(iso).toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
export const longDate = (iso) => (iso ? toDate(iso).toLocaleDateString('en-US', { day: 'numeric', month: 'short', year: 'numeric' }) : '—');
export const pretty = (s) => {
  const t = String(s ?? '').replace(/_/g, ' ').trim();
  return t.charAt(0).toUpperCase() + t.slice(1);
};
export const sum = (a, k) => a.reduce((s, x) => s + Number(x[k] || 0), 0);
export const ratio = (a, b) => (Number(b) ? (100 * Number(a)) / Number(b) : 0);
export const delta = (cur, prev) => (Number(prev) ? ((Number(cur) - Number(prev)) / Math.abs(Number(prev))) * 100 : null);

export function parseContributors(text) {
  return String(text || '')
    .split(';')
    .map((p) => p.trim().match(/^(.+?)\s*\(([+-]?[\d.]+)\)$/))
    .filter(Boolean)
    .map((m) => ({ name: pretty(m[1].replace('payment_status_', 'payment: ')), value: Number(m[2]) }));
}

export function prettyBand(b) {
  const m = String(b).match(/[([]\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*[)\]]/);
  if (!m) return String(b);
  const f = (v) => { const n = Number(v); return String(Math.abs(n) < 10 ? Number(n.toFixed(2)) : Math.round(n)); };
  return `${f(m[1])} – ${f(m[2])}`;
}
export const bandStart = (b) => Number((String(b).match(/-?[\d.]+/) || [0])[0]);

export function downloadCsv(rows, name) {
  if (!rows?.length) return;
  const h = Object.keys(rows[0]);
  const esc = (v) => `"${String(v ?? '').replaceAll('"', '""')}"`;
  const csv = [h.join(','), ...rows.map((r) => h.map((k) => esc(r[k])).join(','))].join('\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const a = Object.assign(document.createElement('a'), { href: url, download: name });
  a.click();
  URL.revokeObjectURL(url);
}
