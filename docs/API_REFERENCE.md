# HORIZON API Reference

Base URL (local): `http://127.0.0.1:8000`. Interactive docs: `/docs`. API version `1.1.0`.

All responses are JSON. Dates are ISO strings, `Decimal` values are floats. There is no authentication. Database failures return HTTP 503 with the driver message in `detail`.

## System

| Method | Path | Description |
|---|---|---|
| GET | `/` | Name, version and docs path |
| GET | `/api/health` | Runs `SELECT 1`. Returns `{status, database, churn_model}` where `churn_model` is `available` or `not_found`. Returns 503 if the database is unreachable |
| GET | `/api/metadata/sources` | Three source descriptions (billing, churn, benchmarks) and the governance note |

## Overview

### `GET /api/overview`

Two independent KPI blocks plus a source note.

| Key | Fields |
|---|---|
| `billing_source` | `invoice_rows`, `accounts_in_invoice_data`, `total_billed`, `total_collected`, `unpaid_balance`, `first_invoice_date`, `latest_invoice_date` |
| `independent_churn_source` | `customers`, `churned_customers`, `observed_churn_rate_pct` |
| `source_note` | Reminder that the two blocks are separate populations |

`unpaid_balance` is `SUM(amount_due - amount_paid)` over all invoices, so it includes void invoices. See [KNOWN_GAPS](KNOWN_GAPS.md).

## Revenue

Source schema: `primary_analytics`. Amounts are in source units with no confirmed currency.

| Method | Path | Backing view | Notes |
|---|---|---|---|
| GET | `/api/revenue/monthly` | `monthly_billing` | Ordered by `billing_month`. Invoice counts by status, billed, collected, unpaid |
| GET | `/api/revenue/regions` | `regional_performance` | Ordered by `total_billed` desc. Missing region shown as `Unknown` |
| GET | `/api/revenue/plans` | `plan_performance` | Ordered by `total_billed` desc. Includes `average_invoice_row_mrr` |
| GET | `/api/revenue/invoice-status` | `invoice_status_summary` | One row each for paid, open, void |
| GET | `/api/revenue/accounts` | `account_billing_summary` | Ordered by `total_billed` desc |

`/api/revenue/accounts` parameters:

| Param | Type | Default | Constraint |
|---|---|---|---|
| `limit` | int | 20 | 1 to 100 |
| `offset` | int | 0 | at least 0 |

## Churn analytics

| Method | Path | Source | Description |
|---|---|---|---|
| GET | `/api/churn/summary` | `customer_churn`, `calibrated_customer_scores` | `distribution` (churned vs not), `priority_tiers` (count, average probability, flagged, observed churned) and `model_note` |
| GET | `/api/churn/features` | `churn_model_feature_importance` | Permutation importance, ordered by `mean_pr_auc_decrease`. **Comes from the legacy model that includes `payment_status`** |
| GET | `/api/churn/segments` | `churn_observed_by_segment` | Observed churn rate by segment. Optional `dimension` filter (max 80 chars) |
| GET | `/api/churn/numeric-bands` | `churn_observed_numeric_bands` | Observed churn rate by numeric band. Optional `dimension` filter |
| GET | `/api/churn/batch-model-info` | `calibrated_customer_scores` | `customers_scored`, `flagged_for_review`, `model_name`, `model_version`, `review_threshold`, `highest_score`, `lowest_score` |

### `GET /api/churn/customers`

Customer explorer, ordered by predicted probability descending.

| Param | Type | Default | Constraint |
|---|---|---|---|
| `tier` | string | none | `Critical`, `High`, `Medium` or `Monitor` |
| `search` | string | none | Max 100 chars. Case-insensitive match on `customer_id` or `company_name` |
| `min_score` | float | none | 0 to 1 |
| `limit` | int | 50 | 1 to 200 |
| `offset` | int | 0 | at least 0 |

Each row: `customer_id`, `company_name`, `predicted_churn_probability`, `risk_percentile`, `priority_tier`, `flag_for_review`, `review_threshold`, `model_name`, `model_version`, `industry`, `country`, `company_size`, `plan_tier`, `billing_cycle`, `recommended_action`, `top_model_contributors` (always `null`), `actual_is_churned`.

`recommended_action` is a fixed text per tier, not a model output. `actual_is_churned` is the historical label, included for retrospective review only.

### `GET /api/churn/customers/count`

Returns `{total}`. Optional `tier` filter. It does not accept `search` or `min_score`, so the total shown next to a searched list can differ from the number of matching rows.

## Prediction

### `GET /api/churn/model-info`

Static description: availability of the model file, name, version, threshold (0.075), calibration method, excluded features and a note.

### `POST /api/churn/predict`

Scores one customer with the calibrated model. Every field is optional; missing values are imputed by the pipeline. Any other field (for example `payment_status`) is rejected with HTTP 422.

| Field | Type | Constraint |
|---|---|---|
| `monthly_recurring_revenue` | float | at least 0 |
| `active_seats_used` | int | at least 0 |
| `total_seats_allowed` | int | at least 0 |
| `support_tickets_30d` | int | at least 0 |
| `feature_adoption_rate` | float | 0 to 1 (a proportion, so 35% is 0.35) |
| `industry` | string | max 100 |
| `country` | string | max 100 |
| `company_size` | string | max 100 |
| `account_manager` | string | max 150 |
| `plan_tier` | string | max 100 |
| `billing_cycle` | string | max 100 |

Example request:

```json
{
  "monthly_recurring_revenue": 499,
  "active_seats_used": 13,
  "total_seats_allowed": 24,
  "support_tickets_30d": 3,
  "feature_adoption_rate": 0.58,
  "industry": "CyberSecurity",
  "country": "USA",
  "company_size": "51-200",
  "plan_tier": "Pro",
  "billing_cycle": "Annual"
}
```

Response:

| Field | Meaning |
|---|---|
| `predicted_churn_probability` | Calibrated probability, 6 decimals |
| `predicted_churn_probability_pct` | Same value as a percentage |
| `threshold` | 0.075 |
| `decision` | `flag_for_review` or `below_review_threshold` |
| `model_name`, `model_version` | Hard-coded constants |
| `missing_features` | Names of fields sent as null or omitted |
| `note` | Synthetic-data caution |

Errors: 503 if the model file is missing or unreadable, 422 if scoring fails (for example an unseen category is handled by the encoder, but a malformed value is not).

## Not available

There are no endpoints for benchmarks, the sample database, cohorts, statistics, scenario simulation, model retraining or batch scoring. Batch scoring is a script, not an API call.
