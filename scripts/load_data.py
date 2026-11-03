
from pathlib import Path
import json
import os
import re
import sys

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, URL, text, inspect

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

load_dotenv(ROOT / ".env")

required = ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
missing = [key for key in required if not os.getenv(key)]
if missing:
    sys.exit(f"Missing .env settings: {missing}")

url = URL.create(
    "postgresql+psycopg2",
    username=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT")),
    database=os.getenv("DB_NAME"),
)

engine = create_engine(url, pool_pre_ping=True)

SCHEMAS = [
    "primary_analytics",
    "churn_lab",
    "sample_lab",
    "benchmarks",
]


def only_file(folder, suffix):
    files = list(folder.glob(f"*{suffix}"))
    if len(files) != 1:
        raise RuntimeError(
            f"Expected exactly one {suffix} file in {folder}; found {len(files)}"
        )
    return files[0]


def clean_column_names(df):
    df = df.copy()
    df.columns = [
        re.sub(r"_+", "_", re.sub(r"[^a-zA-Z0-9]+", "_", str(c).strip()))
        .strip("_")
        .lower()
        for c in df.columns
    ]
    return df


def create_schemas():
    with engine.begin() as conn:
        for schema in SCHEMAS:
            conn.execute(
                text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            )
    print("[OK] Database schemas verified")


def load_table(df, schema, table):
    if df.empty:
        raise ValueError(f"{schema}.{table} is empty")

    if not schema.replace("_", "").isalnum():
        raise ValueError(f"Invalid schema name: {schema}")

    if not table.replace("_", "").isalnum():
        raise ValueError(f"Invalid table name: {table}")

    with engine.begin() as conn:
        table_exists = inspect(conn).has_table(table, schema=schema)

        if table_exists:
            # Delete existing rows while preserving table structure and dependent SQL views.
            conn.execute(
                text(f'DELETE FROM "{schema}"."{table}"')
            )

        # Append into an existing table, or create it on first load.
        df.to_sql(
            name=table,
            con=conn,
            schema=schema,
            if_exists="append",
            index=False,
            chunksize=1000,
            method="multi",
        )

        count = conn.execute(
            text(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
        ).scalar_one()

        if count != len(df):
            raise RuntimeError(
                f"Row count mismatch for {schema}.{table}: "
                f"expected {len(df)}, got {count}"
            )

    print(f"[LOADED] {schema}.{table}: {count:,} rows")


def main():
    print("HORIZON ETL starting...")

    create_schemas()

    # 1. Primary SaaS billing dataset
    primary_file = only_file(RAW / "primary", ".xlsx")
    primary = pd.read_excel(primary_file)
    primary.columns = primary.columns.astype(str).str.strip().str.lower()

    primary["invoice_date"] = pd.to_datetime(
        primary["invoice_date"], errors="coerce"
    )

    for col in ["seats", "mrr", "amount_due", "amount_paid"]:
        primary[col] = pd.to_numeric(primary[col], errors="coerce")

    load_table(primary, "primary_analytics", "invoice_lines")

    # 2. Independent churn modelling dataset
    churn_file = only_file(RAW / "churn", ".csv")
    churn = pd.read_csv(churn_file, low_memory=False)
    churn = clean_column_names(churn)

    for col in ["signup_date", "last_active_date"]:
        churn[col] = pd.to_datetime(churn[col], errors="coerce")

    churn["feature_adoption_rate"] = pd.to_numeric(
        churn["feature_adoption_rate"].astype(str).str.replace("%", ""),
        errors="coerce",
    )

    # Retained for audit; excluded from model features.
    load_table(churn, "churn_lab", "customer_churn")

    # 3. External benchmark reference dataset
    benchmark_file = only_file(RAW / "benchmarks", ".json")
    benchmark_data = json.loads(
        benchmark_file.read_text(encoding="utf-8")
    )

    benchmark_rows = benchmark_data.get("rows", [])
    benchmarks = pd.json_normalize(benchmark_rows)

    for col in benchmarks.columns:
        if benchmarks[col].map(
            lambda value: isinstance(value, (dict, list))
        ).any():
            benchmarks[col] = benchmarks[col].map(
                lambda value: json.dumps(value)
                if isinstance(value, (dict, list)) else value
            )

    load_table(benchmarks, "benchmarks", "industry_churn")

    # 4. Preserve benchmark provenance
    metadata = pd.DataFrame([
        {"key": str(key), "value": json.dumps(value, default=str)}
        for key, value in benchmark_data.items()
        if key != "rows"
    ])

    load_table(metadata, "benchmarks", "source_metadata")

    print("\nETL completed successfully.")
    print("Sample database intentionally excluded pending sanitization.")
    print("Existing tables were refreshed without dropping their definitions.")


if __name__ == "__main__":
    main()
