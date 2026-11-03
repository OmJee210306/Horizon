import { AlertTriangle, CircleDollarSign, CreditCard, Percent, Receipt, Sparkles, Target, Trophy, Users, Wallet } from 'lucide-react';
import { useApi, useTitle } from '../hooks';
import { useFmt } from '../context';
import { getOverview, getMonthlyRevenue, getChurnSummary, getRegions, getPlans } from '../api';
import { ErrorState, Metric, Note, PageHeader, Panel, SectionLabel, Card, CardHead } from '../components/ui';
import Chart, { COLORS } from '../components/Chart';
import { delta, monthLabel, ratio, sum } from '../format';
import { TIER_COLORS } from '../config';

export default function Overview() {
  useTitle('Overview');
  const f = useFmt();
  const ov = useApi('overview', getOverview);
  const mo = useApi('monthly', getMonthlyRevenue);
  const ch = useApi('churn-summary', getChurnSummary);
  const rg = useApi('regions', getRegions);
  const pl = useApi('plans', getPlans);
  const error = ov.error || mo.error || ch.error;

  const b = ov.data?.billing_source || {};
  const c = ov.data?.independent_churn_source || {};
  const monthly = mo.data || [];
  const tiers = ch.data?.priority_tiers || [];
  const labels = monthly.map((m) => monthLabel(m.billing_month));
  const last = monthly.at(-1), prev = monthly.at(-2);
  const series = (k) => monthly.map((m) => m[k]);
  const collRate = ratio(b.total_collected, b.total_billed);

  const insights = [];
  const regions = rg.data || [], plans = pl.data || [];
  if (regions.length) { const t = regions[0]; insights.push(['blue', Trophy, <><b>{t.region}</b> leads billing with {f.moneyC(t.total_billed)} ({ratio(t.total_billed, sum(regions, 'total_billed')).toFixed(1)}% of total).</>]); }
  if (plans.length) { const t = plans[0]; insights.push(['purple', Sparkles, <><b>{t.plan_name}</b> is the top plan by billing at {f.moneyC(t.total_billed)} across {f.num(t.account_count)} accounts.</>]); }
  if (b.total_billed) insights.push([collRate >= 85 ? 'green' : 'amber', Wallet, <>Collections stand at <b>{collRate.toFixed(1)}%</b> of billed amount, leaving {f.moneyC(b.unpaid_balance)} outstanding.</>]);
  if (tiers.length && c.observed_churn_rate_pct) {
    const crit = tiers[0], capture = ratio(sum(tiers.slice(0, 2), 'actual_churned_customers'), sum(tiers, 'actual_churned_customers'));
    insights.push(['red', Target, <>The <b>Critical</b> tier churns at {Number(crit.observed_churn_rate_pct).toFixed(1)}%, <b>{(crit.observed_churn_rate_pct / c.observed_churn_rate_pct).toFixed(0)}×</b> the baseline. Critical + High (5% of customers) hold {capture.toFixed(0)}% of churners.</>]);
  }

  return (
    <div className="page">
      <PageHeader title="Overview" sub="A unified view of billing performance and customer retention signals." />
      <ErrorState message={error} onRetry={() => { ov.reload(); mo.reload(); ch.reload(); }} />

      <SectionLabel tag="PRIMARY ANALYTICS SOURCE">BILLING PERFORMANCE</SectionLabel>
      <div className="grid g4">
        <Metric loading={ov.loading && !ov.data} label="Total Billed" value={f.money(b.total_billed)} note={`${f.num(b.invoice_rows)} invoices`} icon={CircleDollarSign} change={delta(last?.total_billed, prev?.total_billed)} spark={series('total_billed')} />
        <Metric loading={ov.loading && !ov.data} label="Total Collected" value={f.money(b.total_collected)} note={`${collRate.toFixed(1)}% collection rate`} icon={CreditCard} tone="green" change={delta(last?.total_collected, prev?.total_collected)} spark={series('total_collected')} />
        <Metric loading={ov.loading && !ov.data} label="Unpaid Balance" value={f.money(b.unpaid_balance)} note="Billed less paid" icon={Receipt} tone="amber" spark={series('unpaid_balance')} />
        <Metric loading={ov.loading && !ov.data} label="Accounts Invoiced" value={f.num(b.accounts_in_invoice_data)} note="Distinct account IDs" icon={Users} tone="purple" spark={series('active_accounts_in_invoices')} />
      </div>

      <SectionLabel tag="INDEPENDENT SYNTHETIC CHURN SOURCE">CUSTOMER RETENTION</SectionLabel>
      <div className="grid g3">
        <Metric loading={ov.loading && !ov.data} label="Customers Analysed" value={f.num(c.customers)} note="Synthetic churn dataset" icon={Users} />
        <Metric loading={ov.loading && !ov.data} label="Churned Customers" value={f.num(c.churned_customers)} note="Observed target labels" icon={AlertTriangle} tone="amber" />
        <Metric loading={ov.loading && !ov.data} label="Observed Churn Rate" value={f.pct(c.observed_churn_rate_pct, 2)} note="Churned ÷ total customers" icon={Percent} tone="red" />
      </div>

      <div className="grid g-wide mt">
        <Panel title="Monthly billing trend" sub="Billed vs collected amounts by invoice month">
          <Chart loading={mo.loading && !mo.data} height={310} data={[
            { x: labels, y: series('total_billed'), name: 'Billed', type: 'scatter', mode: 'lines', fill: 'tozeroy', fillcolor: 'rgba(108,123,255,.12)', line: { color: COLORS.accent, width: 2.5, shape: 'spline' }, hovertemplate: `%{x}<br>Billed: ${f.symbol}%{y:,.0f}<extra></extra>` },
            { x: labels, y: series('total_collected'), name: 'Collected', type: 'scatter', mode: 'lines', line: { color: COLORS.teal, width: 2.5, shape: 'spline' }, hovertemplate: `%{x}<br>Collected: ${f.symbol}%{y:,.0f}<extra></extra>` }
          ]} layout={{ yaxis: { tickprefix: f.symbol, tickformat: '~s' }, xaxis: { nticks: 10 } }} />
        </Panel>
        <Panel title="Churn priority distribution" sub="Customers by model-score percentile tier">
          <Chart loading={ch.loading && !ch.data} height={310} data={[{
            type: 'pie', hole: 0.64, sort: false, labels: tiers.map((t) => t.priority_tier), values: tiers.map((t) => t.customer_count),
            marker: { colors: tiers.map((t) => TIER_COLORS[t.priority_tier]) }, textinfo: 'percent', textfont: { color: '#fff' }, hovertemplate: '%{label}: %{value:,} customers<extra></extra>'
          }]} layout={{ margin: { l: 10, r: 10, t: 6, b: 6 }, legend: { orientation: 'h', y: -0.04, x: 0.1 }, annotations: [{ text: `<b>${f.compact(c.customers)}</b><br>customers`, showarrow: false, font: { size: 15 } }] }} />
        </Panel>
      </div>

      {insights.length > 0 && (
        <Card className="mt">
          <CardHead title="Key insights" sub="Generated automatically from the current data" />
          <div className="insights">
            {insights.map(([tone, Icon, text], i) => <div className="insight" key={i}><span className={`mi ${tone}`}><Icon size={15} /></span><span>{text}</span></div>)}
          </div>
        </Card>
      )}
      <Note>Billing and churn are separate datasets. Their KPIs are shown side by side and are never combined into a single customer population.</Note>
      <footer className="footer"><span>HORIZON Analytics & Decision Platform</span><span>React · FastAPI · PostgreSQL · Plotly</span></footer>
    </div>
  );
}
