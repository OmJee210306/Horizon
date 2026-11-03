# HORIZON Data Dictionary

Describes every table the project creates, the meaning of each column as far as it is known, and the rules for using them. Where the source gives no documentation, the entry says so rather than guessing.

## Independent source rule

The billing and churn datasets are different populations. Similar-looking IDs (`account_id`, `customer_id`) do not authorize a join. Cross-source metrics need a verified shared key and a documented population relationship.

---

## 1. `primary_analytics.invoice_lines` (billing)

Source: `saas-subscriptions-v1.0.0-analysis.xlsx`, one sheet, 85,448 rows, 12 columns. Column names are lower-cased by `load_data.py`.

| Column | Type | Meaning | Notes |
|---|---|---|---|
| `invoice_id` | text | Invoice identifier | Unique per row |
| `invoice_date` | timestamp | Invoice date | 2023-01-04 to 2025-12-28 |
| `invoice_status` | text | `paid`, `open` or `void` | 80,101 paid, 5,311 open, 36 void |
| `account_id` | text | Account within this source | 5,000 distinct |
| `region` | text | EMEA, NA, LATAM, APAC | No missing values found. Any blank would be shown as `Unknown` |
| `segment` | text | SMB, mid_market, enterprise | Constant per account |
| `subscription_id` | text | Subscription identifier | One subscription per account in this extract |
| `plan_name` | text | Starter, Growth, Scale, Enterprise | Constant per account |
| `seats` | numeric | Seats on the record | Range 1 to 524 |
| `mrr` | numeric | Source MRR field | Range 49 to 2,595. Repeated on every monthly invoice row. **Semantics unconfirmed. Do not sum it as company MRR** |
| `amount_due` | numeric | Billed amount | Equals `mrr` on every row |
| `amount_paid` | numeric | Collected amount | Zero for open and void; equal to `amount_due` for paid |

Facts about the extract:

- Total collected: 27,639,401 source units. Open: 1,857,721. Void: 9,652.
- Invoices per account: 3 to 36 (mean about 17.1, median 16). Consecutive invoices are 28 to 31 days apart.
- There is **no currency column**. Do not attach a currency symbol to the numbers.
- There is no cancellation flag, churn label, refund, discount, tax or payment-attempt history.

### Billing views (`sql/analytics.sql`)

| View | Grain | Columns |
|---|---|---|
| `monthly_billing` | Month | `billing_month`, `invoice_count`, `active_accounts_in_invoices`, `total_billed`, `total_collected`, `unpaid_balance`, `paid_invoice_count`, `open_invoice_count`, `void_invoice_count` |
| `invoice_status_summary` | Status | `invoice_status`, `invoice_count`, `total_billed`, `total_collected`, `invoice_percentage` |
| `plan_performance` | Plan | `plan_name`, `invoice_count`, `account_count`, `total_billed`, `total_collected`, `average_seats`, `average_invoice_row_mrr` |
| `regional_performance` | Region | `region`, `invoice_count`, `account_count`, `total_billed`, `total_collected` |
| `account_billing_summary` | Account | `account_id`, `invoice_count`, `subscription_count`, `first_invoice_date`, `latest_invoice_date`, `total_billed`, `total_collected`, `unpaid_balance` |

### Metric definitions

| Metric | Definition | Caveat |
|---|---|---|
| Total billed | `SUM(amount_due)` | Includes void invoices |
| Total collected | `SUM(amount_paid)` | Cash collected, not recognized revenue |
| Unpaid balance | `SUM(amount_due - amount_paid)` | **Includes void invoices** (9,652 of 1,867,373). Open-only balance is 1,857,721 |
| Active accounts in invoices | `COUNT(DISTINCT account_id)` in the period | Means "invoiced", not "retained" |
| Average invoice-row MRR | `AVG(mrr)` over invoice rows | Weighted by invoice count, not a subscription-level MRR |

---

## 2. `churn_lab.customer_churn` (synthetic churn)

Source: `MP_Synthetics_50000_Rows.csv`, 50,000 rows, 18 columns. Column names are converted to snake_case.

| Column | Type | Meaning | Notes |
|---|---|---|---|
| `customer_id` | text | Customer identifier (`CUST-1001` style) | Unique |
| `company_name` | text | Generated company name | Synthetic |
| `industry` | text | Industry label | 8 values: CyberSecurity, DevTools, E-Commerce, EdTech, FinTech, HealthTech, Logistics, MarTech |
| `country` | text | Country | 8 values: Australia, Canada, France, Germany, India, Singapore, UK, USA |
| `company_size` | text | Employee-count band | 6 values: 1-10, 11-50, 51-200, 201-500, 501-1000, 1000+ |
| `account_manager` | text | Account manager name | 5 distinct managers |
| `plan_tier` | text | Plan tier | 3 values: Starter, Pro, Enterprise |
| `billing_cycle` | text | Billing cycle | 2 values: Monthly, Annual |
| `monthly_recurring_revenue` | numeric | Customer MRR | 49 to 8,499 source units. Currency not stated |
| `signup_date` | timestamp | Signup date | 2022-11-17 to 2026-01-29 |
| `last_active_date` | timestamp | Last activity | 2025-09-02 to 2026-02-28. **59 rows are earlier than `signup_date`** |
| `payment_status` | text | Active, Pending or Failed | **Timing relative to the churn outcome unknown** |
| `active_seats_used` | integer | Seats in use | Never exceeds allowed seats in the checks run |
| `total_seats_allowed` | integer | Seat limit | |
| `support_tickets_30d` | integer | Tickets in the last 30 days | 0 to 8 |
| `feature_adoption_rate` | numeric | Feature adoption | Stored as percentage points (44 means 44%). Models use a 0 to 1 proportion |
| `churn_risk_score` | text | Low, Medium or High | **Provenance unknown. Excluded from modelling** |
| `is_churned` | integer | Target, 1 = churned | 916 of 50,000 (1.832%) |

Observed churn by `payment_status`: Active 1.14% (513 of 44,965), Pending 3.63% (109 of 3,006), Failed 14.49% (294 of 2,029).

### Churn views

`churn_distribution`, `churn_by_industry`, `churn_by_plan`, `churn_by_billing_cycle`, `churn_by_payment_status`. Each returns `customer_count`, `churned_customers` and `churn_rate_pct` (or `customer_percentage` for the distribution). They are defined in SQL but no API endpoint calls them.

---

## 3. `churn_lab.calibrated_customer_scores` (derived)

Created by `scripts/run_horizon_batch_scoring.py`. 50,000 rows, one per customer.

| Column | Meaning |
|---|---|
| `customer_id`, `company_name` | Copied from the source |
| `predicted_churn_probability` | Calibrated model output (0 to 1) |
| `actual_is_churned` | Historical label for retrospective review. **Never a model input** |
| `risk_percentile` | Percentile rank of the score within the 50,000 scored customers (0 to 100) |
| `priority_tier` | Critical (top 1%), High (next 4%), Medium (next 15%), Monitor (remaining 80%) |
| `review_threshold` | 0.075 |
| `flag_for_review` | True when the probability is at least 0.075 (1,750 rows) |
| `model_name`, `model_version` | Provenance strings |
| `industry`, `country`, `company_size`, `plan_tier`, `billing_cycle` | Descriptive fields copied from the source |

Tier counts: Critical 500, High 2,000, Medium 7,500, Monitor 40,000. Tiers are rank bands, not probability classes. Every Critical customer and 1,250 High customers are flagged; no Medium or Monitor customer is.

---

## 4. Churn analysis tables (legacy model)

Loaded by `scripts/load_churn_intelligence.py` from `data/processed/churn_intelligence/`. They were produced with the **legacy baseline model** (`churn_model.joblib`, which includes `payment_status`).

| Table | Content | Served by |
|---|---|---|
| `churn_model_feature_importance` | `feature`, `mean_pr_auc_decrease`, `std_pr_auc_decrease` (permutation importance, 5 repeats) | `/api/churn/features` |
| `churn_observed_by_segment` | Observed churn rate per segment value (`dimension`, `segment`, `customer_count`, `churned_customers`, `churn_rate`, `churn_rate_pct`; 35 rows) | `/api/churn/segments` |
| `churn_observed_numeric_bands` | Observed churn rate per numeric band (`dimension`, `band`, counts, `churn_rate`, `churn_rate_pct`; 44 rows) | `/api/churn/numeric-bands` |
| `churn_customer_intelligence` | Per-customer legacy score and tier | Not served |
| `churn_priority_tier_summary` | Legacy tier summary | Not served |

Observed-rate tables describe the data, not a model, so they stay valid. The importance table reflects a model the project no longer deploys.

---

## 5. `benchmarks.*` (reference)

| Table | Content |
|---|---|
| `industry_churn` | 118 records flattened from `churn-benchmarks.json`; nested values stored as JSON strings |
| `source_metadata` | Key and value pairs from the JSON header (licence, provider, update dates) |

Licence: CC BY 4.0. Provider: retentioncheck.com. Reported monthly churn 0.8% to 12.4%, annual churn 9.2% to 79.2%. Treat as contextual reference, not ground truth. These tables are not exposed through the API.

---

## 6. Sample database JSON (not loaded)

`subscription-sample-database-1k-en_GB-v2.json` has 30 tables. It contains credential-like and payment-like fields (`password_hash`, `token_value`, `apikey_value`, `card_number`, `cvv`, personal and address fields). It is intentionally excluded from the database. `subscription_analytics` holds a churn rate of 129.1, which is invalid. Recompute from underlying records if the file is ever used.

---

## 7. Data cautions

- Billing amounts have no verified currency. The dashboard's currency selector changes the symbol only.
- `amount_paid` is collected cash, not recognized revenue.
- `mrr` must not be summed across repeated invoice rows.
- No churn can be derived from the billing workbook.
- The churn dataset has no prediction timestamp, which limits any deployment claim.
- Missing region values are labelled `Unknown`.
- Do not describe synthetic results as real company performance.
