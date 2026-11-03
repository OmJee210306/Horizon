import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Download, Layers, ListFilter, Search, ShieldAlert, Target, Users, BrainCircuit, Activity } from 'lucide-react';
import { useApi, useDebounce, useTitle } from '../hooks';
import { useFmt } from '../context';
import { getChurnBands, getChurnFeatures, getChurnSegments, getChurnSummary, getCustomers, getOverview, getChurnModelInfo, predictChurn } from '../api';
import { Badge, Card, CardHead, DataTable, ErrorState, Metric, Note, PageHeader, Pager, Panel, Segmented } from '../components/ui';
import Chart, { COLORS } from '../components/Chart';
import CustomerDrawer from '../components/CustomerDrawer';
import { bandStart, downloadCsv, parseContributors, pretty, prettyBand, ratio, sum } from '../format';
import { TIERS, TIER_COLORS } from '../config';

const TABS = [['overview', 'Risk overview', Target], ['segments', 'Segments', Layers], ['customers', 'Customer explorer', Users], ['predict', 'Predict customer', BrainCircuit]];
const tierIcon = [ShieldAlert, AlertTriangle, Users, Users];
const tierTone = ['red', 'amber', 'purple', 'green'];

export default function Churn() {
  useTitle('Churn Intelligence');
  const [tab, setTab] = useState('overview');
  const sm = useApi('churn-summary', getChurnSummary);
  const ov = useApi('overview', getOverview);
  const tiers = (sm.data?.priority_tiers || []).map((t) => ({
    ...t,
    actual_churned_customers: Number(t.actual_churned_customers ?? t.observed_churned_customers ?? 0),
    observed_churn_rate_pct: Number(t.observed_churn_rate_pct ?? (Number(t.customer_count) ? (100 * Number(t.observed_churned_customers || 0) / Number(t.customer_count)) : 0)),
    average_model_score: Number(t.average_model_score ?? t.average_predicted_probability ?? 0),
  }));

  return (
    <div className="page">
      <PageHeader title="Churn Intelligence" sub="Understand churn patterns, model signals and customer-level retention priorities." />
      <ErrorState message={sm.error} onRetry={sm.reload} />
      <div className="toolbar"><Segmented options={TABS} value={tab} onChange={setTab} /></div>
      {tab === 'overview' && <RiskOverview tiers={tiers} loading={sm.loading && !sm.data} baseline={ov.data?.independent_churn_source} />}
      {tab === 'segments' && <Segments baseline={Number(ov.data?.independent_churn_source?.observed_churn_rate_pct)} />}
      {tab === 'customers' && <Customers />}
      {tab === 'predict' && <CustomerPrediction />}
      <Note warn>{sm.data?.model_note || 'Risk tiers are relative score-percentile bands, not calibrated future churn probabilities.'} Payment-status timing must be validated before real-world use.</Note>
    </div>
  );
}

function CustomerPrediction() {
  const model = useApi('churn-model-info', getChurnModelInfo);
  const [form, setForm] = useState({
    monthly_recurring_revenue: '499',
    active_seats_used: '8',
    total_seats_allowed: '10',
    support_tickets_30d: '5',
    feature_adoption_rate: '0.35',
    industry: 'FinTech',
    country: 'India',
    company_size: 'Medium',
    account_manager: 'AM_12',
    plan_tier: 'Pro',
    billing_cycle: 'Monthly',
  });
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const fields = [
    ['monthly_recurring_revenue', 'Monthly recurring revenue', 'number', '0.01'],
    ['active_seats_used', 'Active seats used', 'number', '1'],
    ['total_seats_allowed', 'Total seats allowed', 'number', '1'],
    ['support_tickets_30d', 'Support tickets (30 days)', 'number', '1'],
    ['feature_adoption_rate', 'Feature adoption rate (0–1)', 'number', '0.01'],
    ['industry', 'Industry', 'text'],
    ['country', 'Country', 'text'],
    ['company_size', 'Company size', 'text'],
    ['account_manager', 'Account manager', 'text'],
    ['plan_tier', 'Plan tier', 'text'],
    ['billing_cycle', 'Billing cycle', 'text'],
  ];

  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }));

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    setResult(null);
    try {
      const payload = {
        monthly_recurring_revenue: form.monthly_recurring_revenue === '' ? null : Number(form.monthly_recurring_revenue),
        active_seats_used: form.active_seats_used === '' ? null : Number(form.active_seats_used),
        total_seats_allowed: form.total_seats_allowed === '' ? null : Number(form.total_seats_allowed),
        support_tickets_30d: form.support_tickets_30d === '' ? null : Number(form.support_tickets_30d),
        feature_adoption_rate: form.feature_adoption_rate === '' ? null : Number(form.feature_adoption_rate),
        industry: form.industry || null,
        country: form.country || null,
        company_size: form.company_size || null,
        account_manager: form.account_manager || null,
        plan_tier: form.plan_tier || null,
        billing_cycle: form.billing_cycle || null,
      };
      const response = await predictChurn(payload);
      setResult(response);
    } catch (e) {
      setError(e?.friendly || e?.message || 'Prediction failed. Check the API and input values.');
    } finally {
      setBusy(false);
    }
  };

  const inputStyle = {
    width: '100%', padding: '11px 12px', border: '1px solid var(--line)',
    borderRadius: 10, background: 'var(--panel2)', color: 'var(--text)', outline: 'none',
  };
  const labelStyle = { display: 'grid', gap: 7, color: 'var(--muted)', fontSize: 12.5, fontWeight: 550 };

  return (
    <div className="grid g-wide">
      <Card>
        <CardHead title="Score a customer" sub="Enter the approved model features to estimate a churn-risk score." />
        <form onSubmit={submit} style={{ padding: '4px 20px 20px' }}>
          <div className="grid g2">
            {fields.map(([key, label, type, step]) => (
              <label key={key} style={labelStyle}>
                {label}
                <input
                  type={type}
                  step={step || undefined}
                  min={type === 'number' ? 0 : undefined}
                  max={key === 'feature_adoption_rate' ? 1 : undefined}
                  value={form[key]}
                  onChange={(e) => update(key, e.target.value)}
                  style={inputStyle}
                />
              </label>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 20, flexWrap: 'wrap' }}>
            <button className="btn primary" type="submit" disabled={busy}>
              <BrainCircuit size={16} /> {busy ? 'Scoring customer…' : 'Predict churn risk'}
            </button>
            <button className="btn" type="button" disabled={busy} onClick={() => { setForm({ monthly_recurring_revenue: '', active_seats_used: '', total_seats_allowed: '', support_tickets_30d: '', feature_adoption_rate: '', industry: '', country: '', company_size: '', account_manager: '', plan_tier: '', billing_cycle: '' }); setResult(null); setError(''); }}>
              Clear form
            </button>
          </div>
        </form>
        {error && <div className="err" style={{ margin: '0 20px 20px' }}><AlertTriangle size={18} /><div><b>Prediction unavailable</b>{error}</div></div>}
        <Note warn>Use feature adoption as a proportion between 0 and 1 (for example, 35% = 0.35). Payment status, churn-risk score, customer identifiers and dates are intentionally excluded.</Note>
      </Card>
      <div style={{ display: 'grid', gap: 16, alignContent: 'start' }}>
        <Card>
          <CardHead title="Model configuration" sub="Active prediction model" />
          <div style={{ padding: '0 20px 20px', display: 'grid', gap: 12 }}>
            <div><div className="sub">Model</div><b>{model.data?.model_name || 'Loading model information…'}</b></div>
            <div className="grid g2">
              <div><div className="sub">Review threshold</div><div className="metric-value">{model.data ? `${(model.data.threshold * 100).toFixed(1)}%` : '—'}</div></div>
              <div><div className="sub">Calibration</div><b>{model.data?.calibration_method || '—'}</b></div>
            </div>
            <div className="sub">{model.data?.note || 'Model metadata is loading.'}</div>
            {model.error && <ErrorState message={model.error} onRetry={model.reload} />}
          </div>
        </Card>
        {result && (
          <Card>
            <CardHead title="Prediction result" sub="Model output for the entered customer profile" />
            <div style={{ padding: '0 20px 20px', display: 'grid', gap: 14 }}>
              <div>
                <div className="sub">Estimated churn probability</div>
                <div className="metric-value" style={{ fontSize: 38 }}>{Number(result.predicted_churn_probability_pct).toFixed(2)}%</div>
              </div>
              <div style={{ height: 9, borderRadius: 20, background: 'var(--panel2)', overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${Math.min(100, Math.max(0, result.predicted_churn_probability_pct))}%`, background: 'var(--accent)', borderRadius: 20 }} />
              </div>
              <Badge tier={result.decision === 'flag_for_review' ? 'High' : 'Monitor'}>{result.decision === 'flag_for_review' ? 'Flag for review' : 'Below review threshold'}</Badge>
              <div className="sub">Threshold: {(result.threshold * 100).toFixed(1)}% · Model version: {result.model_version}</div>
              {result.missing_features?.length > 0 && <div className="sub">Imputed missing inputs: {result.missing_features.join(', ')}</div>}
              <Note warn>{result.note}</Note>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}

function RiskOverview({ tiers, loading, baseline }) {
  const f = useFmt();
  const ft = useApi('churn-features', getChurnFeatures);
  const feats = (ft.data || []).slice(0, 8).reverse();
  const total = sum(tiers, 'customer_count'), churned = sum(tiers, 'actual_churned_customers');
  let cc = 0, ch = 0;
  const gains = tiers.map((t) => { cc += Number(t.customer_count); ch += Number(t.actual_churned_customers); return [ratio(cc, total), ratio(ch, churned)]; });
  const color = (t) => TIER_COLORS[t.priority_tier];
  return (
    <>
      <div className="grid g4">
        {(loading ? [...Array(4)] : tiers).map((t, i) => (
          <Metric key={i} loading={loading} label={t && `${t.priority_tier} priority`} value={t && f.num(t.customer_count)} icon={tierIcon[i]} tone={tierTone[i]}
            note={t && `${Number(t.observed_churn_rate_pct).toFixed(2)}% observed churn · ${f.num(t.actual_churned_customers)} churned`} />
        ))}
      </div>
      <div className="grid g-wide mt">
        <Panel title="Model signal importance" sub="Earlier exploratory model feature importance; payment status remains excluded from the active calibrated model">
          <Chart loading={ft.loading && !ft.data} height={340} data={[{ type: 'bar', orientation: 'h', y: feats.map((x) => pretty(x.feature)), x: feats.map((x) => x.mean_pr_auc_decrease),
            error_x: { type: 'data', array: feats.map((x) => x.std_pr_auc_decrease), color: 'rgba(148,163,184,.6)', thickness: 1.2 },
            marker: { color: feats.map((_, i) => `rgba(108,123,255,${0.35 + (0.65 * i) / Math.max(feats.length - 1, 1)})`), cornerradius: 5 }, hovertemplate: '%{y}: %{x:.4f}<extra></extra>' }]}
            layout={{ xaxis: { title: { text: 'PR-AUC decrease when shuffled' } }, margin: { l: 150, r: 20, t: 10, b: 44 } }} />
        </Panel>
        <Panel title="Observed churn by priority" sub="Historical churn rate within each tier">
          <Chart loading={loading} height={340} data={[{ type: 'bar', x: tiers.map((t) => t.priority_tier), y: tiers.map((t) => t.observed_churn_rate_pct), marker: { color: tiers.map(color), cornerradius: 6 },
            text: tiers.map((t) => `${Number(t.observed_churn_rate_pct).toFixed(1)}%`), textposition: 'outside', cliponaxis: false, hovertemplate: '%{x}: %{y:.2f}%<extra></extra>' }]}
            layout={{ yaxis: { ticksuffix: '%' }, margin: { l: 48, r: 14, t: 24, b: 36 } }} />
        </Panel>
      </div>
      <div className="grid g2 mt">
        <Panel title="Cumulative churn capture" sub="Share of all churners found when working tiers from highest risk down">
          <Chart loading={loading} height={290} data={[
            { x: [0, 100], y: [0, 100], mode: 'lines', name: 'Random targeting', line: { color: COLORS.slate, dash: 'dot', width: 1.5 }, hoverinfo: 'skip' },
            { x: [0, ...gains.map((g) => g[0])], y: [0, ...gains.map((g) => g[1])], mode: 'lines+markers', name: 'HORIZON ranking', text: ['', ...tiers.map((t) => t.priority_tier)], line: { color: COLORS.accent, width: 3 }, marker: { size: 8 }, fill: 'tonexty', fillcolor: 'rgba(108,123,255,.12)', hovertemplate: '%{text}: %{x:.0f}% of customers → %{y:.0f}% of churners<extra></extra>' }
          ]} layout={{ xaxis: { ticksuffix: '%', title: { text: 'Customers contacted' }, range: [0, 100] }, yaxis: { ticksuffix: '%', title: { text: 'Churners captured' }, range: [0, 100] } }} />
        </Panel>
        <Panel title="Average model score by tier" sub={`Relative ranking scores · baseline churn ${baseline ? Number(baseline.observed_churn_rate_pct).toFixed(2) + '%' : '—'}`}>
          <Chart loading={loading} height={290} data={[{ type: 'bar', orientation: 'h', y: tiers.map((t) => t.priority_tier), x: tiers.map((t) => Number(t.average_model_score) * 100), marker: { color: tiers.map(color), cornerradius: 5 }, hovertemplate: '%{y}: %{x:.1f}%<extra></extra>' }]}
            layout={{ xaxis: { ticksuffix: '%', range: [0, 100] }, yaxis: { autorange: 'reversed' } }} />
        </Panel>
      </div>
    </>
  );
}

function Segments({ baseline }) {
  const f = useFmt();
  const seg = useApi('segments', getChurnSegments);
  const bands = useApi('bands', getChurnBands);
  const [dim, setDim] = useState('');
  const catDims = useMemo(() => [...new Set((seg.data || []).map((x) => x.dimension))], [seg.data]);
  const numDims = useMemo(() => [...new Set((bands.data || []).map((x) => x.dimension))], [bands.data]);
  useEffect(() => { if (!dim && catDims.length) setDim(catDims[0]); }, [catDims, dim]);

  const isNum = numDims.includes(dim);
  const rows = useMemo(() => {
    if (isNum) return (bands.data || []).filter((x) => x.dimension === dim).sort((a, b) => bandStart(a.band) - bandStart(b.band)).map((x) => ({ ...x, label: prettyBand(x.band) }));
    return (seg.data || []).filter((x) => x.dimension === dim).sort((a, b) => b.churn_rate_pct - a.churn_rate_pct).map((x) => ({ ...x, label: String(x.segment) }));
  }, [isNum, seg.data, bands.data, dim]);

  const loading = (seg.loading && !seg.data) || (bands.loading && !bands.data);
  const max = Math.max(...rows.map((r) => Number(r.churn_rate_pct)), 0);
  const base = Number.isFinite(baseline) ? baseline : null;

  return (
    <>
      <div className="toolbar">
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <ListFilter size={16} color="var(--faint)" />
          <select className="select-sm" value={dim} onChange={(e) => setDim(e.target.value)} aria-label="Dimension" style={{ minWidth: 220 }}>
            <optgroup label="Categorical">{catDims.map((d) => <option key={d} value={d}>{pretty(d)}</option>)}</optgroup>
            <optgroup label="Numeric bands">{numDims.map((d) => <option key={d} value={d}>{pretty(d)}</option>)}</optgroup>
          </select>
        </div>
        {base != null && <span className="updated">Dashed line = overall churn {base.toFixed(2)}%</span>}
      </div>
      <ErrorState message={seg.error || bands.error} onRetry={() => { seg.reload(); bands.reload(); }} />
      <div className="grid g-wide mt">
        <Panel title={`Observed churn by ${pretty(dim).toLowerCase() || 'segment'}`} sub={isNum ? 'Ordered by value band' : 'Highest churn rate first'}>
          <Chart loading={loading} height={Math.max(300, rows.length * 38 + 60)} data={[{ type: 'bar', orientation: 'h', y: rows.map((r) => r.label), x: rows.map((r) => r.churn_rate_pct),
            marker: { color: rows.map((r) => (base != null && r.churn_rate_pct > base ? COLORS.amber : COLORS.accent)), cornerradius: 5 }, text: rows.map((r) => `${Number(r.churn_rate_pct).toFixed(2)}%`), textposition: 'outside', cliponaxis: false,
            customdata: rows.map((r) => [r.customer_count, r.churned_customers]), hovertemplate: '%{y}<br>%{x:.2f}% · %{customdata[1]:,} of %{customdata[0]:,}<extra></extra>' }]}
            layout={{ xaxis: { ticksuffix: '%', range: [0, max * 1.2 || 1] }, yaxis: { autorange: 'reversed' }, margin: { l: 120, r: 50, t: 10, b: 36 },
              shapes: base != null ? [{ type: 'line', xref: 'x', yref: 'paper', x0: base, x1: base, y0: 0, y1: 1, line: { color: COLORS.rose, dash: 'dash', width: 1.5 } }] : [] }} />
        </Panel>
        <Card>
          <CardHead title="Segment detail" sub="Counts behind each rate" />
          <DataTable loading={loading} rows={rows} columns={[
            { key: 'label', label: pretty(dim), render: (r) => <b>{r.label}</b> },
            { key: 'customer_count', label: 'Customers', right: true, render: (r) => f.num(r.customer_count) },
            { key: 'churned_customers', label: 'Churned', right: true, render: (r) => f.num(r.churned_customers) },
            { key: 'churn_rate_pct', label: 'Rate', right: true, render: (r) => <b style={{ color: base != null && r.churn_rate_pct > base ? 'var(--warn)' : 'inherit' }}>{Number(r.churn_rate_pct).toFixed(2)}%</b> }
          ]} />
        </Card>
      </div>
      <Note>Segment churn rates are retrospective associations in a synthetic dataset, not causal effects. Differences between segments may be small relative to sampling noise.</Note>
    </>
  );
}

function Customers() {
  const f = useFmt();
  const [q, setQ] = useState('');
  const [tier, setTier] = useState('');
  const [min, setMin] = useState(0);
  const [page, setPage] = useState(0);
  const [size, setSize] = useState(15);
  const [sel, setSel] = useState(null);
  const dq = useDebounce(q), dmin = useDebounce(min, 300);
  useEffect(() => setPage(0), [dq, tier, dmin, size]);

  const params = { tier, search: dq.trim(), min_score: dmin > 0 ? dmin / 100 : '' };
  const { data, loading, error, reload } = useApi(`cust:${JSON.stringify(params)}:${page}:${size}`, () => getCustomers({ ...params, limit: size + 1, offset: page * size }));
  const rows = (data || []).slice(0, size);
  const exportAll = async () => downloadCsv(await getCustomers({ ...params, limit: 200 }), 'horizon_customer_risk.csv');

  return (
    <Card>
      <CardHead title="Customer risk explorer" sub="Search, filter and open any customer for model drivers and the recommended action."
        right={<button className="btn primary" onClick={exportAll}><Download size={15} /> Export top 200</button>} />
      <div className="toolbar" style={{ padding: '16px 20px 0', marginBottom: 14 }}>
        <label className="search"><Search size={16} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search customer ID or company…" aria-label="Search customers" /></label>
        <Segmented options={[['', 'All'], ...TIERS.map((t) => [t, t])]} value={tier} onChange={setTier} />
        <label className="range">Min score <input type="range" min="0" max="99" step="1" value={min} onChange={(e) => setMin(+e.target.value)} /><b style={{ width: 36 }}>{min}%</b></label>
      </div>
      <ErrorState message={error} onRetry={reload} />
      <div className={`fade ${loading && data ? 'busy' : ''}`}>
        <DataTable loading={loading} rows={rows} empty="No customers match these filters." onRowClick={setSel} columns={[
          { key: 'customer_id', label: 'Customer', render: (r) => <><b>{r.company_name || '—'}</b><span className="sub mono">{r.customer_id}</span></> },
          { key: 'score', label: 'Model score', render: (r) => { const p = Math.max(0, Math.min(100, Number(r.predicted_churn_probability) * 100)); return <div className="score"><div className="track"><i style={{ width: `${p}%`, background: TIER_COLORS[r.priority_tier] }} /></div><b>{p.toFixed(1)}%</b></div>; } },
          { key: 'risk_percentile', label: 'Percentile', right: true, render: (r) => Number(r.risk_percentile).toFixed(1) },
          { key: 'priority_tier', label: 'Priority', render: (r) => <Badge tier={r.priority_tier} /> },
          { key: 'actual_is_churned', label: 'Outcome', render: (r) => (Number(r.actual_is_churned) === 1 ? <Badge tier="critical">Churned</Badge> : <Badge tier="neutral">Retained</Badge>) },
          { key: 'top', label: 'Model driver', render: (r) => { const t = parseContributors(r.top_model_contributors)[0]; return t ? <span className="chip">{t.name}</span> : '—'; } }
        ]} />
      </div>
      <Pager page={page} size={size} onSize={setSize} onPage={setPage} hasNext={(data || []).length > size} count={rows.length} unit="customers" />
      <CustomerDrawer customer={sel} onClose={() => setSel(null)} />
    </Card>
  );
}
