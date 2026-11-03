# HORIZON Decisions Log

IDs D-001 to D-012 are the original project decisions. IDs D-013 onward were recorded afterwards by reading the implemented code and reports, so each one says where the evidence is. Confirm or change any of them; the log is only useful if it matches what you actually decided.

Status values: **Locked** (do not change without a new entry), **Provisional** (acting default, expected to be revisited), **Open** (undecided).

## A. Original decisions

| ID | Decision | Rationale / guardrail | Status |
|---|---|---|---|
| D-001 | Project name is HORIZON | User-selected | Locked |
| D-002 | Stack: Python, PostgreSQL, FastAPI, React and Vite | Approved technology set | Locked |
| D-003 | Plotly.js for frontend charts | Interactive analytical UI | Locked |
| D-004 | Billing invoices are the core business dataset | Largest transaction history | Locked |
| D-005 | The churn CSV is an isolated ML experiment | Different synthetic population, no cross-source joins | Locked |
| D-006 | The sample database is an isolated usage lab with sensitive fields filtered | Small source, credential and payment fields present | Locked |
| D-007 | Benchmark JSON is canonical | Has five drivers per record, CSV is a flattened copy | Locked |
| D-008 | No churn claim from the billing workbook | No cancellation or status history | Locked |
| D-009 | No CAC or marketing ROI claim | No spend or acquisition data | Locked |
| D-010 | Exclude `churn_risk_score` from predictors | Possible proxy or leakage, provenance unknown | Provisional |
| D-011 | Do not use Power BI, Tableau, Streamlit, DuckDB, XGBoost, Prophet, Jupyter or Docker | Explicit scope exclusions | Locked |
| D-012 | Build phase by phase and claim only tested features | Prevents planned work being described as done | Locked |

## B. Decisions recorded from the implementation

| ID | Decision | Evidence | Status |
|---|---|---|---|
| D-013 | Exclude `payment_status` from the deployed model | `run_horizon_calibration.py`, `payment_status_reliability_report.json`. Timing relative to churn is unverified | Provisional |
| D-014 | Use sigmoid (Platt) calibration with 5-fold CV on the training partition | Class weighting inflated probabilities (Brier 0.183 before, 0.017 after) | Locked for v1.0.0 |
| D-015 | Stratified 60/20/20 split, `random_state = 42`; test partition never used for fitting or threshold choice | Calibration report | Locked for v1.0.0 |
| D-016 | Review threshold 0.075, chosen by maximum F1 on validation | Calibration report. F1 ignores business cost | Provisional |
| D-017 | Priority tiers are relative rank bands: top 1%, next 4%, next 15%, remaining 80% | `run_horizon_batch_scoring.py`, `batch_scoring_report.json` | Locked |
| D-018 | Schemas are `primary_analytics`, `churn_lab`, `benchmarks`; database is `horizon` | `load_data.py`, `sql/analytics.sql`. Supersedes the `horizon_db`, `raw_primary`, `analytics` names in the first plan | Locked |
| D-019 | The currency selector changes the displayed symbol only, with no conversion | `frontend/src/config.js`. Source currency is unknown | Provisional |
| D-020 | The sample database is not loaded into PostgreSQL | `load_data.py` prints that it is excluded pending sanitization | Locked |
| D-021 | Two scoring paths: batch scores stored in PostgreSQL, plus a single-customer prediction endpoint | `main.py`, `run_horizon_batch_scoring.py` | Locked |
| D-022 | Model name, version and threshold are hard-coded in code | `main.py`, scoring script. No model registry | Provisional |
| D-023 | Raw SQL through SQLAlchemy `text()` rather than ORM models | `main.py` | Locked |
| D-024 | Local dev ports are fixed (API 8000, UI 5173); CORS allows only those origins | `main.py`, `vite.config.js` | Provisional |

## C. Open decisions

| ID | Question | Why it matters |
|---|---|---|
| D-025 | What happens to the legacy model (`churn_model.joblib`), its tables and its dashboard facts? | Methodology page and the feature-importance chart still describe it, which contradicts the deployed model |
| D-026 | Is `payment_status` allowed as a predictor once its timing is known? | PR-AUC more than doubles with it |
| D-027 | Does "unpaid balance" mean open invoices only, or open plus void? | Current SQL includes void invoices |
| D-028 | Which of the unbuilt plan modules are in scope for v1 (cohorts, benchmarks UI, statistics, simulator)? | Plan and docs must match what ships |
| D-029 | How is the project deployed and tested (CI, hosting)? | None exists today |
| D-030 | How are the 59 rows with `last_active_date` before `signup_date` handled? | Documented as anomalies, no rule applied |
