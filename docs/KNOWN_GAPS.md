# HORIZON Known Gaps and Shortcomings

What is missing, inconsistent or risky in the project today, found by reading the code, SQL, reports and docs. Each item has a priority, the evidence, and a suggested fix.

**Priority:** P1 = fix before sharing or calling the project complete. P2 = should fix. P3 = nice to have.

## Summary

| # | Gap | Area | Priority |
|---|---|---|---|
| 1 | No automated tests | Quality | P1 |
| 2 | `backend/requirements.txt` is incomplete | Setup | P1 |
| 3 | Dashboard facts and importance chart describe the legacy model | Consistency | P1 |
| 4 | Setup is not reproducible from the repo | Setup | P1 |
| 5 | Secrets and environment folders in the shared copy | Security | P1 |
| 6 | "Unpaid balance" includes void invoices | Metrics | P1 |
| 7 | Model performance is weak and lightly validated | ML | P2 |
| 8 | Planned modules were never built | Scope | P2 |
| 9 | API has no authentication and exposes customer-level data | Security | P2 |
| 10 | API code quality issues | Backend | P2 |
| 11 | Database has no constraints, few indexes, fragile reload | Data | P2 |
| 12 | Frontend gaps | Frontend | P2 |
| 13 | No CI, deployment, logging or monitoring | Ops | P2 |
| 14 | Data questions still unanswered | Data | P2 |
| 15 | Smaller items | Various | P3 |

---

## P1

### 1. No automated tests
**Evidence:** `tests/` holds only a README. No test file exists for the API, SQL, scripts or frontend. Every item in `FINAL_TEST_CHECKLIST.md` is unchecked.
**Risk:** Nothing protects the metrics or the model contract. The README can only describe the project as implemented, not tested.
**Fix:** Add `pytest` with FastAPI `TestClient`. Start with: health, `/api/overview` shape, `/api/revenue/accounts` limit validation, `/api/churn/customers` tier validation, `POST /api/churn/predict` happy path, rejection of `payment_status`, rejection of adoption above 1. Add a data test that checks the expected row counts and tier counts. Later add frontend tests with Vitest.

### 2. `backend/requirements.txt` is incomplete
**Evidence:** The file lists fastapi, uvicorn, sqlalchemy, psycopg2-binary, python-dotenv. `main.py` imports `pandas` and `joblib`, and unpickling the model needs `scikit-learn` and `numpy`. The environment that produced the project had pandas 2.3.3, numpy 2.2.6, joblib 1.6.0 and scikit-learn 1.7.2, and the model files record scikit-learn 1.7.2.
**Risk:** A fresh install fails when the API starts or when the first prediction loads the model.
**Fix:** Replace the file with `backend/requirements.txt` from this package, and add a root `requirements.txt` (or `requirements-dev.txt`) for the scripts (`openpyxl`, plus the same ML packages).

### 3. Dashboard facts and importance chart describe the legacy model
**Evidence:**
- `frontend/src/config.js` (`MODEL_FACTS`) says PR-AUC 0.205 and the limitation list says "Model scores are not calibrated probabilities". The deployed model is calibrated and has PR-AUC 0.095.
- `/api/churn/features` reads `churn_lab.churn_model_feature_importance`, built by `build_churn_intelligence.py` from `models/churn_model.joblib`, which **includes `payment_status`** (it ranks first, importance 0.150). The deployed model excludes that field.
- `churn_lab.churn_customer_intelligence` and `churn_priority_tier_summary` (legacy scores) are loaded but not used.
**Risk:** The Methodology page and one chart contradict the model that produces the scores. A reviewer would notice.
**Fix:** Decide D-025. Preferably regenerate importance and band tables from the calibrated model, update `MODEL_FACTS` (ideally by reading `/api/churn/model-info` instead of hard-coding), and remove or clearly label the legacy artifacts.

### 4. Setup is not reproducible from the repo alone
**Evidence:**
- No schema DDL. `load_data.py` writes into `primary_analytics` and `benchmarks` with `to_sql`, which does not create schemas.
- No `.env.example`, although the frontend README tells you to copy one.
- No single command or documented order for the 13 scripts (the README now lists the order).
- `to_sql(if_exists="replace")` drops and recreates tables. PostgreSQL rejects `DROP TABLE` while views depend on it, so re-running `load_data.py` after `sql/analytics.sql` will probably fail. (Not tested here, no database was available.)
- `data/raw/` is gitignored, so a clone has no data and the scripts fail with file-not-found until the four source files are supplied.
**Fix:** Add `sql/00_schemas.sql` (the three `CREATE SCHEMA` lines), `.env.example`, a `scripts/run_pipeline.py` or `Makefile`, and change the loader to truncate and reload (or drop views first). Document where to download each source file.

### 5. Secrets and environment folders in the shared copy
**Evidence:** The uploaded zip contains `.env` (database credentials, plus unused `DATABASE_URL`, `APP_ENV`, `APP_NAME`, `API_PREFIX`), a Windows `.venv/`, `frontend/dist/`, `__pycache__/` folders, the model `.joblib` files and the raw data. `.gitignore` covers these for Git, but a zip bypasses Git.
**Risk:** Anyone who receives the zip gets the credentials. The `.venv` is not portable.
**Fix:** Rotate the database password if the zip left your machine. Share by Git, or zip with `git archive`. Remove the unused variables from `.env`.

### 6. "Unpaid balance" includes void invoices
**Evidence:** `sql/analytics.sql` (`monthly_billing`, `account_billing_summary`) and `/api/overview` compute `SUM(amount_due - amount_paid)` over every invoice. Void invoices have `amount_due > 0` and `amount_paid = 0`. In the data: open 1,857,721 and void 9,652, so the reported unpaid figure is 1,867,373, about 0.5% too high. A void invoice is cancelled, not owed.
**Fix:** Count only open invoices:
```sql
SUM(CASE WHEN invoice_status = 'open' THEN amount_due - amount_paid ELSE 0 END) AS unpaid_balance
```
Apply to both views and the overview query, or rename the metric. Total billed also includes void invoices; consider excluding them there too and state the rule (D-027).

---

## P2

### 7. Model performance is weak and lightly validated
**Evidence (test partition):** PR-AUC 0.095 (positive rate 0.018), precision 11.6% and recall 22.4% at the review threshold, calibrated Brier 0.0173 against a no-skill 0.0180. Ranking is useful at the top (top 1% lift 9.8x).
**Gaps:**
- One random split and 183 positives, no confidence intervals, no cross-validated comparison.
- No temporal or external validation, and the data has no prediction date.
- Threshold maximizes F1, not cost or capacity. No cost-benefit analysis.
- `payment_status` is excluded on caution; it more than doubles PR-AUC. The question is open (D-026).
- No Decision Tree comparison, no explicit majority-class baseline model, no subgroup or fairness check, no drift monitoring.
- Several overlapping scripts produce three model files with different splits (80/20 and 60/20/20) and thresholds (0.5, 0.83, 0.075), which is easy to misread.
- 59 date anomalies are noted but have no handling rule.
**Fix:** Add bootstrap intervals on test metrics, repeated stratified CV, a cost-based threshold, and a short comparison table of the three models. Archive superseded scripts.

### 8. Planned modules were never built
Not started: cohort and billing-continuity analysis, sample-database usage lab, statistics module (hypothesis tests and regression; SciPy and statsmodels are installed but unused), decision simulator, data-quality page, tests, deployment. Partial: benchmarks (loaded into the database, no API or UI), data lineage and refresh metadata.
**Fix:** Pick the modules that are in scope (D-028) and delete the rest from the plan, or build them. A benchmark endpoint and page is the cheapest because the data is already loaded.

### 9. API has no authentication and exposes customer-level data
**Evidence:** `/api/churn/customers` returns customer IDs and company names with scores and the historical churn label. No auth, rate limit or audit log. CORS allows two local origins only.
**Risk:** Fine for a local demo, unsafe if deployed as is, even with synthetic data.
**Fix:** Add an API key or OAuth layer, rate limiting, and read the allowed origins from configuration.

### 10. API code quality issues
Evidence in `backend/app/main.py`:
- Single 540-line module; no routers, no service layer, no settings class.
- Pydantic v1 style (`class Config`, `.dict()`) and `@app.on_event("shutdown")` are deprecated in current FastAPI and Pydantic. Use `model_config`, `.model_dump()` and a lifespan handler.
- Model name, version, threshold and path are hard-coded and duplicated in `run_horizon_batch_scoring.py`.
- `top_model_contributors` is always `NULL` in `/api/churn/customers`, although the customer drawer exists to show it.
- `recommended_action` is fixed text per tier, not model output.
- `/api/churn/customers` sorts by probability only, so ties can reorder between pages. Add `customer_id` as a tiebreaker.
- `/api/churn/customers/count` ignores `search` and `min_score`, so the total can disagree with the list.
- Database error text (`exc.orig`) is returned to the client.
- `/api/health` raises 503 instead of reporting `database: disconnected`.
- No logging, no query timeouts, no response caching.
- `lru_cache` makes model loading sticky: a failed load is retried, but a replaced file needs a restart.

### 11. Database has no constraints, few indexes and a fragile reload path
**Evidence:** All tables come from `pandas.to_sql` with no primary keys, types beyond pandas defaults, or constraints. The only indexes are on `churn_customer_intelligence`, which the API does not query. `calibrated_customer_scores` has no index although it is filtered by tier, searched by `ILIKE '%...%'` and sorted by probability. Fine at 50,000 rows, slow at scale.
**Fix:** Add DDL with primary keys (`invoice_id`, `customer_id`), CHECK constraints (status values, probability range), and indexes on `(priority_tier, predicted_churn_probability DESC)`. Add a `pg_trgm` index if search matters.

### 12. Frontend gaps
- No tests, no ESLint config, no TypeScript or prop validation. One `eslint-disable` comment is present.
- `config.js` hard-codes model facts, and `Sources.jsx` hard-codes the benchmark count (118), licence and origin. These drift from the backend.
- The currency selector offers USD, INR, EUR and GBP symbols although the source currency is unknown. It is labelled display-only, but a symbol still reads as a currency claim. Consider a neutral "units" default and a clear label.
- Fixed to port 5173 and a single API URL via one env var; `frontend/README` mentions `.env.example`, which does not exist. README uses `npm install`, root README `npm ci`.
- `frontend/dist/` is built output and is gitignored; the zip contains it, which can mislead about whether a build was run.
- No accessibility audit, no keyboard test of the command palette and drawer.
- Plotly bundle is large (build config raises the chunk warning limit to 1,600 kB).

### 13. No CI, deployment, logging or monitoring
No GitHub Actions or other CI, no deployment config or hosting choice, no structured logging, no health or error monitoring, no backup or migration strategy for the database. Docker is excluded by decision D-011, so the deployment route needs another packaging approach.

### 14. Data questions still unanswered
- Currency of billing and MRR amounts.
- Meaning of `mrr` (it equals `amount_due` and repeats monthly).
- When `payment_status` is recorded relative to churn, and how `churn_risk_score` is produced.
- Licence and download metadata for the billing and churn files.
- Handling of 59 rows with last activity before signup.
- Sample database is unused and still sits in `data/raw/sample_lab/` with credential-like fields.

---

## P3

- Documentation will drift again unless it is updated alongside code changes (model version, threshold, metrics, endpoint list).
- Several scripts repeat the same column-cleaning, engine-creation and adoption-rate conversion code. Move shared helpers to a `scripts/common.py` or a package.
- Scripts use `print` and have no logging or command-line arguments.
- `feature_adoption_rate` is stored as percentage points in PostgreSQL but as a 0 to 1 proportion in the model and API. Pick one and document or convert it.
- `backend/README.txt` should be `README.md`; the sub-folder READMEs for `sql/`, `scripts/` and `tests/` were placeholders (replacements are included).
- No LICENSE file, CONTRIBUTING guide, screenshots or architecture diagram image.
- The API version (`1.1.0`) and model version (`1.0.0-calibrated`) are strings with no release process.

## Quick fixes included in this package

| File | What changes |
|---|---|
| `backend/requirements.txt` | Adds pandas, numpy, scikit-learn, joblib and pydantic |
| `.env.example` | Template for database settings |
| `backend/README.md`, `sql/README.md`, `scripts/README.md`, `tests/README.md` | Replace the placeholder text |

The SQL fix for gap 6 and the Methodology page update for gap 3 are code changes, so they are described here but not applied.
