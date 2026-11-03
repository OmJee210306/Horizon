
-- =========================================================
-- HORIZON: SQL ANALYTICS LAYER
-- Sources remain isolated by schema.
-- =========================================================

-- 1. Monthly billing performance
CREATE OR REPLACE VIEW primary_analytics.monthly_billing AS
SELECT
    DATE_TRUNC('month', invoice_date)::date AS billing_month,
    COUNT(*) AS invoice_count,
    COUNT(DISTINCT account_id) AS active_accounts_in_invoices,
    SUM(amount_due) AS total_billed,
    SUM(amount_paid) AS total_collected,
    SUM(
    	CASE
        	WHEN invoice_status <> 'void'
        	THEN amount_due - amount_paid
        	ELSE 0
    	END
	) AS unpaid_balance,
    SUM(CASE WHEN invoice_status = 'paid' THEN 1 ELSE 0 END)
        AS paid_invoice_count,
    SUM(CASE WHEN invoice_status = 'open' THEN 1 ELSE 0 END)
        AS open_invoice_count,
    SUM(CASE WHEN invoice_status = 'void' THEN 1 ELSE 0 END)
        AS void_invoice_count
FROM primary_analytics.invoice_lines
GROUP BY 1;


-- 2. Invoice status summary
CREATE OR REPLACE VIEW primary_analytics.invoice_status_summary AS
SELECT
    invoice_status,
    COUNT(*) AS invoice_count,
    SUM(amount_due) AS total_billed,
    SUM(amount_paid) AS total_collected,
    ROUND(
        100.0 * COUNT(*) / SUM(COUNT(*)) OVER (),
        2
    ) AS invoice_percentage
FROM primary_analytics.invoice_lines
GROUP BY invoice_status;


-- 3. Plan performance
CREATE OR REPLACE VIEW primary_analytics.plan_performance AS
SELECT
    plan_name,
    COUNT(*) AS invoice_count,
    COUNT(DISTINCT account_id) AS account_count,
    SUM(amount_due) AS total_billed,
    SUM(amount_paid) AS total_collected,
    AVG(seats) AS average_seats,
    AVG(mrr) AS average_invoice_row_mrr
FROM primary_analytics.invoice_lines
GROUP BY plan_name;


-- 4. Regional performance
CREATE OR REPLACE VIEW primary_analytics.regional_performance AS
SELECT
    COALESCE(NULLIF(TRIM(region), ''), 'Unknown') AS region,
    COUNT(*) AS invoice_count,
    COUNT(DISTINCT account_id) AS account_count,
    SUM(amount_due) AS total_billed,
    SUM(amount_paid) AS total_collected
FROM primary_analytics.invoice_lines
GROUP BY 1;


-- 5. Account-level billing summary
CREATE OR REPLACE VIEW primary_analytics.account_billing_summary AS
SELECT
    account_id,
    COUNT(*) AS invoice_count,
    COUNT(DISTINCT subscription_id) AS subscription_count,
    MIN(invoice_date)::date AS first_invoice_date,
    MAX(invoice_date)::date AS latest_invoice_date,
    SUM(amount_due) AS total_billed,
    SUM(amount_paid) AS total_collected,
    SUM(
    	CASE
        	WHEN invoice_status <> 'void'
        	THEN amount_due - amount_paid
        	ELSE 0
    	END
	) AS unpaid_balance
FROM primary_analytics.invoice_lines
GROUP BY account_id;


-- 6. Churn target distribution
CREATE OR REPLACE VIEW churn_lab.churn_distribution AS
SELECT
    is_churned,
    COUNT(*) AS customer_count,
    ROUND(
        100.0 * COUNT(*) / SUM(COUNT(*)) OVER (),
        2
    ) AS customer_percentage
FROM churn_lab.customer_churn
GROUP BY is_churned;


-- 7. Churn by industry
CREATE OR REPLACE VIEW churn_lab.churn_by_industry AS
SELECT
    industry,
    COUNT(*) AS customer_count,
    SUM(is_churned) AS churned_customers,
    ROUND(AVG(is_churned::numeric) * 100, 2) AS churn_rate_pct
FROM churn_lab.customer_churn
GROUP BY industry;


-- 8. Churn by plan tier
CREATE OR REPLACE VIEW churn_lab.churn_by_plan AS
SELECT
    plan_tier,
    COUNT(*) AS customer_count,
    SUM(is_churned) AS churned_customers,
    ROUND(AVG(is_churned::numeric) * 100, 2) AS churn_rate_pct
FROM churn_lab.customer_churn
GROUP BY plan_tier;


-- 9. Churn by billing cycle
CREATE OR REPLACE VIEW churn_lab.churn_by_billing_cycle AS
SELECT
    billing_cycle,
    COUNT(*) AS customer_count,
    SUM(is_churned) AS churned_customers,
    ROUND(AVG(is_churned::numeric) * 100, 2) AS churn_rate_pct
FROM churn_lab.customer_churn
GROUP BY billing_cycle;


-- 10. Churn by payment status
CREATE OR REPLACE VIEW churn_lab.churn_by_payment_status AS
SELECT
    payment_status,
    COUNT(*) AS customer_count,
    SUM(is_churned) AS churned_customers,
    ROUND(AVG(is_churned::numeric) * 100, 2) AS churn_rate_pct
FROM churn_lab.customer_churn
GROUP BY payment_status;
