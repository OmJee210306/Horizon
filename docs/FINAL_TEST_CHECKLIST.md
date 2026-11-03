# HORIZON Final Test Checklist

Manual verification before describing the project as tested. **No item has been recorded as run.** Tick a box only after you have actually done the check, and note the date and result in section G.

Commands use PowerShell and the project root `D:\Horizon`. Adjust for your machine.

## A. Clean-install check

This catches setup gaps that a working developer machine hides.

- [ ] In a new folder and a new virtual environment, `python -m pip install -r backend\requirements.txt` completes.
- [ ] `python -c "import pandas, joblib, sklearn"` succeeds in that environment (these are needed by the API but were missing from the original `requirements.txt`).
- [ ] The API starts and the model loads (`GET /api/churn/model-info` shows `available: true`).
- [ ] `sklearn.__version__` is 1.7.2, or loading the model produces no version warning.
- [ ] `.env.example` exists, and `.env` is not tracked by Git (`git check-ignore .env` prints the path).

## B. Environment and services

- [ ] PostgreSQL is running and database `horizon` exists with schemas `primary_analytics`, `churn_lab`, `benchmarks`.
- [ ] Backend starts with no traceback.
- [ ] Frontend starts with no Vite errors (`npm ci`, `npm run dev`).
- [ ] `GET /api/health` returns `status: ok`, `database: connected`, `churn_model: available`.
- [ ] Stopping PostgreSQL makes `/api/health` return 503 and the dashboard show an error state, not a blank page.

## C. Pipeline and data checks

Run these in psql after the pipeline in the README has completed.

```sql
SELECT COUNT(*) FROM primary_analytics.invoice_lines;            -- expect 85448
SELECT COUNT(*) FROM churn_lab.customer_churn;                   -- expect 50000
SELECT SUM(is_churned) FROM churn_lab.customer_churn;            -- expect 916
SELECT COUNT(*) FROM churn_lab.calibrated_customer_scores;       -- expect 50000

SELECT priority_tier, COUNT(*)
FROM churn_lab.calibrated_customer_scores
GROUP BY priority_tier
ORDER BY CASE priority_tier
    WHEN 'Critical' THEN 1 WHEN 'High' THEN 2
    WHEN 'Medium' THEN 3 ELSE 4 END;
-- expect Critical 500, High 2000, Medium 7500, Monitor 40000

SELECT COUNT(*) FROM churn_lab.calibrated_customer_scores
WHERE flag_for_review;                                           -- expect 1750

SELECT invoice_status, COUNT(*), SUM(amount_due), SUM(amount_paid)
FROM primary_analytics.invoice_lines GROUP BY 1;
-- expect paid 80101 / 27639401 / 27639401, open 5311 / 1857721 / 0, void 36 / 9652 / 0
```

- [ ] All counts match the expected values above.
- [ ] The 10 views exist (`\dv primary_analytics.*` and `\dv churn_lab.*`).
- [ ] Re-running `scripts/load_data.py` on an already-built database either succeeds or fails with a clear message (known risk: dependent views block table replacement).

## D. API checks

Use `/docs` or curl.

- [ ] `GET /api/overview`
- [ ] `GET /api/revenue/monthly`, `/regions`, `/plans`, `/invoice-status`
- [ ] `GET /api/revenue/accounts?limit=20&offset=0`; `limit=101` returns 422
- [ ] `GET /api/churn/summary`
- [ ] `GET /api/churn/features`, `/segments`, `/numeric-bands`
- [ ] `GET /api/churn/customers?tier=Critical&limit=10` returns 10 rows, all Critical
- [ ] `GET /api/churn/customers?tier=Bogus` returns 422
- [ ] `GET /api/churn/customers?search=CUST-1001` finds the customer
- [ ] `GET /api/churn/customers/count` returns 50000
- [ ] `GET /api/churn/model-info` and `/batch-model-info`
- [ ] `POST /api/churn/predict` with the example payload in `API_REFERENCE.md` returns a probability and a decision
- [ ] `POST /api/churn/predict` with `payment_status` returns 422
- [ ] `POST /api/churn/predict` with `feature_adoption_rate: 58` returns 422 (must be 0 to 1)
- [ ] `POST /api/churn/predict` with `{}` returns a response with all 11 features in `missing_features`

## E. Metric reconciliation

- [ ] `total_collected` in `/api/overview` equals 27,639,401.
- [ ] `total_billed` equals `SUM(amount_due)` computed independently from the Excel file (pandas).
- [ ] `unpaid_balance` is compared with open-only (1,857,721). Record whether the dashboard label matches the number (see KNOWN_GAPS item 6).
- [ ] The sum of `total_billed` across regions equals the overall total.
- [ ] The sum of tier counts equals 50,000.

## F. Frontend checks

- [ ] Every page loads with no blank screen: Overview, Revenue, Churn, Sources, Methodology.
- [ ] Revenue charts render and the period filter changes them.
- [ ] Churn: risk overview, segments, customer explorer and prediction form all work.
- [ ] Customer explorer: search, tier filter, pagination, drawer and CSV export work.
- [ ] Prediction form submits and shows a result; an API error shows a readable message.
- [ ] **Methodology page values match the deployed model** (PR-AUC about 0.095, calibrated, threshold 0.075). The original page showed 0.205 and "not calibrated".
- [ ] **Feature-importance chart:** record whether it lists `payment_status`, and whether that is acceptable given the deployed model excludes it.
- [ ] Light and dark theme, sidebar, mobile drawer and `Ctrl/Cmd + K` still work.
- [ ] The browser console shows no uncaught errors.
- [ ] Stopping the API shows retry and error states.

## G. Build and repository hygiene

```powershell
cd D:\Horizon\frontend
npm ci
npm run build
cd D:\Horizon
git status --short
git check-ignore .env .venv frontend/dist data/raw
```

- [ ] `npm run build` succeeds.
- [ ] `.env`, `.venv`, `frontend/dist`, raw data, generated customer-level CSVs and model files are not staged.
- [ ] No password or token appears in any tracked file (`git grep -i password`).
- [ ] If a real DB password was ever shared (for example in a zip), it has been rotated.

## H. Evidence to record

| Evidence | Done | Date and result |
|---|---|---|
| Screenshot: Overview | [ ] | |
| Screenshot: Revenue Analytics | [ ] | |
| Screenshot: Churn Intelligence and customer explorer | [ ] | |
| Screenshot: prediction result | [ ] | |
| Successful frontend build output | [ ] | |
| `/api/health` response | [ ] | |
| Postgres count of 50,000 scored customers | [ ] | |

Do not mark a check complete until it has been run.
