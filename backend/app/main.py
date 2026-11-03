from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError


ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

required_env = ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
missing_env = [key for key in required_env if not os.getenv(key)]
if missing_env:
    raise RuntimeError(
        "Missing database settings in project .env: " + ", ".join(missing_env)
    )

DATABASE_URL = URL.create(
    "postgresql+psycopg2",
    username=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT", "5432")),
    database=os.getenv("DB_NAME"),
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

# This is the calibrated model saved by the calibration experiment.
CHURN_MODEL_PATH = (
    ROOT
    / "models"
    / "horizon_churn_logistic_no_payment_status_calibrated.joblib"
)
CHURN_THRESHOLD = 0.075
CHURN_MODEL_NAME = "Logistic Regression — sigmoid calibrated — no payment_status"
CHURN_MODEL_VERSION = "1.0.0-calibrated"


class ChurnPredictionRequest(BaseModel):
    """Features expected by the calibrated churn model.

    Fields are optional so the model's training-time imputers can handle
    missing values. payment_status, churn_risk_score, IDs and dates are
    intentionally not accepted.
    """

    model_config = ConfigDict(extra="forbid")

    monthly_recurring_revenue: float | None = Field(default=None, ge=0)
    active_seats_used: int | None = Field(default=None, ge=0)
    total_seats_allowed: int | None = Field(default=None, ge=0)
    support_tickets_30d: int | None = Field(default=None, ge=0)
    feature_adoption_rate: float | None = Field(default=None, ge=0, le=1)

    industry: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, max_length=100)
    company_size: str | None = Field(default=None, max_length=100)
    account_manager: str | None = Field(default=None, max_length=150)
    plan_tier: str | None = Field(default=None, max_length=100)
    billing_cycle: str | None = Field(default=None, max_length=100)


class ChurnPredictionResponse(BaseModel):
    predicted_churn_probability: float
    predicted_churn_probability_pct: float
    threshold: float
    decision: str
    model_name: str
    model_version: str
    missing_features: list[str]
    note: str


app = FastAPI(
    title="HORIZON Analytics API",
    description=(
        "Analytics API for HORIZON. Primary billing and synthetic churn datasets "
        "are intentionally treated as separate sources. The prediction endpoint "
        "uses a calibrated exploratory model trained without payment_status."
    ),
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def clean_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "item"):
        return value.item()
    return value


def rows(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    try:
        with engine.connect() as connection:
            result = connection.execute(text(sql), params or {})
            return [
                {key: clean_value(value) for key, value in row.items()}
                for row in result.mappings()
            ]
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Database query failed: {str(exc.orig)}",
        )


def one(sql: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    result = rows(sql, params)
    return result[0] if result else {}


@lru_cache(maxsize=1)
def load_churn_model():
    """Load the calibrated model once per API process."""
    if not CHURN_MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Calibrated churn model not found: {CHURN_MODEL_PATH}"
        )
    return joblib.load(CHURN_MODEL_PATH)


@app.get("/", tags=["System"])
def root():
    return {
        "name": "HORIZON Analytics API",
        "version": "1.1.0",
        "docs": "/docs",
    }


@app.get("/api/health", tags=["System"])
def health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "database": "connected",
            "churn_model": (
                "available" if CHURN_MODEL_PATH.exists() else "not_found"
            ),
        }
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Database unavailable: {str(exc.orig)}",
        )


@app.get("/api/overview", tags=["Overview"])
def overview():
    """High-level KPIs; billing and churn remain separate data sources."""
    billing = one("""
        SELECT
            COUNT(*) AS invoice_rows,
            COUNT(DISTINCT account_id) AS accounts_in_invoice_data,
            COALESCE(SUM(amount_due), 0) AS total_billed,
            COALESCE(SUM(amount_paid), 0) AS total_collected,
            COALESCE(
                SUM(
                    CASE
                        WHEN invoice_status <> 'void'
                        THEN amount_due - amount_paid
                        ELSE 0
                    END
                ), 0
            ) AS unpaid_balance,
            MIN(invoice_date) AS first_invoice_date,
            MAX(invoice_date) AS latest_invoice_date
        FROM primary_analytics.invoice_lines
    """)
    churn = one("""
        SELECT
            COUNT(*) AS customers,
            COALESCE(SUM(is_churned), 0) AS churned_customers,
            ROUND(100.0 * COALESCE(SUM(is_churned), 0) / NULLIF(COUNT(*), 0), 2)
                AS observed_churn_rate_pct
        FROM churn_lab.customer_churn
    """)
    return {
        "billing_source": billing,
        "independent_churn_source": churn,
        "source_note": (
            "Billing and churn KPIs are calculated from separate datasets. "
            "They must not be interpreted as one joined customer population."
        ),
    }


@app.get("/api/revenue/monthly", tags=["Revenue"])
def monthly_revenue():
    return rows("""
        SELECT *
        FROM primary_analytics.monthly_billing
        ORDER BY billing_month
    """)


@app.get("/api/revenue/regions", tags=["Revenue"])
def regional_revenue():
    return rows("""
        SELECT *
        FROM primary_analytics.regional_performance
        ORDER BY total_billed DESC
    """)


@app.get("/api/revenue/plans", tags=["Revenue"])
def plan_performance():
    return rows("""
        SELECT *
        FROM primary_analytics.plan_performance
        ORDER BY total_billed DESC
    """)


@app.get("/api/revenue/invoice-status", tags=["Revenue"])
def invoice_status():
    return rows("""
        SELECT *
        FROM primary_analytics.invoice_status_summary
    """)


@app.get("/api/revenue/accounts", tags=["Revenue"])
def account_billing(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return rows("""
        SELECT *
        FROM primary_analytics.account_billing_summary
        ORDER BY total_billed DESC
        LIMIT :limit OFFSET :offset
    """, {"limit": limit, "offset": offset})


@app.get("/api/churn/summary", tags=["Churn"])
def churn_summary():
    return {
        "distribution": rows("""
            SELECT
                is_churned,
                COUNT(*) AS customer_count
            FROM churn_lab.customer_churn
            GROUP BY is_churned
            ORDER BY is_churned
        """),
        "priority_tiers": rows("""
            SELECT
                priority_tier,
                COUNT(*) AS customer_count,
                ROUND(AVG(predicted_churn_probability)::numeric, 6)
                    AS average_predicted_probability,
                ROUND(100 * AVG(predicted_churn_probability)::numeric, 2)
                    AS average_predicted_probability_pct,
                COUNT(*) FILTER (WHERE flag_for_review) AS flagged_for_review,
                COALESCE(SUM(actual_is_churned), 0) AS observed_churned_customers
            FROM churn_lab.calibrated_customer_scores
            GROUP BY priority_tier
            ORDER BY CASE priority_tier
                WHEN 'Critical' THEN 1 WHEN 'High' THEN 2
                WHEN 'Medium' THEN 3 ELSE 4 END
        """),
        "model_note": (
            "Customer rankings and priority tiers come from the calibrated "
            "no-payment-status model. Tiers are relative ranking bands, not "
            "probability categories. Churn source data is synthetic."
        ),
    }


@app.get("/api/churn/features", tags=["Churn"])
def churn_features():
    return rows("""
        SELECT *
        FROM churn_lab.churn_model_feature_importance
        ORDER BY mean_pr_auc_decrease DESC
    """)


@app.get("/api/churn/segments", tags=["Churn"])
def churn_segments(dimension: str | None = Query(default=None, max_length=80)):
    if dimension:
        return rows("""
            SELECT *
            FROM churn_lab.churn_observed_by_segment
            WHERE dimension = :dimension
            ORDER BY churn_rate_pct DESC
        """, {"dimension": dimension})
    return rows("""
        SELECT *
        FROM churn_lab.churn_observed_by_segment
        ORDER BY dimension, churn_rate_pct DESC
    """)


@app.get("/api/churn/numeric-bands", tags=["Churn"])
def churn_numeric_bands(dimension: str | None = Query(default=None, max_length=80)):
    if dimension:
        return rows("""
            SELECT *
            FROM churn_lab.churn_observed_numeric_bands
            WHERE dimension = :dimension
            ORDER BY churn_rate_pct DESC
        """, {"dimension": dimension})
    return rows("""
        SELECT *
        FROM churn_lab.churn_observed_numeric_bands
        ORDER BY dimension, churn_rate_pct DESC
    """)


@app.post(
    "/api/churn/predict",
    response_model=ChurnPredictionResponse,
    tags=["Churn Prediction"],
)
def predict_churn(payload: ChurnPredictionRequest):
    """Score one customer with the calibrated no-payment-status model."""
    try:
        model = load_churn_model()
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Churn model unavailable: {exc}",
        )

    feature_values = payload.dict()
    missing_features = [
        name for name, value in feature_values.items() if value is None
    ]

    # The model pipeline contains imputers for missing values.
    input_frame = pd.DataFrame([feature_values])
    try:
        probability = float(model.predict_proba(input_frame)[0][1])
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not score this customer: {str(exc)}",
        )

    decision = (
        "flag_for_review"
        if probability >= CHURN_THRESHOLD
        else "below_review_threshold"
    )

    return ChurnPredictionResponse(
        predicted_churn_probability=round(probability, 6),
        predicted_churn_probability_pct=round(probability * 100, 2),
        threshold=CHURN_THRESHOLD,
        decision=decision,
        model_name=CHURN_MODEL_NAME,
        model_version=CHURN_MODEL_VERSION,
        missing_features=missing_features,
        note=(
            "Exploratory model trained on a synthetic dataset. "
            "The threshold was selected on validation data using F1. "
            "This output is a prioritization signal, not a guarantee or "
            "a production-validated churn forecast."
        ),
    )


@app.get("/api/churn/model-info", tags=["Churn Prediction"])
def churn_model_info():
    return {
        "available": CHURN_MODEL_PATH.exists(),
        "model_name": CHURN_MODEL_NAME,
        "model_version": CHURN_MODEL_VERSION,
        "threshold": CHURN_THRESHOLD,
        "calibrated": True,
        "calibration_method": "sigmoid (Platt scaling)",
        "excluded_features": [
            "payment_status",
            "churn_risk_score",
            "customer_id",
            "company_name",
            "signup_date",
            "last_active_date",
        ],
        "note": (
            "Synthetic-data model. The threshold is a validation-selected "
            "review threshold, not a production business policy."
        ),
    }


@app.get("/api/churn/customers", tags=["Churn"])
def churn_customers(
    tier: str | None = Query(default=None, pattern="^(Critical|High|Medium|Monitor)$"),
    search: str | None = Query(default=None, max_length=100),
    min_score: float | None = Query(default=None, ge=0, le=1),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    conditions = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}

    if tier:
        conditions.append("priority_tier = :tier")
        params["tier"] = tier
    if min_score is not None:
        conditions.append("predicted_churn_probability >= :min_score")
        params["min_score"] = min_score
    if search:
        conditions.append(
            "(COALESCE(customer_id, '') ILIKE :search "
            "OR COALESCE(company_name, '') ILIKE :search)"
        )
        params["search"] = f"%{search}%"

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    return rows(f"""
        SELECT
            customer_id,
            company_name,
            predicted_churn_probability,
            risk_percentile,
            priority_tier,
            flag_for_review,
            review_threshold,
            model_name,
            model_version,
            industry,
            country,
            company_size,
            plan_tier,
            billing_cycle,
            CASE
                WHEN priority_tier = 'Critical'
                    THEN 'Prioritize for immediate retention review'
                WHEN priority_tier = 'High'
                    THEN 'Review account health and engagement'
                WHEN priority_tier = 'Medium'
                    THEN 'Monitor engagement and product adoption'
                ELSE 'Continue routine monitoring'
            END AS recommended_action,
            NULL::text AS top_model_contributors,
            actual_is_churned
        FROM churn_lab.calibrated_customer_scores
        {where_clause}
        ORDER BY predicted_churn_probability DESC
        LIMIT :limit OFFSET :offset
    """, params)


@app.get("/api/churn/customers/count", tags=["Churn"])
def churn_customer_count(
    tier: str | None = Query(default=None, pattern="^(Critical|High|Medium|Monitor)$"),
):
    if tier:
        return one("""
            SELECT COUNT(*) AS total
            FROM churn_lab.calibrated_customer_scores
            WHERE priority_tier = :tier
        """, {"tier": tier})
    return one("""
        SELECT COUNT(*) AS total
        FROM churn_lab.calibrated_customer_scores
    """)


@app.get("/api/churn/batch-model-info", tags=["Churn Prediction"])
def churn_batch_model_info():
    return one("""
        SELECT
            COUNT(*) AS customers_scored,
            COUNT(*) FILTER (WHERE flag_for_review) AS flagged_for_review,
            MAX(model_name) AS model_name,
            MAX(model_version) AS model_version,
            MAX(review_threshold) AS review_threshold,
            MAX(predicted_churn_probability) AS highest_score,
            MIN(predicted_churn_probability) AS lowest_score
        FROM churn_lab.calibrated_customer_scores
    """)


@app.get("/api/metadata/sources", tags=["Metadata"])
def source_metadata():
    return {
        "sources": [
            {
                "name": "SaaS subscription billing",
                "schema": "primary_analytics",
                "description": "Invoice-level billing and payment analytics.",
                "independent": True,
            },
            {
                "name": "Synthetic customer churn",
                "schema": "churn_lab",
                "description": (
                    "Synthetic customer attributes and exploratory churn analytics."
                ),
                "independent": True,
            },
            {
                "name": "Industry churn benchmarks",
                "schema": "benchmarks",
                "description": "External benchmark reference data with source attribution.",
                "independent": True,
            },
        ],
        "data_governance_note": (
            "No customer-level join is performed across the independent billing "
            "and churn datasets."
        ),
    }


@app.on_event("shutdown")
def shutdown_event():
    engine.dispose()
