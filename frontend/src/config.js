
export const API_URL =
  import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api';

export const TIERS = ['Critical', 'High', 'Medium', 'Monitor'];

export const TIER_COLORS = {
  Critical: '#ef5b6b',
  High: '#f59e4b',
  Medium: '#e9c24a',
  Monitor: '#3fbf9a'
};

export const STATUS_COLORS = {
  paid: '#2dd4bf',
  open: '#f59e4b',
  void: '#8b97ad'
};

export const CURRENCIES = {
  USD: { locale: 'en-US', symbol: '$' },
  INR: { locale: 'en-IN', symbol: '₹' },
  EUR: { locale: 'de-DE', symbol: '€' },
  GBP: { locale: 'en-GB', symbol: '£' }
};

export const MODEL_FACTS = {
  type: 'Logistic Regression · Sigmoid Calibrated',
  version: '1.0.0-calibrated',
  rowsScored: 50000,

  rocAuc: 0.81643,
  prAuc: 0.09543,
  brierScore: 0.017266,
  threshold: 0.075,

  precision: 0.1158,
  recall: 0.2240,
  f1: 0.1527,
  topOnePercentLift: 9.84,

  tiers: [
    ['Critical', 'Top 1% by model score percentile'],
    ['High', 'Next 4% (95th to below 99th percentile)'],
    ['Medium', 'Next 15% (80th to below 95th percentile)'],
    ['Monitor', 'Remaining 80%']
  ],

  explainability:
    'Model contributions describe how transformed features influence predictions. They are not causal explanations.',

  importance:
  'Existing permutation-importance results belong to the legacy model. They must be recomputed using the deployed calibrated model before being presented as its feature importance.',

  limitations: [
    'Dataset is synthetic and independent of the primary SaaS billing data.',
    'Priority tiers are relative ranking bands, not calibrated risk categories.',
    'Calibration does not establish production reliability.',
    'Threshold 0.075 was selected on validation data using F1, not business cost.',
    'Feature contributions describe model behaviour, not causation.',
    'Observed segment churn rates are retrospective associations, not causal effects.',
    'The dataset has no defined prediction timestamp, limiting real-world deployment claims.',
    'The model has not undergone temporal or external validation.'
  ]
};
