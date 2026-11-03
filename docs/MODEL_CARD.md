# HORIZON Churn Model Card

## 1. Model identity

| Item | Value |
|---|---|
| Name | Logistic Regression, sigmoid (Platt) calibrated, no `payment_status` |
| Version | `1.0.0-calibrated` |
| Artifact | `models/horizon_churn_logistic_no_payment_status_calibrated.joblib` |
| Built by | `scripts/run_horizon_calibration.py` |
| Library | scikit-learn 1.7.2 (the artifact must be loaded with a compatible version) |
| Target | `is_churned` (916 of 50,000 rows, 1.83%) |
| Data | 50,000-row synthetic B2B churn dataset |
| Status | Exploratory candidate. Not approved for production |

Other model files in `models/`:

| File | What it is | Used by the API |
|---|---|---|
| `churn_model.joblib` | Legacy baseline, **includes `payment_status`**, PR-AUC 0.205 on its own split | No (still used by two analysis scripts) |
| `horizon_churn_logistic_no_payment_status.joblib` | Uncalibrated no-payment-status candidate, threshold 0.83 | No |

## 2. Intended use

Exploratory ranking of customers by relative churn risk, and a demonstration of an end-to-end predictive analytics workflow on synthetic data. Output supports human review only.

Not intended for: automated cancellation, pricing, service denial or any consequential customer decision; claims about real-world churn; use on populations other than the synthetic dataset.

## 3. Features

| Type | Features |
|---|---|
| Numeric (5) | `monthly_recurring_revenue`, `active_seats_used`, `total_seats_allowed`, `support_tickets_30d`, `feature_adoption_rate` (0 to 1) |
| Categorical (6) | `industry`, `country`, `company_size`, `account_manager`, `plan_tier`, `billing_cycle` |
| Excluded | `payment_status` (timing unverified), `churn_risk_score` (provenance unverified), `customer_id`, `company_name`, `signup_date`, `last_active_date` |

Preprocessing: median imputation and standard scaling for numeric features; most-frequent imputation and one-hot encoding (`handle_unknown="ignore"`) for categorical features.

## 4. Training and evaluation design

- Stratified 60/20/20 train, validation and test split, `random_state = 42` (30,000 / 10,000 / 10,000 rows; 183 churned in each of validation and test).
- Base estimator: Logistic Regression, `class_weight="balanced"`, `max_iter=2500`.
- Calibration: `CalibratedClassifierCV`, sigmoid, 5-fold cross-validation on the training partition only.
- Threshold: maximum F1 on the validation partition, giving 0.075.
- The test partition was not used for fitting, calibration or threshold selection.

## 5. Results (test partition, 10,000 customers, 183 churned)

### Probability quality

| Metric | Uncalibrated | Calibrated |
|---|---:|---:|
| ROC-AUC | 0.8167 | 0.8164 |
| PR-AUC (average precision) | 0.0956 | 0.0954 |
| Brier score | 0.1833 | 0.0173 |
| Log loss | 0.5339 | 0.0783 |

Calibration fixes the probability scale (class weighting had inflated it) but does not change ranking, which is why ROC-AUC and PR-AUC are unchanged.

For context: the positive rate is 0.0183, so a no-skill PR-AUC is about 0.018 and the model is roughly 5 times better than chance on that measure. A constant prediction of the base rate has a Brier score of about 0.0180, so the calibrated model's 0.0173 is a skill improvement of roughly 4%.

### At the review threshold 0.075

| Metric | Validation | Test |
|---|---:|---:|
| Precision | 10.3% | 11.6% |
| Recall | 19.7% | 22.4% |
| F1 | 0.135 | 0.153 |
| Customers flagged | 349 | 354 |
| True positives | 36 | 41 |
| False positives | 313 | 313 |
| False negatives | 147 | 142 |

About 9 of every 10 flagged customers did not churn, and about 4 of every 5 churners are missed.

### Ranking lift (test)

| Top slice | Customers | Churned | Observed churn | Lift |
|---|---:|---:|---:|---:|
| 1% | 100 | 18 | 18.0% | 9.8x |
| 5% | 500 | 54 | 10.8% | 5.9x |
| 10% | 1,000 | 85 | 8.5% | 4.6x |
| 20% | 2,000 | 127 | 6.35% | 3.5x |

The model is more useful as a ranker for the top slice than as a yes/no classifier.

### Batch scoring (all 50,000 customers, in-sample)

| Tier | Customers | Avg predicted | Flagged | Observed churned |
|---|---:|---:|---:|---:|
| Critical | 500 | 13.2% | 500 | 68 |
| High | 2,000 | 8.2% | 1,250 | 174 |
| Medium | 7,500 | 4.3% | 0 | 329 |
| Monitor | 40,000 | 0.9% | 0 | 345 |

This table scores the training population, so it is retrospective and optimistic. Use the test table above for performance claims.

## 6. Payment-status decision

With `payment_status` the legacy model reached PR-AUC 0.205 and ROC-AUC 0.858. Without it, comparable models fell to about 0.085 and 0.797. The field is strongly associated with churn (Failed 14.5%, Pending 3.6%, Active 1.1%), but the dataset does not say when it was recorded relative to the churn outcome. The project excludes it until that timing is documented. If it turns out to be a valid pre-outcome signal, the model should be retrained and re-evaluated.

## 7. Limitations

- Synthetic data. Metrics do not show real-world generalization.
- One random split. No cross-validated model comparison, confidence intervals, temporal split or external validation.
- The dataset has no defined prediction date, so "predicting future churn" is not established.
- The threshold maximizes F1, not business value, intervention cost or capacity.
- Calibration is assessed on one holdout with only 183 positives, so probability estimates are noisy.
- No subgroup, fairness, drift or stability analysis.
- Associations are not causes. Coefficients and importances describe the model.
- Priority tiers are rank bands. "Critical" does not mean a given probability.
- `recommended_action` text in the API is a fixed phrase per tier, not a validated intervention.
- Model name, version and threshold are hard-coded constants in the API and scoring script.

## 8. Responsible use

Use scores to prioritize human review. Do not automatically cancel, penalize, reprice or deny service to anyone based on this model. Re-validate on real, time-ordered data before any operational use.

## 9. Reproduce

```powershell
python scripts/run_horizon_calibration.py        # trains, calibrates, saves the model and report
python scripts/run_horizon_batch_scoring.py      # scores 50,000 customers into PostgreSQL
```

Reports: `data/processed/calibration_experiment/calibration_experiment_report.json`, `data/processed/calibrated_customer_scoring/batch_scoring_report.json`.
