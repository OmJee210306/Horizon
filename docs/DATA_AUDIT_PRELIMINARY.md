# HORIZON Data Audit

**Status:** structural and profile audit of the uploaded source files, produced by `scripts/audit_datasets.py`, `validate_data.py` and `run_data_diagnostics.py`. It is not a signed-off data dictionary: several source semantics remain unconfirmed (see section 7). Original files are never modified.

Generated outputs live in `data/processed/` (`dataset_audit.*`, `data_quality_report.*`, `diagnostics/`).

## 1. Source inventory

| File | Structure | Role | Loaded to PostgreSQL |
|---|---|---|---|
| `saas-subscriptions-v1.0.0-analysis.xlsx` | 1 sheet, 85,448 rows, 12 columns | Billing core | Yes, `primary_analytics.invoice_lines` |
| `MP_Synthetics_50000_Rows.csv` | 50,000 rows, 18 columns | Independent churn experiment | Yes, `churn_lab.customer_churn` |
| `churn-benchmarks.json` | 118 records | Industry reference | Yes, `benchmarks.*` |
| `subscription-sample-database-1k-en_GB-v2.json` | 30 tables | Possible API-usage lab | **No** (sensitive fields) |
| `churn-benchmarks.csv` | Flattened copy of the JSON | Duplicate | No. Do not load it |

## 2. Billing workbook

- 85,448 unique invoices, 5,000 accounts, 5,000 subscriptions (one per account), 36 calendar months (2023-01-04 to 2025-12-28).
- No missing values in the 12 columns.
- Status: 80,101 paid, 5,311 open, 36 void. Collected total 27,639,401 source units.
- Open and void invoices have zero paid. Paid invoices are fully paid.
- `amount_due` equals `mrr` on every row. MRR ranges 49 to 2,595, seats 1 to 524.
- Account attributes (`region`, `segment`, `subscription_id`, `plan_name`, `seats`, `mrr`) never change within an account.
- Invoices per account: 3 to 36. Gaps between consecutive invoices: 28 to 31 days.
- Regions EMEA, NA, LATAM, APAC. Segments SMB, mid_market, enterprise. Plans Starter, Growth, Scale, Enterprise.

### What the billing file cannot support

No subscription start or end date, no cancellation flag, no churn label, no upgrade or downgrade history, no marketing spend or acquisition channel, no payment-attempt history, refunds, tax or discounts, and no currency. Do not claim churn, CAC, marketing ROI, price elasticity or expansion MRR from it. A billing-continuity view must not be called customer retention.

## 3. Synthetic churn CSV

- 50,000 rows, 18 columns, 50,000 unique customer IDs, no missing values.
- Target `Is_Churned`: 49,084 not churned, 916 churned (1.832%).
- 59 rows have `Last_Active_Date` before `Signup_Date`. They are flagged but not corrected or removed; the model does not use either date.
- `Churn_Risk_Score`: Low 49,529, Medium 454, High 17. Observed churn differs sharply by category, so it is a proxy or leakage risk. Excluded.
- `Payment_Status`: Active 44,965, Pending 3,006, Failed 2,029. Observed churn 1.14%, 3.63% and 14.49%.
- Seats used never exceed seats allowed. Adoption ranges 30% to 100%. Tickets range 0 to 8. MRR ranges 49 to 8,499.
- Categorical sizes: 8 industries, 8 countries, 6 company-size bands, 3 plan tiers, 2 billing cycles, 5 account managers.

### Payment-status sensitivity study

`run_payment_status_reliability.py` compared models with and without `payment_status` on one 80/20 stratified holdout (10,000 rows, 183 churned, threshold 0.5).

| Model | PR-AUC with | PR-AUC without | ROC-AUC with | ROC-AUC without |
|---|---:|---:|---:|---:|
| Logistic Regression | 0.205 | 0.085 | 0.858 | 0.797 |
| Random Forest | 0.172 | 0.066 | 0.838 | 0.760 |

Removing the field cuts PR-AUC by more than half. This shows heavy predictive dependence; it does **not** prove leakage. The field's timing is the open question.

## 4. Sample database JSON

- 30 tables with unique candidate keys and no orphan references across 32 checked foreign keys.
- Largest tables: `apirequests` 1,000, `billing_invoices` 250, `payments` 240, `activity_log` 100.
- Contains `password_hash`, `token_value`, `apikey_value`, `card_number`, `cvv`, addresses, birth dates and personal names.
- `subscription_analytics` reports a churn rate of 129.1, outside 0 to 100. Do not trust precomputed values.
- 10 support tickets is too few for support-performance claims.

## 5. Benchmarks JSON

- 118 records, 109 distinct industry labels, five churn drivers per record. Licence CC BY 4.0, update dates 2026-03-31 to 2026-05-19.
- Monthly churn 0.8% to 12.4%, annual churn 9.2% to 79.2%, median ARPU 4 to 850 source units.
- CSV and JSON agree on slugs and headline values. JSON is canonical.

## 6. Quality issues raised by `validate_data.py`

| Severity | Source | Check | Detail |
|---|---|---|---|
| WARNING | churn | `last_active_before_signup` | 59 rows |
| REVIEW | churn | `possible_target_leakage` | `Churn_Risk_Score` needs investigation |
| REVIEW | sample_lab | `sensitive_fields` | Token, API-key, card and password fields present |

## 7. Open items

1. Confirm the licence and download metadata of the billing and churn files before any public release.
2. Obtain a source description for `mrr`, `payment_status`, `churn_risk_score` and the timing of `is_churned`.
3. Decide a documented handling rule for the 59 date anomalies.
4. Confirm the currency of billing and MRR amounts.
5. Decide whether `payment_status` may be used once its timing is known.
