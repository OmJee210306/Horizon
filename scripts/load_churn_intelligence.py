"""
HORIZON - Load churn intelligence outputs into PostgreSQL.

Run from project root:
    python scripts/load_churn_intelligence.py

Creates/replaces only these dedicated tables in schema churn_lab:
  churn_customer_intelligence
  churn_priority_tier_summary
  churn_model_feature_importance
  churn_observed_by_segment
  churn_observed_numeric_bands

Does not modify the original customer_churn table or existing SQL views.
"""

from pathlib import Path
import os
import sys

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


ROOT = Path(__file__).resolve().parents[1]
INTELLIGENCE_DIR = ROOT / "data" / "processed" / "churn_intelligence"

FILES = {
    "churn_customer_intelligence": "customer_churn_intelligence.csv",
    "churn_priority_tier_summary": "priority_tier_summary.csv",
    "churn_model_feature_importance": "model_feature_importance.csv",
    "churn_observed_by_segment": "observed_churn_by_segment.csv",
    "churn_observed_numeric_bands": "observed_churn_numeric_bands.csv",
}


def create_db_engine():
    load_dotenv(ROOT / ".env")

    required = ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError(
            "Missing database settings in .env: " + ", ".join(missing)
        )

    url = URL.create(
        "postgresql+psycopg2",
        username=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT")),
        database=os.getenv("DB_NAME"),
    )
    return create_engine(url, pool_pre_ping=True)


def main():
    if not INTELLIGENCE_DIR.exists():
        raise FileNotFoundError(
            f"Intelligence output folder not found: {INTELLIGENCE_DIR}\n"
            "Run scripts/build_churn_intelligence.py first."
        )

    engine = create_db_engine()

    with engine.begin() as connection:
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS churn_lab"))

    print("Connected to PostgreSQL.")
    loaded = {}

    for table_name, filename in FILES.items():
        path = INTELLIGENCE_DIR / filename
        if not path.exists():
            if table_name == "churn_observed_numeric_bands":
                print(f"Optional file missing; skipping: {filename}")
                continue
            raise FileNotFoundError(f"Required output missing: {path}")

        frame = pd.read_csv(path)
        if frame.empty:
            raise ValueError(f"Refusing to load empty file: {path}")

        frame.to_sql(
            name=table_name,
            con=engine,
            schema="churn_lab",
            if_exists="replace",
            index=False,
            chunksize=5000,
            method="multi",
        )
        loaded[table_name] = len(frame)
        print(f"Loaded churn_lab.{table_name}: {len(frame):,} rows")

    # Add useful indexes to the customer-level table.
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_churn_intel_risk_score
            ON churn_lab.churn_customer_intelligence
            (predicted_churn_probability DESC)
        """))
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_churn_intel_priority_tier
            ON churn_lab.churn_customer_intelligence
            (priority_tier)
        """))

    # Verify the resulting table counts.
    print("\nPOST-LOAD VERIFICATION")
    with engine.connect() as connection:
        for table_name, expected in loaded.items():
            actual = connection.execute(
                text(f'SELECT COUNT(*) FROM churn_lab."{table_name}"')
            ).scalar_one()
            status = "OK" if actual == expected else "MISMATCH"
            print(f"{status}: churn_lab.{table_name} -> {actual:,} rows")

    engine.dispose()
    print("\nChurn intelligence data is now available in PostgreSQL.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        raise
