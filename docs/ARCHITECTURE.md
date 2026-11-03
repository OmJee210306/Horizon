# HORIZON Architecture

This document describes the system as it is built today. Planned but unbuilt parts are listed at the end.

## 1. System overview

```text
 Source files (kept local, unchanged)
 ├── saas-subscriptions-v1.0.0-analysis.xlsx   (billing, 85,448 rows)
 ├── MP_Synthetics_50000_Rows.csv              (synthetic churn, 50,000 rows)
 ├── churn-benchmarks.json                     (118 benchmark records)
 └── subscription-sample-database-1k-en_GB-v2.json   (NOT loaded; sensitive fields)

            │  scripts/load_data.py  (pandas -> SQLAlchemy -> to_sql)
            ▼
 PostgreSQL database "horizon"
 ├── primary_analytics.invoice_lines          ──► 5 SQL views (sql/analytics.sql)
 ├── churn_lab.customer_churn                 ──► 5 SQL views (sql/analytics.sql)
 ├── churn_lab.churn_* analysis tables        ◄── scripts/load_churn_intelligence.py
 ├── churn_lab.calibrated_customer_scores     ◄── scripts/run_horizon_batch_scoring.py
 └── benchmarks.industry_churn, source_metadata   (loaded, not served)

            │  SQLAlchemy engine (pool 5, overflow 10, pre-ping)
            ▼
 FastAPI  backend/app/main.py   (single module, 18 endpoints)
 ├── reads views and tables above
 └── loads models/horizon_churn_logistic_no_payment_status_calibrated.joblib
            │  JSON over HTTP  (CORS: localhost:5173 and 127.0.0.1:5173)
            ▼
 React + Vite dashboard  frontend/  (Axios, Plotly, HashRouter)
```

Offline modelling runs separately from the API:

```text
 MP_Synthetics_50000_Rows.csv
   └─ scripts/*  (train, reliability study, calibration)
        └─ models/*.joblib  +  data/processed/**  (reports, CSVs)
             └─ run_horizon_batch_scoring.py ─► churn_lab.calibrated_customer_scores
```

## 2. Source isolation rule

Billing and churn data are independent populations. No query, view, script or API endpoint joins them. The Overview endpoint returns them under separate keys (`billing_source`, `independent_churn_source`) with an explicit note. Any future combined KPI requires a verified shared key and a documented population relationship.

## 3. Database layout

Database name (from `.env`): `horizon`.

| Schema | Created by | Contents | Used by API |
|---|---|---|---|
| `primary_analytics` | Manual `CREATE SCHEMA`, then `load_data.py` | `invoice_lines` plus 5 views | Yes |
| `churn_lab` | Manual or `load_churn_intelligence.py` / `run_horizon_batch_scoring.py` (both run `CREATE SCHEMA IF NOT EXISTS`) | `customer_churn`, 5 views, 5 intelligence tables, `calibrated_customer_scores` | Yes |
| `benchmarks` | Manual `CREATE SCHEMA`, then `load_data.py` | `industry_churn`, `source_metadata` | No |
| `sample_lab` | Not created | Reserved name only | No |

### Tables and views

| Object | Type | Source |
|---|---|---|
| `primary_analytics.invoice_lines` | table | Billing workbook |
| `primary_analytics.monthly_billing` | view | `invoice_lines` |
| `primary_analytics.invoice_status_summary` | view | `invoice_lines` |
| `primary_analytics.plan_performance` | view | `invoice_lines` |
| `primary_analytics.regional_performance` | view | `invoice_lines` |
| `primary_analytics.account_billing_summary` | view | `invoice_lines` |
| `churn_lab.customer_churn` | table | Churn CSV |
| `churn_lab.churn_distribution`, `churn_by_industry`, `churn_by_plan`, `churn_by_billing_cycle`, `churn_by_payment_status` | views | `customer_churn` (defined in SQL, not called by the API) |
| `churn_lab.churn_customer_intelligence` | table | Legacy model output (loaded, not called by the API) |
| `churn_lab.churn_priority_tier_summary` | table | Legacy model output (not called by the API) |
| `churn_lab.churn_model_feature_importance` | table | Legacy model permutation importance (served by `/api/churn/features`) |
| `churn_lab.churn_observed_by_segment` | table | Observed churn rates (served by `/api/churn/segments`) |
| `churn_lab.churn_observed_numeric_bands` | table | Observed churn rates (served by `/api/churn/numeric-bands`) |
| `churn_lab.calibrated_customer_scores` | table | Calibrated batch scores (served by customers, summary, batch-model-info endpoints) |
| `benchmarks.industry_churn`, `benchmarks.source_metadata` | tables | Benchmark JSON |

No primary keys, foreign keys or constraints are defined on any table. `to_sql(if_exists="replace")` creates them as plain tables. The only indexes are two created by `load_churn_intelligence.py` on `churn_customer_intelligence`, which the API does not query.

## 4. Offline pipeline

| Stage | Script | Output |
|---|---|---|
| Audit | `audit_datasets.py` | `data/processed/dataset_audit.{json,md}` |
| Validation | `validate_data.py` | `data_quality_report.{json,md}` |
| Diagnostics | `run_data_diagnostics.py` | `data/processed/diagnostics/` |
| Load | `load_data.py` | Billing, churn and benchmark tables |
| Legacy baseline | `train_churn_model.py` | `models/churn_model.joblib` (includes `payment_status`) |
| Threshold study | `analyze_churn_thresholds.py` | `data/processed/churn_model/` |
| Legacy intelligence | `build_churn_intelligence.py`, `load_churn_intelligence.py` | `data/processed/churn_intelligence/`, `churn_lab.churn_*` tables |
| Leakage sensitivity | `run_payment_status_reliability.py` | `data/processed/model_reliability/` |
| Candidate model | `finalize_horizon_churn_model.py` | `models/horizon_churn_logistic_no_payment_status.joblib` |
| **Calibration** | `run_horizon_calibration.py` | `models/horizon_churn_logistic_no_payment_status_calibrated.joblib` |
| **Batch scoring** | `run_horizon_batch_scoring.py` | `calibrated_customer_scores.csv` and the Postgres table |

All scripts resolve paths relative to the project root, read credentials from the root `.env`, and write only to `data/processed/`, `models/` or their own tables.

## 5. Model serving

- The API loads the calibrated pipeline once per process (`functools.lru_cache`) and keeps it in memory. Restart the API after replacing the file.
- The model path, threshold (0.075), name and version (`1.0.0-calibrated`) are **hard-coded constants** in `main.py` and repeated in `run_horizon_batch_scoring.py`.
- `POST /api/churn/predict` accepts exactly the 11 model features, all optional. Missing values are handled by the pipeline's imputers. Unknown fields are rejected (`extra = "forbid"`).
- The response decision is `flag_for_review` when probability is at least 0.075, otherwise `below_review_threshold`.

### Model features

| Type | Features |
|---|---|
| Numeric | `monthly_recurring_revenue`, `active_seats_used`, `total_seats_allowed`, `support_tickets_30d`, `feature_adoption_rate` |
| Categorical | `industry`, `country`, `company_size`, `account_manager`, `plan_tier`, `billing_cycle` |
| Excluded | `payment_status`, `churn_risk_score`, `customer_id`, `company_name`, `signup_date`, `last_active_date` |

Scale note: `feature_adoption_rate` is stored in `churn_lab.customer_churn` as percentage points (44 for "44%"; `load_data.py` only strips the `%` sign). The modelling and batch-scoring scripts convert it to a 0 to 1 proportion, and the prediction API and form expect 0 to 1 (35% is sent as 0.35). Keep the two scales apart when writing new SQL against the table.

## 6. Backend

- **Single file:** `backend/app/main.py` (about 540 lines) holds configuration, models, helpers and all routes.
- **Configuration:** loaded from the project-root `.env`. The app refuses to start if any of the five `DB_*` variables is missing. `APP_ENV`, `APP_NAME`, `API_PREFIX` and `DATABASE_URL` that may appear in `.env` are not read by the code.
- **Data access:** raw SQL strings through `rows()` and `one()` helpers, which convert dates, decimals and NumPy scalars to JSON types. Database errors return HTTP 503 with the driver message.
- **Validation:** Pydantic v2 request model, `Query` constraints for paging (`limit` 1 to 100 or 1 to 200), tier regex `^(Critical|High|Medium|Monitor)$`, score range 0 to 1.
- **CORS:** fixed list of two local origins.
- **Not present:** authentication, rate limiting, logging, request IDs, caching of query results, API tests.

## 7. Frontend

| Concern | Implementation |
|---|---|
| Build | Vite 6 with `@vitejs/plugin-react`, dev server fixed at `127.0.0.1:5173` (`strictPort`) |
| Routing | React Router 6 with `HashRouter` |
| API client | Axios instance, 25 s timeout, interceptor that builds a friendly error message |
| Data hooks | `useApi` (fetch with reload), `useTitle` in `hooks.js` |
| Charts | `react-plotly.js` over `plotly.js-basic-dist-min`, split into its own chunk |
| State | `context.jsx` for theme, currency symbol and formatter helpers |
| Config | `src/config.js` holds API URL, tier colours and **hard-coded model facts** for the Methodology page |

Health polling, command palette (`Ctrl/Cmd + K`), CSV export and the customer drawer are implemented in the components and pages listed in the README.

## 8. Operational notes

- Start order: PostgreSQL, then backend, then frontend.
- `GET /api/health` returns HTTP 503 when the database is down, so a monitor sees a failure rather than a `database: disconnected` body.
- After retraining, copy the new `.joblib` into `models/`, update the constants in `main.py`, rerun `run_horizon_batch_scoring.py`, then restart the API.
- The scripts use `if_exists="replace"`. PostgreSQL refuses `DROP TABLE` when views depend on the table, so rerunning `load_data.py` after `sql/analytics.sql` has been applied will probably fail unless the views are dropped first.
- Saved models depend on scikit-learn 1.7.2. Loading them with another minor version may warn or fail.

## 9. Not built

These appear in `PROJECT_PLAN.md` but have no code: cohort analysis, sample-database lab, benchmark API and UI, statistics module (SciPy and statsmodels are installed but no script imports them), decision simulator, data-quality page, automated tests, CI, deployment configuration.
