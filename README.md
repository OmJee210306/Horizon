# HORIZON

**Subscription billing analytics and a calibrated churn-risk scoring workflow, served through a FastAPI backend and a React dashboard.**

HORIZON takes two independent datasets, a SaaS invoice workbook and a synthetic B2B churn file, loads them into PostgreSQL, builds SQL analytics views, trains and calibrates a churn model, batch-scores 50,000 customers, and exposes everything through a REST API and a Plotly dashboard.

> **Data boundary.** The billing workbook and the churn dataset are separate sources. HORIZON never joins their customer records and never claims they describe the same company.
>
> **Synthetic data.** The churn dataset is synthetic. Model metrics here say nothing about production performance.

---

## Contents

- [What it does](#what-it-does)
- [Status at a glance](#status-at-a-glance)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Quick start](#quick-start)
- [Pipeline run order](#pipeline-run-order)
- [Dashboard pages](#dashboard-pages)
- [API overview](#api-overview)
- [Model summary](#model-summary)
- [Known shortcomings](#known-shortcomings)
- [Documentation index](#documentation-index)
- [Security and publishing](#security-and-publishing)

---

## What it does

| Area | What is built |
|---|---|
| **Billing analytics** | 85,448 invoices (Jan 2023 to Dec 2025, 5,000 accounts) loaded to PostgreSQL. Five SQL views: monthly billing, invoice status, plan, region, account. |
| **Churn analysis** | Observed churn by segment and numeric band, permutation importance, payment-status sensitivity study. |
| **Churn model** | Logistic Regression with sigmoid (Platt) calibration, trained **without** `payment_status` and `churn_risk_score`. |
| **Batch scoring** | 50,000 customers scored into `churn_lab.calibrated_customer_scores` with risk percentile, priority tier and a review flag. |
| **Single prediction** | `POST /api/churn/predict` scores one customer; unsupported fields are rejected. |
| **Dashboard** | React + Vite + Plotly. Five pages, light and dark theme, command palette, server-side pagination, CSV export. |

## Status at a glance

| Component | Status |
|---|---|
| Data audit, validation, diagnostics scripts | Implemented |
| PostgreSQL loading (billing, churn, benchmarks) | Implemented, manual schema setup required |
| SQL analytics views (10 views) | Implemented |
| Churn modelling, calibration, batch scoring | Implemented |
| FastAPI backend (18 endpoints) | Implemented, **no automated tests** |
| React dashboard (5 pages) | Implemented, **no automated tests** |
| Benchmark data | Loaded into the database, **not exposed in the API or UI** |
| Sample-database lab, cohorts, statistics module, decision simulator | **Not built** (planned only) |
| Automated tests, CI, deployment | **Not built** |

The full list of gaps is in [docs/KNOWN_GAPS.md](docs/KNOWN_GAPS.md).

## Tech stack

- **Backend:** Python 3.10, FastAPI, Pydantic v2, SQLAlchemy 2, psycopg2
- **Data and ML:** pandas, NumPy, scikit-learn 1.7.2, joblib, openpyxl (SciPy and statsmodels are installed in the environment but no script uses them yet)
- **Database:** PostgreSQL
- **Frontend:** React 18, Vite 6, React Router 6 (hash routing), Axios, Plotly.js (basic bundle), lucide-react

## Project structure

```text
Horizon/
├── backend/
│   ├── app/main.py              # FastAPI app: all endpoints, model loading, DB access
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/               # Overview, Revenue, Churn, Sources, Methodology
│   │   ├── components/          # ui, Chart, CustomerDrawer, CommandPalette
│   │   ├── api.js  config.js  hooks.js  format.js  context.jsx  nav.js
│   └── package.json
├── scripts/                     # Audit, ETL, modelling, calibration, scoring
├── sql/analytics.sql            # Analytics views (primary_analytics, churn_lab)
├── models/                      # Serialized scikit-learn pipelines (.joblib)
├── data/
│   ├── raw/                     # Source files (primary, churn, benchmarks, sample_lab)
│   └── processed/               # Generated reports and score files
├── docs/                        # Architecture, data dictionary, model card, etc.
├── tests/                       # Empty (README only)
├── .env                         # Local secrets (never commit)
└── .gitignore
```

## Quick start

Commands below are for Windows PowerShell. Adjust paths on macOS or Linux.

### 1. Python environment

```powershell
cd D:\Horizon
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

Scripts need more packages than the API does. If `backend\requirements.txt` has not been updated yet (see [KNOWN_GAPS](docs/KNOWN_GAPS.md)), also run:

```powershell
python -m pip install pandas numpy scikit-learn==1.7.2 joblib openpyxl
```

The saved model files were written with scikit-learn 1.7.2. Use the same version to load them.

### 2. Environment variables

Copy `.env.example` to `.env` in the project root and fill in your local values:

```dotenv
DB_HOST=localhost
DB_PORT=5432
DB_NAME=horizon
DB_USER=postgres
DB_PASSWORD=change_me
```

### 3. Database

Create the database and schemas once. The loader scripts do not create `primary_analytics` or `benchmarks`.

```sql
CREATE DATABASE horizon;
\c horizon
CREATE SCHEMA IF NOT EXISTS primary_analytics;
CREATE SCHEMA IF NOT EXISTS churn_lab;
CREATE SCHEMA IF NOT EXISTS benchmarks;
```

Place the source files exactly as described in [data/README.md](data/README.md), then follow the [pipeline run order](#pipeline-run-order).

### 4. Start the backend

```powershell
cd D:\Horizon
python -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

- Health check: http://127.0.0.1:8000/api/health
- Interactive docs: http://127.0.0.1:8000/docs

### 5. Start the frontend

```powershell
cd D:\Horizon\frontend
npm ci
npm run dev
```

Open http://127.0.0.1:5173. The port is fixed because the API's CORS list allows only `localhost:5173` and `127.0.0.1:5173`.

## Pipeline run order

Run from the project root with the virtual environment active.

| Step | Command | Result |
|---|---|---|
| 1 | `python scripts/audit_datasets.py` | Source audit in `data/processed/dataset_audit.*` |
| 2 | `python scripts/validate_data.py` | `data_quality_report.*` |
| 3 | `python scripts/run_data_diagnostics.py` | `data/processed/diagnostics/` |
| 4 | `python scripts/load_data.py` | Loads `primary_analytics.invoice_lines`, `churn_lab.customer_churn`, `benchmarks.industry_churn`, `benchmarks.source_metadata` |
| 5 | Run `sql/analytics.sql` in psql | Creates the 10 analytics views |
| 6 | `python scripts/train_churn_model.py` | Legacy baseline model `models/churn_model.joblib` (uses `payment_status`) |
| 7 | `python scripts/analyze_churn_thresholds.py` | Threshold analysis for the legacy model |
| 8 | `python scripts/build_churn_intelligence.py` | Importance, segment and band CSVs in `data/processed/churn_intelligence/` |
| 9 | `python scripts/load_churn_intelligence.py` | Loads the `churn_lab.churn_*` tables the API reads |
| 10 | `python scripts/run_payment_status_reliability.py` | With and without `payment_status` comparison |
| 11 | `python scripts/finalize_horizon_churn_model.py` | Uncalibrated no-payment-status candidate |
| 12 | `python scripts/run_horizon_calibration.py` | **Calibrated model** `models/horizon_churn_logistic_no_payment_status_calibrated.joblib` |
| 13 | `python scripts/run_horizon_batch_scoring.py` | `churn_lab.calibrated_customer_scores` (50,000 rows) |

Steps 6 to 9 produce the legacy analysis tables that some dashboard charts still read. See [KNOWN_GAPS](docs/KNOWN_GAPS.md) for the inconsistency this causes.

## Dashboard pages

| Route | Contents |
|---|---|
| `/` Overview | Billing and churn KPIs, trend, tier distribution |
| `/revenue` Revenue Analytics | Monthly billing and collections, regions, plans, invoice status, top accounts (paged) |
| `/churn` Churn Intelligence | Risk overview, segment and numeric-band explorer, customer explorer with detail drawer and CSV export, single-customer prediction form |
| `/sources` Data Sources | Source cards, live API and database health |
| `/methodology` Methodology | Model facts, tier definitions, limitations |

Other features: light and dark theme, collapsible sidebar, `Ctrl/Cmd + K` command palette, display-only currency symbol selector, debounced search, skeleton loaders and error states.

## API overview

Base URL `http://127.0.0.1:8000`. Full reference: [docs/API_REFERENCE.md](docs/API_REFERENCE.md).

| Group | Endpoints |
|---|---|
| System | `GET /`, `GET /api/health`, `GET /api/metadata/sources` |
| Overview | `GET /api/overview` |
| Revenue | `/api/revenue/monthly`, `/regions`, `/plans`, `/invoice-status`, `/accounts` |
| Churn analytics | `/api/churn/summary`, `/features`, `/segments`, `/numeric-bands`, `/customers`, `/customers/count`, `/batch-model-info` |
| Prediction | `POST /api/churn/predict`, `GET /api/churn/model-info` |

## Model summary

| Item | Value |
|---|---|
| Algorithm | Logistic Regression, sigmoid calibration (5-fold CV on training data) |
| Version | `1.0.0-calibrated` |
| Features | 5 numeric, 6 categorical. Excludes `payment_status`, `churn_risk_score`, IDs, names, dates |
| Split | Stratified 60/20/20, `random_state=42` |
| Test ROC-AUC | 0.816 |
| Test PR-AUC | 0.095 (positive rate is 1.83%) |
| Test Brier score | 0.0173 |
| Review threshold | 0.075 (max F1 on validation) |
| At threshold (test) | Precision 11.6%, recall 22.4%, F1 0.153 |
| Top 1% lift (test) | 9.8x |

Priority tiers are **relative rank bands**: Critical is the top 1%, High the next 4%, Medium the next 15%, Monitor the remaining 80%. At threshold 0.075 the batch run flags 1,750 customers.

This is a ranking aid for exploration. It is not approved for automated customer decisions. See [docs/MODEL_CARD.md](docs/MODEL_CARD.md).

## Known shortcomings

The most important ones. Details and suggested fixes are in [docs/KNOWN_GAPS.md](docs/KNOWN_GAPS.md).

1. **No automated tests.** `tests/` contains only a README, and every item in the final checklist is unchecked.
2. **Backend `requirements.txt` is incomplete.** `main.py` imports pandas and joblib and loads a scikit-learn pipeline, but none of these are listed.
3. **Dashboard and model disagree.** The Methodology page states PR-AUC 0.205 and "not calibrated". Those are the legacy model's facts. The deployed model has PR-AUC 0.095 and is calibrated. The feature-importance chart also comes from the legacy model that includes `payment_status`.
4. **Setup is not reproducible from the repo alone.** There is no schema DDL, no `.env.example`, and re-running `load_data.py` after the views exist can fail.
5. **The "unpaid balance" metric includes void invoices** (9,652 units out of 1,867,373).
6. **The model is weak in absolute terms.** Precision at the review threshold is 11.6%, and there is no temporal or external validation.
7. **Planned modules were never built:** cohorts, sample-database lab, benchmark views, statistics module, decision simulator, deployment.
8. **No authentication** on an API that returns customer-level names and IDs.

## Documentation index

| File | Purpose |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, schemas, data flow, model serving |
| [docs/API_REFERENCE.md](docs/API_REFERENCE.md) | Every endpoint with parameters and response notes |
| [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md) | Tables, columns, source boundaries, metric definitions |
| [docs/DATA_AUDIT_PRELIMINARY.md](docs/DATA_AUDIT_PRELIMINARY.md) | Findings from the source-file audit |
| [docs/MODEL_CARD.md](docs/MODEL_CARD.md) | Model design, results, limitations, responsible use |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Decision log |
| [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md) | Roadmap with built and not-built status |
| [docs/FINAL_TEST_CHECKLIST.md](docs/FINAL_TEST_CHECKLIST.md) | Manual verification checklist |
| [docs/KNOWN_GAPS.md](docs/KNOWN_GAPS.md) | What is missing, wrong or risky, with priorities |

## Security and publishing

- Never commit `.env`, raw data, database dumps or credentials. If a real password was ever stored in `.env` and the folder was shared or zipped, rotate it.
- Do not commit `.venv/`, `node_modules/`, `frontend/dist/` or `__pycache__/`.
- The sample-database JSON contains credential-like and payment-like fields (`password_hash`, `token_value`, `apikey_value`, `card_number`, `cvv`). It is excluded from loading. Do not expose those fields.
- Generated customer-level files (`calibrated_customer_scores.csv` and similar) are derived from the dataset. Review them before publishing.
- For a public portfolio repository, use synthetic data only and verify the licence of each source.
