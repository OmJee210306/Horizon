import { Activity, ArrowRight, BarChart3, CheckCircle2, Database, Server, ShieldCheck, XCircle } from 'lucide-react';
import { useApi, useTitle } from '../hooks';
import { useFmt } from '../context';
import { getHealth, getOverview, getSources } from '../api';
import { Card, CardHead, ErrorState, Note, PageHeader, SectionLabel } from '../components/ui';
import { longDate } from '../format';

const META = { primary_analytics: ['blue', Database, 'PRIMARY ANALYTICS'], churn_lab: ['purple', Activity, 'INDEPENDENT SYNTHETIC DATA'], benchmarks: ['green', BarChart3, 'REFERENCE DATA'] };

export default function Sources() {
  useTitle('Data Sources');
  const f = useFmt();
  const src = useApi('sources', getSources);
  const ov = useApi('overview', getOverview);
  const hl = useApi('health', getHealth);
  const b = ov.data?.billing_source || {}, c = ov.data?.independent_churn_source || {};
  const facts = {
    primary_analytics: [['Schema', 'primary_analytics'], ['Invoice records', f.num(b.invoice_rows)], ['Accounts', f.num(b.accounts_in_invoice_data)], ['Date range', `${longDate(b.first_invoice_date)} – ${longDate(b.latest_invoice_date)}`]],
    churn_lab: [['Schema', 'churn_lab'], ['Customers', f.num(c.customers)], ['Churned', f.num(c.churned_customers)], ['Observed churn', f.pct(c.observed_churn_rate_pct, 2)]],
    benchmarks: [['Schema', 'benchmarks'], ['Reference records', '118'], ['License', 'CC BY 4.0'], ['Origin', 'RetentionCheck']]
  };
  const ok = hl.data?.status === 'ok';

  return (
    <div className="page">
      <PageHeader title="Data Sources" sub="The independent datasets powering HORIZON, and the health of the pipeline that serves them." />
      <ErrorState message={src.error} onRetry={src.reload} />
      <SectionLabel tag="ISOLATED BY SCHEMA">SOURCE DATASETS</SectionLabel>
      <div className="grid g3">
        {(src.data?.sources || []).map((s) => {
          const [tone, Icon, tag] = META[s.schema] || ['blue', Database, 'SOURCE'];
          return (
            <Card key={s.schema} className="src-card">
              <span className={`mi ${tone}`} style={{ width: 44, height: 44 }}><Icon size={22} /></span>
              <div className="src-type">{tag}</div>
              <h3>{s.name}</h3><p>{s.description}</p>
              {(facts[s.schema] || []).map(([k, v]) => <div className="meta" key={k}><span>{k}</span><b>{v}</b></div>)}
            </Card>
          );
        })}
      </div>

      <SectionLabel>DATA FLOW</SectionLabel>
      <Card>
        <div className="flow">
          {[['Raw files', 'CSV · XLSX · JSON'], ['Python scripts', 'Audit · validate · model'], ['PostgreSQL', 'Isolated schemas + SQL views'], ['FastAPI', 'Read-only analytics API'], ['React dashboard', 'This interface']].flatMap(([t, s], i, a) => [
            <div key={t}><b>{t}</b><small>{s}</small></div>, i < a.length - 1 && <div className="arrow" key={t + 'a'}><ArrowRight size={18} /></div>
          ])}
        </div>
      </Card>

      <div className="grid g2 mt">
        <Card>
          <CardHead title="System status" sub="Live check of the API and database" />
          <div style={{ padding: '10px 20px 18px' }}>
            {[['API server', ok, hl.data ? `${hl.data.latency} ms response` : hl.error || 'Checking…'], ['PostgreSQL', ok && hl.data?.database === 'connected', hl.data?.database || 'Unknown']].map(([n, good, d]) => (
              <div className="meta" key={n}><span style={{ display: 'flex', gap: 10, alignItems: 'center' }}><Server size={15} />{n}</span>
                <b style={{ display: 'flex', gap: 8, alignItems: 'center', color: good ? 'var(--good)' : 'var(--bad)' }}>{good ? <CheckCircle2 size={15} /> : <XCircle size={15} />}{d}</b></div>
            ))}
          </div>
        </Card>
        <Card>
          <CardHead title="Governance" sub="How HORIZON keeps sources honest" />
          <div className="insights">
            <div className="insight"><span className="mi green"><ShieldCheck size={15} /></span><span>{src.data?.data_governance_note || 'No customer-level join is performed across the independent billing and churn datasets.'}</span></div>
            <div className="insight"><span className="mi blue"><Database size={15} /></span><span>The API only reads from PostgreSQL views and tables; it never creates or modifies data.</span></div>
          </div>
        </Card>
      </div>
      <Note>{ov.data?.source_note}</Note>
    </div>
  );
}
