from __future__ import annotations

import json
import re
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, text


ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "raw" / "churn" / "MP_Synthetics_50000_Rows.csv"
MODEL_FILE = ROOT / "models" / "horizon_churn_logistic_no_payment_status_calibrated.joblib"
OUTPUT_DIR = ROOT / "data" / "processed" / "calibrated_customer_scoring"
OUTPUT_CSV = OUTPUT_DIR / "calibrated_customer_scores.csv"
OUTPUT_JSON = OUTPUT_DIR / "batch_scoring_report.json"

TABLE_SCHEMA = "churn_lab"
TABLE_NAME = "calibrated_customer_scores"


def snake(value: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(value).strip())
    return re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()


def make_engine():
    load_dotenv(ROOT / ".env")
    required = ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
    missing = [key for key in required if not __import__("os").getenv(key)]
    if missing:
        raise RuntimeError("Missing .env settings: " + ", ".join(missing))

    import os
    url = URL.create(
        "postgresql+psycopg2",
        username=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME"),
    )
    return create_engine(url, pool_pre_ping=True)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Churn dataset not found: {DATA_FILE}")
    if not MODEL_FILE.exists():
        raise FileNotFoundError(f"Calibrated model not found: {MODEL_FILE}")

    print("=" * 68)
    print("HORIZON — BATCH CUSTOMER RISK SCORING")
    print("=" * 68)

    df = pd.read_csv(DATA_FILE)
    df.columns = [snake(c) for c in df.columns]

    required_features = [
        "monthly_recurring_revenue",
        "active_seats_used",
        "total_seats_allowed",
        "support_tickets_30d",
        "feature_adoption_rate",
        "industry",
        "country",
        "company_size",
        "account_manager",
        "plan_tier",
        "billing_cycle",
    ]
    missing_features = [c for c in required_features if c not in df.columns]
    if missing_features:
        raise ValueError(f"Dataset is missing model features: {missing_features}")

    if "customer_id" not in df.columns:
        raise ValueError("Customer_ID is required to identify scored customers.")

    if "feature_adoption_rate" in df.columns:
        adoption = df["feature_adoption_rate"].astype(str).str.replace("%", "", regex=False)
        adoption = pd.to_numeric(adoption, errors="coerce")
        if adoption.notna().any() and adoption.max() > 1:
            adoption = adoption / 100
        df["feature_adoption_rate"] = adoption

    # Do not send target, possible leakage fields, identifiers or dates to the model.
    X = df[required_features].copy()
    model = joblib.load(MODEL_FILE)

    print(f"Loaded customers: {len(df):,}")
    print("Scoring with calibrated model...")
    probabilities = model.predict_proba(X)[:, 1]

    result = pd.DataFrame({
        "customer_id": df["customer_id"].astype(str),
        "company_name": (
            df["company_name"].astype(str)
            if "company_name" in df.columns
            else "Unknown"
        ),
        "predicted_churn_probability": probabilities.astype(float),
        "actual_is_churned": (
            pd.to_numeric(df["is_churned"], errors="coerce").fillna(0).astype(int)
            if "is_churned" in df.columns
            else None
        ),
    })

    # Percentile is a ranking measure, not a probability.
    result["risk_percentile"] = (
        result["predicted_churn_probability"].rank(method="average", pct=True) * 100
    )

    # Mutually exclusive score-ranking bands across this dataset.
    rank_order = result["predicted_churn_probability"].rank(
        method="first", ascending=False
    )
    n = len(result)
    result["priority_tier"] = np.select(
        [
            rank_order <= max(1, int(np.ceil(n * 0.01))),
            rank_order <= max(1, int(np.ceil(n * 0.05))),
            rank_order <= max(1, int(np.ceil(n * 0.20))),
        ],
        ["Critical", "High", "Medium"],
        default="Monitor",
    )

    result["review_threshold"] = 0.075
    result["flag_for_review"] = (
        result["predicted_churn_probability"] >= result["review_threshold"]
    )
    result["model_name"] = "Logistic Regression — sigmoid calibrated — no payment_status"
    result["model_version"] = "1.0.0-calibrated"

    result = result.sort_values(
        "predicted_churn_probability", ascending=False
    ).reset_index(drop=True)

    # Add non-sensitive descriptive features for the explorer and filters.
    for col in ["industry", "country", "company_size", "plan_tier", "billing_cycle"]:
        if col in df.columns:
            result[col] = df[col].astype("string").fillna("Unknown").astype(str)

    result.to_csv(OUTPUT_CSV, index=False)

    tier_summary = (
        result.groupby("priority_tier", dropna=False)
        .agg(
            customer_count=("customer_id", "size"),
            average_predicted_probability=("predicted_churn_probability", "mean"),
            flagged_for_review=("flag_for_review", "sum"),
            observed_churned_customers=("actual_is_churned", "sum"),
        )
        .reset_index()
    )
    tier_summary["average_predicted_probability_pct"] = (
        tier_summary["average_predicted_probability"] * 100
    )

    report = {
        "rows_scored": int(len(result)),
        "unique_customer_ids": int(result["customer_id"].nunique()),
        "model_file": str(MODEL_FILE.relative_to(ROOT)),
        "model_version": "1.0.0-calibrated",
        "threshold": 0.075,
        "flagged_for_review": int(result["flag_for_review"].sum()),
        "tier_definition": {
            "Critical": "Top 1% by predicted score",
            "High": "Next 4% by predicted score",
            "Medium": "Next 15% by predicted score",
            "Monitor": "Remaining 80% by predicted score",
        },
        "tier_summary": tier_summary.to_dict(orient="records"),
        "cautions": [
            "Source dataset is synthetic.",
            "Scores are model estimates, not verified future outcomes.",
            "Priority tiers are relative ranking bands, not probability categories.",
            "actual_is_churned is historical target data included for retrospective analysis only.",
            "The source customer dataset is not joined to the separate billing dataset.",
        ],
        "csv_file": str(OUTPUT_CSV.relative_to(ROOT)),
        "postgres_table": f"{TABLE_SCHEMA}.{TABLE_NAME}",
    }

    OUTPUT_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print("\nTier summary:")
    print(tier_summary.to_string(index=False))
    print(f"\nFlagged at threshold 0.075: {int(result['flag_for_review'].sum()):,}")
    print(f"CSV saved: {OUTPUT_CSV}")

    print("\nLoading separate PostgreSQL table...")
    engine = make_engine()
    try:
        with engine.begin() as connection:
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {TABLE_SCHEMA}"))

        # Replace only this new dedicated table; existing intelligence tables are untouched.
        result.to_sql(
            TABLE_NAME,
            engine,
            schema=TABLE_SCHEMA,
            if_exists="replace",
            index=False,
            chunksize=3000,
            method="multi",
        )

        with engine.connect() as connection:
            count = connection.execute(
                text(f"SELECT COUNT(*) FROM {TABLE_SCHEMA}.{TABLE_NAME}")
            ).scalar_one()

        if count != len(result):
            raise RuntimeError(
                f"PostgreSQL row count mismatch: expected {len(result)}, got {count}"
            )

        print(f"PostgreSQL table: {TABLE_SCHEMA}.{TABLE_NAME}")
        print(f"Rows verified: {count:,}")
    finally:
        engine.dispose()

    print(f"\nReport saved: {OUTPUT_JSON}")
    print("\nBATCH CUSTOMER SCORING COMPLETED SUCCESSFULLY")


if __name__ == "__main__":
    main()
