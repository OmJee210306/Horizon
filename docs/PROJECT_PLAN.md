# HORIZON Project Plan and Status

This is the original plan, updated with what has actually been built. Status values: **Done**, **Partial**, **Not started**. A feature counts as done only when the code exists; "tested" is a separate claim and, today, nothing has automated tests.

## 1. Goal

Build an analytics product that goes from source data to business insight and transparent decision support, demonstrating data engineering, SQL, statistics, practical ML, a backend API, a frontend, testing and honest communication of limits.

The business case is a fictional educational SaaS company. All datasets are synthetic or independent sources. Results must never be described as the verified performance of a real company.

## 2. Module status

| Module | Planned output | Status | Where |
|---|---|---|---|
| Data quality and lineage | Source inventory, validation, scorecards | Partial | Audit and validation scripts, reports in `data/processed/`. No UI page, no refresh metadata |
| Executive overview | Billing and churn KPIs | Done | `/api/overview`, Overview page |
| Revenue and billing intelligence | Trends, status, plan, region, account views | Done | 5 SQL views, 5 endpoints, Revenue page |
| Customer and cohort intelligence | Billing cohorts, continuity | Not started | |
| Churn prediction lab | Model comparison, probabilities, thresholds, importance | Done | Scripts, calibrated model, Churn page |
| Product and API usage lab | Sample-database analysis | Not started | Source deliberately not loaded |
| Industry benchmarking | Benchmark ranges and drivers | Partial | Data loaded to `benchmarks.*`. No API, no UI |
| Statistical intelligence | Hypothesis tests, regression | Not started | No script uses SciPy or statsmodels |
| Business decision simulator | What-if scenarios | Not started | |

### Metric guardrails (still in force)

- The billing workbook has no churn or cancellation history. Never call an inferred last invoice a confirmed churn.
- Billing cohorts, if built, are billing-continuity views, not retention.
- `amount_paid` is collected cash, not recognized revenue.
- `mrr` repeats on every monthly invoice row. Do not sum it across history.
- No acquisition spend exists, so CAC and marketing ROI are unavailable.
- No price-change data exists. Elasticity can only be a labelled scenario assumption.
- Historical paid amount per account is not customer lifetime value.
- Benchmarks are context, not ground truth.

## 3. Data architecture (as built)

One PostgreSQL database `horizon` with isolated schemas: `primary_analytics`, `churn_lab`, `benchmarks`. The first plan named them `horizon_db`, `raw_primary`, `analytics`, `raw_churn`, `ml_churn`, `sample_lab` and `reference_data`; that layout was not adopted (see decision D-018). There is no separate raw layer: the loader writes cleaned tables directly and keeps the original files on disk. See [ARCHITECTURE.md](ARCHITECTURE.md).

## 4. Technology

Python, pandas, NumPy, scikit-learn, SQLAlchemy, psycopg2, FastAPI, Pydantic, PostgreSQL, React, Vite, Axios, Plotly.js, Git. SciPy and statsmodels are installed but unused. No Docker or notebooks by decision D-011.

## 5. Phases

### Phase 0. Foundation: Done
Folder structure, virtual environment, `.env` handling, `.gitignore`. The uploaded copy contains no `.git` folder, so repository history could not be checked.

### Phase 1. Dataset audit and data dictionary: Mostly done
- Done: source inventory, profiling, validation checks, diagnostics, quality reports, data dictionary.
- Open: confirm licences and download metadata, source definitions for `mrr`, `payment_status`, `churn_risk_score`, currency, and a rule for the 59 date anomalies.

### Phase 2. Data engineering and PostgreSQL: Partial
- Done: repeatable loader with row-count verification, source-isolated schemas, raw files left untouched.
- Missing: schema DDL, primary keys and constraints, indexes on served tables, SQL data-quality checks, reconciliation tests, a one-command pipeline, a safe re-run path (replacing tables fails once views depend on them).

### Phase 3. SQL and core analytics: Partial
- Done: 10 analytics views (5 billing, 5 churn).
- Missing: cohort continuity, benchmark comparison views, sample-lab summaries, independent recomputation of the KPIs. The unpaid-balance definition needs a decision (D-027).

### Phase 4. Statistical and predictive analytics: Partial
- Done: leakage review (`payment_status`, `churn_risk_score`), Logistic Regression and Random Forest comparison, PR-AUC based selection, stratified splits, threshold analysis, permutation importance, sigmoid calibration, lift tables.
- Missing: majority-class baseline report, Decision Tree comparison, hypothesis tests and regression, temporal evaluation, subgroup and stability checks, cross-validated comparison.

### Phase 5. FastAPI backend: Partial
- Done: 18 endpoints, request validation, paging limits, error handling, model caching.
- Missing: API tests, authentication, logging, planned endpoint groups (`billing`, `accounts`, `cohorts`, `benchmarks`, `sample-lab`, `statistics`, `simulator`, `data-quality`), splitting `main.py` into routers.

### Phase 6. React frontend: Partial
- Done: 5 pages, theme, navigation, loading, error and empty states, customer explorer, prediction form, CSV export.
- Missing: benchmark, statistics, simulator, cohort and data-quality pages, frontend tests, accessibility review.
- Needs correction: Methodology page facts describe the legacy model.

### Phase 7. Decision simulator: Not started

### Phase 8. Testing, deployment, packaging: Not started
- A manual checklist exists ([FINAL_TEST_CHECKLIST.md](FINAL_TEST_CHECKLIST.md)) but no item has been recorded as run.
- Missing: automated tests, CI, deployment, screenshots, licence file, interview walkthrough.

## 6. Suggested next steps

In priority order:

1. Fix `backend/requirements.txt` and add `.env.example` (minutes).
2. Update the Methodology page and `config.js` to the calibrated model, and decide what to do with the legacy importance chart (D-025).
3. Decide and fix the unpaid-balance definition (D-027).
4. Add schema DDL and a single `run_pipeline` script so a fresh clone can reach a working app.
5. Add API tests (health, one revenue endpoint, customers paging, predict validation and rejection of `payment_status`).
6. Run the manual checklist and record screenshots.
7. Decide which unbuilt modules are in scope and remove the rest from the plan (D-028).
8. Add CI and a deployment target.

## 7. Definition of done

HORIZON is complete when: provenance and quality are documented, source boundaries are enforced, metrics reconcile, ML leakage and imbalance are addressed, APIs and UI are tested, documentation matches the code, and the app runs from a clean checkout or is deployed. Resume or portfolio statements must be limited to implemented and tested features.
