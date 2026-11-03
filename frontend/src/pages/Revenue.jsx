import { useMemo, useState } from 'react';
import { BarChart3, CircleDollarSign, CreditCard, Download, FileText, LineChart, Receipt, TrendingUp, Wallet } from 'lucide-react';
import { useApi, useTitle } from '../hooks';
import { useFmt } from '../context';
import { getAccounts, getInvoiceStatus, getMonthlyRevenue, getPlans, getRegions } from '../api';
import { Card, CardHead, DataTable, ErrorState, Metric, Note, PageHeader, Pager, Panel, Segmented } from '../components/ui';
import Chart, { COLORS } from '../components/Chart';
import { delta, downloadCsv, longDate, monthLabel, ratio, sum } from '../format';
import { STATUS_COLORS } from '../config';

const RANGES = [['all', 'All'], ['24', '24M'], ['12', '12M'], ['6', '6M']];

export default function Revenue() {
  useTitle('Revenue Analytics');
  const f = useFmt();
  const [range, setRange] = useState('all');
  const [kind, setKind] = useState('bar');
  const [page, setPage] = useState(0);
  const [size, setSize] = useState(10);
  const mo = useApi('monthly', getMonthlyRevenue);
  const rg = useApi('regions', getRegions);
  const pl = useApi('plans', getPlans);
  const st = useApi('inv-status', getInvoiceStatus);
  const ac = useApi(`accounts:${page}:${size}`, () => getAccounts({ limit: size + 1, offset: page * size }));
  const error = mo.error || rg.error || pl.error || st.error;

  const all = mo.data || [];
  const monthly = useMemo(() => (range === 'all' ? all : all.slice(-Number(range))), [all, range]);
  const labels = monthly.map((m) => monthLabel(m.billing_month));
  const billed = sum(monthly, 'total_billed'), collected = sum(monthly, 'total_collected'), invoices = sum(monthly, 'invoice_count');
  const peak = monthly.reduce((p, m) => (Number(m.total_billed) > Number(p?.total_billed ?? -1) ? m : p), null);
  const last = monthly.at(-1), prev = monthly.at(-2);
  const sp = (k) => monthly.map((m) => m[k]);
  const hov = (n) => `%{x}<br>${n}: ${f.symbol}%{y:,.0f}<extra></extra>`;
  const trace = (name, key, color) => kind === 'bar'
    ? { x: labels, y: sp(key), name, type: 'bar', marker: { color, cornerradius: 4 }, hovertemplate: hov(name) }
    : { x: labels, y: sp(key), name, type: 'scatter', mode: 'lines+markers', line: { color, width: 2.5, shape: 'spline' }, marker: { size: 5 }, hovertemplate: hov(name) };

  const regions = rg.data || [], plans = pl.data || [], status = st.data || [];
  const regTotal = sum(regions, 'total_billed');
  const rows = (ac.data || []).slice(0, size);

  return (
    <div className="page">
      <PageHeader title="Revenue Analytics" sub="Explore invoice trends, collections, regions and plan performance."
        right={<button className="btn" onClick={() => downloadCsv(all, 'horizon_monthly_billing.csv')} disabled={!all.length}><Download size={15} /> Export monthly CSV</button>} />
      <ErrorState message={error} onRetry={() => { mo.reload(); rg.reload(); pl.reload(); st.reload(); }} />

      <div className="toolbar"><Segmented options={RANGES} value={range} onChange={setRange} />
        <span className="updated">{monthly.length ? `${monthLabel(monthly[0].billing_month)} – ${monthLabel(monthly.at(-1).billing_month)} · ${monthly.length} months` : ''}</span></div>

      <div className="grid g5">
        <Metric loading={mo.loading && !mo.data} label="Total Billed" value={f.money(billed)} note="Amount due" icon={CircleDollarSign} change={delta(last?.total_billed, prev?.total_billed)} spark={sp('total_billed')} />
        <Metric loading={mo.loading && !mo.data} label="Collected" value={f.money(collected)} note="Amount paid" icon={CreditCard} tone="green" change={delta(last?.total_collected, prev?.total_collected)} spark={sp('total_collected')} />
        <Metric loading={mo.loading && !mo.data} label="Collection Rate" value={f.pct(ratio(collected, billed))} note="Paid ÷ billed" icon={TrendingUp} tone="purple" />
        <Metric loading={mo.loading && !mo.data} label="Unpaid Balance" value={f.money(billed - collected)} note="Outstanding" icon={Wallet} tone="amber" spark={sp('unpaid_balance')} />
        <Metric loading={mo.loading && !mo.data} label="Avg Invoice" value={f.money(invoices ? billed / invoices : 0)} note={peak ? `Peak: ${monthLabel(peak.billing_month)}` : '—'} icon={Receipt} tone="red" spark={sp('invoice_count')} />
      </div>

      <div className="mt"><Panel title="Monthly billing & collections" sub="Trend across the selected invoice period"
        right={<Segmented value={kind} onChange={setKind} options={[['bar', 'Bars', BarChart3], ['line', 'Lines', LineChart]]} />}>
        <Chart loading={mo.loading && !mo.data} height={330} data={[trace('Billed', 'total_billed', COLORS.accent), trace('Collected', 'total_collected', COLORS.teal)]}
          layout={{ barmode: 'group', bargap: 0.25, yaxis: { tickprefix: f.symbol, tickformat: '~s' }, xaxis: { nticks: 12 } }} />
      </Panel></div>

      <div className="grid g2 mt">
        <Panel title="Collection rate by month" sub="Share of billed amount that was collected">
          <Chart loading={mo.loading && !mo.data} height={280} data={[{ x: labels, y: monthly.map((m) => ratio(m.total_collected, m.total_billed)), type: 'scatter', mode: 'lines', fill: 'tozeroy', fillcolor: 'rgba(167,139,250,.14)', line: { color: COLORS.violet, width: 2.5, shape: 'spline' }, hovertemplate: '%{x}: %{y:.1f}%<extra></extra>' }]}
            layout={{ yaxis: { ticksuffix: '%', range: [0, 100] }, xaxis: { nticks: 8 } }} />
        </Panel>
        <Panel title="Invoice status" sub="Invoice count by status">
          <Chart loading={st.loading && !st.data} height={280} data={[{ type: 'pie', hole: 0.64, sort: false, labels: status.map((x) => x.invoice_status), values: status.map((x) => x.invoice_count), marker: { colors: status.map((x) => STATUS_COLORS[x.invoice_status] || COLORS.slate) }, textinfo: 'label+percent', textfont: { color: '#fff' }, hovertemplate: '%{label}: %{value:,} invoices<extra></extra>' }]}
            layout={{ showlegend: false, margin: { l: 10, r: 10, t: 6, b: 6 } }} />
        </Panel>
        <Panel title="Regional billing" sub={`Billed amount by region · ${regions.length} regions`}>
          <Chart loading={rg.loading && !rg.data} height={280} data={[{ type: 'bar', orientation: 'h', y: regions.map((x) => x.region), x: regions.map((x) => x.total_billed), marker: { color: COLORS.accent, cornerradius: 5 }, customdata: regions.map((x) => ratio(x.total_billed, regTotal)), hovertemplate: `%{y}: ${f.symbol}%{x:,.0f} (%{customdata:.1f}%)<extra></extra>` }]}
            layout={{ xaxis: { tickprefix: f.symbol, tickformat: '~s' }, yaxis: { autorange: 'reversed' }, margin: { l: 80, r: 14, t: 10, b: 36 } }} />
        </Panel>
        <Panel title="Plan performance" sub="Billed vs collected by plan">
          <Chart loading={pl.loading && !pl.data} height={280} data={[
            { type: 'bar', name: 'Billed', x: plans.map((x) => x.plan_name), y: plans.map((x) => x.total_billed), marker: { color: COLORS.accent, cornerradius: 4 }, hovertemplate: hov('Billed') },
            { type: 'bar', name: 'Collected', x: plans.map((x) => x.plan_name), y: plans.map((x) => x.total_collected), marker: { color: COLORS.teal, cornerradius: 4 }, hovertemplate: hov('Collected') }
          ]} layout={{ barmode: 'group', bargap: 0.3, yaxis: { tickprefix: f.symbol, tickformat: '~s' } }} />
        </Panel>
      </div>

      <Card className="mt">
        <CardHead title="Plan breakdown" sub="Account reach, seats and collection efficiency per plan" />
        <DataTable loading={pl.loading} rows={plans} columns={[
          { key: 'plan_name', label: 'Plan', render: (r) => <b>{r.plan_name}</b> },
          { key: 'account_count', label: 'Accounts', right: true, render: (r) => f.num(r.account_count) },
          { key: 'invoice_count', label: 'Invoices', right: true, render: (r) => f.num(r.invoice_count) },
          { key: 'average_seats', label: 'Avg seats', right: true, render: (r) => Number(r.average_seats).toFixed(1) },
          { key: 'total_billed', label: 'Billed', right: true, render: (r) => f.money(r.total_billed) },
          { key: 'total_collected', label: 'Collected', right: true, render: (r) => f.money(r.total_collected) },
          { key: 'rate', label: 'Collection', render: (r) => { const p = ratio(r.total_collected, r.total_billed); return <div className="score"><div className="track"><i style={{ width: `${p}%`, background: 'var(--good)' }} /></div><b>{p.toFixed(0)}%</b></div>; } }
        ]} />
      </Card>

      <Card className="mt">
        <CardHead title="Top accounts by billing" sub="Highest billed accounts from the invoice source"
          right={<button className="btn" onClick={() => downloadCsv(rows, 'horizon_top_accounts.csv')} disabled={!rows.length}><Download size={15} /> Export page</button>} />
        <DataTable loading={ac.loading} rows={rows} columns={[
          { key: 'account_id', label: 'Account', mono: true, render: (r) => <><FileText size={13} style={{ verticalAlign: -2, marginRight: 8, color: 'var(--faint)' }} />{r.account_id}</> },
          { key: 'subscription_count', label: 'Subscriptions', right: true },
          { key: 'invoice_count', label: 'Invoices', right: true },
          { key: 'first_invoice_date', label: 'First invoice', render: (r) => longDate(r.first_invoice_date) },
          { key: 'latest_invoice_date', label: 'Latest invoice', render: (r) => longDate(r.latest_invoice_date) },
          { key: 'total_billed', label: 'Billed', right: true, render: (r) => f.money(r.total_billed) },
          { key: 'unpaid_balance', label: 'Unpaid', right: true, render: (r) => <span style={{ color: Number(r.unpaid_balance) > 0 ? 'var(--warn)' : 'var(--muted)' }}>{f.money(r.unpaid_balance)}</span> }
        ]} />
        <Pager page={page} size={size} onSize={(n) => { setSize(n); setPage(0); }} onPage={setPage} hasNext={(ac.data || []).length > size} count={rows.length} unit="accounts" />
      </Card>
      <Note warn>Collected amount is the sum of <code>amount_paid</code> in the source and is not automatically equivalent to recognised revenue. The currency symbol is a display preference; values are not converted.</Note>
    </div>
  );
}
