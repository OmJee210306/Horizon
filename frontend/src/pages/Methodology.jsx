
import { AlertTriangle, Brain, FlaskConical, Gauge } from 'lucide-react';
import { useTitle } from '../hooks';
import { Badge, Card, CardHead, Metric, PageHeader } from '../components/ui';
import { MODEL_FACTS as M } from '../config';
import { useFmt } from '../context';

export default function Methodology() {
  useTitle('Methodology');
  const f = useFmt();

  return (
    <div className="page">
      <PageHeader
        title="Methodology"
        sub="How the calibrated churn model works, what its scores mean, and where its limits are."
      />

      <div className="grid g3">
        <Metric
          label="Model"
          value="Logistic Regression"
          note="Sigmoid calibrated"
          icon={Brain}
        />
        <Metric
          label="Test PR-AUC"
          value={M.prAuc.toFixed(3)}
          note="Held-out test set"
          icon={Gauge}
          tone="purple"
        />
        <Metric
          label="Customers scored"
          value={f.num(M.rowsScored)}
          note="Synthetic churn dataset"
          icon={FlaskConical}
          tone="green"
        />
      </div>

      <div className="grid g3 mt">
        <Metric
          label="Test ROC-AUC"
          value={M.rocAuc.toFixed(3)}
          note="Ranking discrimination"
          icon={Gauge}
        />
        <Metric
          label="Brier Score"
          value={M.brierScore.toFixed(4)}
          note="Probability calibration"
          icon={Gauge}
          tone="purple"
        />
        <Metric
          label="Review Threshold"
          value={`${(M.threshold * 100).toFixed(1)}%`}
          note="Selected on validation data using F1"
          icon={AlertTriangle}
          tone="green"
        />
      </div>

      <Card className="mt">
        <CardHead
          title="Deployed model details"
          sub={`Model version: ${M.version}`}
        />
        <div className="insights">
          <div className="insight">
            <span><b>Algorithm.</b> Logistic Regression with sigmoid (Platt) calibration.</span>
          </div>
          <div className="insight">
            <span><b>Features.</b> 5 numeric and 6 categorical features. Payment status and churn risk score are excluded.</span>
          </div>
          <div className="insight">
            <span><b>Test precision.</b> {(M.precision * 100).toFixed(2)}%</span>
          </div>
          <div className="insight">
            <span><b>Test recall.</b> {(M.recall * 100).toFixed(2)}%</span>
          </div>
          <div className="insight">
            <span><b>Test F1.</b> {M.f1.toFixed(4)}</span>
          </div>
          <div className="insight">
            <span><b>Top 1% lift.</b> {M.topOnePercentLift.toFixed(2)}x on the held-out test set.</span>
          </div>
        </div>
      </Card>

      <div className="grid g2 mt">
        <Card>
          <CardHead
            title="Priority tiers"
            sub="Relative ranking bands by score percentile"
          />
          <div className="insights">
            {M.tiers.map(([t, d]) => (
              <div className="insight" key={t}>
                <Badge tier={t} />
                <span>{d}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <CardHead
            title="Explainability"
            sub="How to interpret model drivers"
          />
          <div className="insights">
            <div className="insight">
              <span><b>Contributions.</b> {M.explainability}</span>
            </div>
            <div className="insight">
              <span><b>Feature importance.</b> {M.importance}</span>
            </div>
          </div>
        </Card>
      </div>

      <Card className="mt">
        <CardHead
          title="Known limitations"
          sub="Read before using any output for decisions"
        />
        <ul className="limits">
          {M.limitations.map((l) => (
            <li key={l}>
              <AlertTriangle size={16} />
              <span>{l}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
