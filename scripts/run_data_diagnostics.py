from pathlib import Path
import json
import re

import numpy as np
import pandas as pd
from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]

CHURN_FILE = (
    ROOT / "data" / "raw" / "churn"
    / "MP_Synthetics_50000_Rows.csv"
)

PRIMARY_FILE = (
    ROOT / "data" / "raw" / "primary"
    / "saas-subscriptions-v1.0.0-analysis.xlsx"
)

OUT = ROOT / "data" / "processed" / "diagnostics"


def snake(value):
    """Convert column names to lowercase snake_case."""
    value = re.sub(
        r"([a-z0-9])([A-Z])",
        r"\1_\2",
        str(value).strip()
    )
    return re.sub(
        r"[^a-zA-Z0-9]+",
        "_",
        value
    ).strip("_").lower()


def churn_diagnostics():

    print("Reading churn dataset...")

    df = pd.read_csv(CHURN_FILE)
    df.columns = [snake(c) for c in df.columns]

    required = ["is_churned"]

    for col in required:
        if col not in df.columns:
            raise ValueError(
                f"Required column missing: {col}"
            )

    df["is_churned"] = pd.to_numeric(
        df["is_churned"],
        errors="coerce"
    )

    df = df[
        df["is_churned"].isin([0, 1])
    ].copy()

    df["is_churned"] = (
        df["is_churned"].astype(int)
    )

    # --------------------------------------------------
    # 1. Feature adoption normalization
    # --------------------------------------------------

    if "feature_adoption_rate" in df.columns:

        adoption = (
            df["feature_adoption_rate"]
            .astype(str)
            .str.replace("%", "", regex=False)
        )

        df["feature_adoption_rate_numeric"] = (
            pd.to_numeric(
                adoption,
                errors="coerce"
            )
        )

        valid_adoption = (
            df["feature_adoption_rate_numeric"]
            .dropna()
        )

        if (
            not valid_adoption.empty
            and valid_adoption.max() > 1
        ):
            df["feature_adoption_rate_numeric"] /= 100

    # --------------------------------------------------
    # 2. Categorical segment diagnostics
    # --------------------------------------------------

    categorical = [
        "payment_status",
        "plan_tier",
        "billing_cycle",
        "industry",
        "company_size",
        "country"
    ]

    categorical = [
        col for col in categorical
        if col in df.columns
    ]

    segment_frames = []

    for col in categorical:

        grouped = (
            df.groupby(col, dropna=False)["is_churned"]
            .agg(
                customer_count="size",
                churned_customers="sum",
                churn_rate="mean"
            )
            .reset_index()
        )

        grouped.insert(0, "dimension", col)

        grouped = grouped.rename(
            columns={col: "segment"}
        )

        grouped["churn_rate_pct"] = (
            grouped["churn_rate"] * 100
        )

        segment_frames.append(grouped)

    segments = (
        pd.concat(
            segment_frames,
            ignore_index=True
        )
        if segment_frames
        else pd.DataFrame()
    )

    # --------------------------------------------------
    # 3. Date quality checks
    # --------------------------------------------------

    date_report = {}

    if {
        "signup_date",
        "last_active_date"
    }.issubset(df.columns):

        signup = pd.to_datetime(
            df["signup_date"],
            errors="coerce"
        )

        last_active = pd.to_datetime(
            df["last_active_date"],
            errors="coerce"
        )

        valid_dates = (
            signup.notna()
            & last_active.notna()
        )

        before = (
            valid_dates
            & (last_active < signup)
        )

        valid_intervals = (
            valid_dates
            & ~before
        )

        date_report = {
            "signup_date_parse_failures": int(
                signup.isna().sum()
            ),

            "last_active_date_parse_failures": int(
                last_active.isna().sum()
            ),

            "last_active_before_signup": int(
                before.sum()
            ),

            "median_days_between_signup_and_last_active_when_valid": (
                float(
                    (
                        last_active[valid_intervals]
                        - signup[valid_intervals]
                    ).dt.days.median()
                )
                if valid_intervals.any()
                else None
            ),

            "note": (
                "Last-active date timing relative to "
                "the churn event is not established. "
                "It remains excluded from the current model."
            )
        }

    # --------------------------------------------------
    # 4. Numeric feature diagnostics
    # --------------------------------------------------

    numeric_candidates = [
        "monthly_recurring_revenue",
        "active_seats_used",
        "total_seats_allowed",
        "support_tickets_30d",
        "feature_adoption_rate_numeric",
        "churn_risk_score"
    ]

    numeric_summary = []

    for col in numeric_candidates:

        if col not in df.columns:
            continue

        # IMPORTANT FIX:
        # Convert values safely to numeric.
        # Text values such as Low, Medium and High
        # become NaN instead of crashing the script.

        numeric_values = pd.to_numeric(
            df[col],
            errors="coerce"
        )

        temp = pd.DataFrame({
            "is_churned": df["is_churned"],
            "value": numeric_values
        })

        temp = temp.dropna(
            subset=["value"]
        )

        if temp.empty:
            print(
                f"Skipping numeric statistics for {col}: "
                "no numeric values found."
            )
            continue

        grouped = (
            temp.groupby("is_churned")["value"]
            .agg([
                "count",
                "mean",
                "median",
                "std"
            ])
            .reset_index()
        )

        for _, row in grouped.iterrows():

            numeric_summary.append({
                "feature": col,

                "is_churned": int(
                    row["is_churned"]
                ),

                "count": int(
                    row["count"]
                ),

                "mean": (
                    None
                    if pd.isna(row["mean"])
                    else float(row["mean"])
                ),

                "median": (
                    None
                    if pd.isna(row["median"])
                    else float(row["median"])
                ),

                "std": (
                    None
                    if pd.isna(row["std"])
                    else float(row["std"])
                )
            })

    # --------------------------------------------------
    # 5. Potential data leakage checks
    # --------------------------------------------------

    leakage = {}

    # Churn risk score may be categorical or numeric.
    # Check both possibilities without assuming its type.

    if "churn_risk_score" in df.columns:

        risk_numeric = pd.to_numeric(
            df["churn_risk_score"],
            errors="coerce"
        )

        if risk_numeric.notna().sum() > 1:

            correlation = pd.DataFrame({
                "risk_score": risk_numeric,
                "is_churned": df["is_churned"]
            }).corr().iloc[0, 1]

            correlation = (
                None
                if pd.isna(correlation)
                else float(correlation)
            )

        else:
            correlation = None

        risk_categories = (
            df["churn_risk_score"]
            .dropna()
            .astype(str)
            .value_counts()
            .to_dict()
        )

        risk_churn_rates = (
            df.groupby(
                "churn_risk_score",
                dropna=False
            )["is_churned"]
            .agg(
                customer_count="size",
                churn_rate="mean"
            )
            .reset_index()
        )

        risk_churn_rates["churn_rate_pct"] = (
            risk_churn_rates["churn_rate"] * 100
        )

        risk_churn_rates.to_csv(
            OUT / "churn_risk_score_diagnostics.csv",
            index=False
        )

        leakage["churn_risk_score"] = {
            "numeric_correlation_with_target": correlation,

            "unique_value_counts": risk_categories,

            "decision": (
                "Keep excluded until data-generation "
                "provenance and timestamp are verified."
            )
        }

    if "payment_status" in df.columns:

        leakage["payment_status"] = {
            "unique_values": sorted(
                df["payment_status"]
                .dropna()
                .astype(str)
                .unique()
                .tolist()
            ),

            "decision": (
                "Verify whether payment status was measured "
                "before the churn prediction point. "
                "Association alone does not prove leakage."
            )
        }

    # --------------------------------------------------
    # 6. Overall dataset summary
    # --------------------------------------------------

    summary = {

        "rows": int(len(df)),

        "churned": int(
            df["is_churned"].sum()
        ),

        "not_churned": int(
            (df["is_churned"] == 0).sum()
        ),

        "churn_rate_pct": float(
            df["is_churned"].mean() * 100
        ),

        "date_quality": date_report,

        "potential_leakage_checks": leakage,

        "limitations": [
            "This is diagnostic analysis, not causal inference.",

            "Feature timing and target-generation logic "
            "cannot be proven from values alone.",

            "Payment status must be verified against "
            "the intended prediction timestamp.",

            "Categorical risk scores are not treated "
            "as numerical values."
        ]
    }

    # --------------------------------------------------
    # 7. Save reports
    # --------------------------------------------------

    segments.to_csv(
        OUT / "churn_segment_diagnostics.csv",
        index=False
    )

    pd.DataFrame(
        numeric_summary
    ).to_csv(
        OUT / "churn_numeric_diagnostics.csv",
        index=False
    )

    (
        OUT / "churn_diagnostics.json"
    ).write_text(
        json.dumps(
            summary,
            indent=2
        ),
        encoding="utf-8"
    )

    return summary



def primary_currency_diagnostics():

    print("Scanning primary workbook for currency clues...")

    wb = load_workbook(
        PRIMARY_FILE,
        read_only=True,
        data_only=False
    )

    result = {
        "workbook": PRIMARY_FILE.name,
        "sheets": []
    }

    keywords = (
        "currency",
        "inr",
        "usd",
        "eur",
        "gbp",
        "rupee",
        "dollar",
        "amount_due",
        "amount_paid",
        "mrr"
    )

    for ws in wb.worksheets:

        hits = []

        # Handle worksheets where max_row is None.
        max_row = ws.max_row or 30
        rows_to_scan = min(max_row, 30)

        for row in ws.iter_rows(
            min_row=1,
            max_row=rows_to_scan,
            values_only=True
        ):

            for value in row:

                if (
                    isinstance(value, str)
                    and any(
                        keyword in value.lower()
                        for keyword in keywords
                    )
                ):
                    hits.append(value[:160])

        result["sheets"].append({
            "name": ws.title,
            "dimensions": ws.calculate_dimension(force=True),
            "currency_or_amount_text_hits": sorted(
                set(hits)
            )[:30]
        })

    wb.close()

    result["conclusion"] = (
        "This scan can surface explicit currency labels "
        "in workbook text. Absence of a label does not "
        "establish the currency. Confirm with the "
        "dataset source documentation."
    )

    (
        OUT / "primary_currency_diagnostics.json"
    ).write_text(
        json.dumps(result, indent=2),
        encoding="utf-8"
    )

    return result



def main():

    print("=" * 60)
    print("HORIZON DATA DIAGNOSTICS")
    print("=" * 60)

    OUT.mkdir(
        parents=True,
        exist_ok=True
    )

    for path in [
        CHURN_FILE,
        PRIMARY_FILE
    ]:

        if not path.exists():

            raise FileNotFoundError(
                f"Expected dataset not found: {path}"
            )

    churn = churn_diagnostics()

    currency = primary_currency_diagnostics()

    print("\n" + "=" * 60)
    print("CHURN DATA QUALITY")
    print("=" * 60)

    print(
        json.dumps(
            churn,
            indent=2
        )
    )

    print("\n" + "=" * 60)
    print("PRIMARY WORKBOOK CURRENCY SCAN")
    print("=" * 60)

    print(
        json.dumps(
            currency,
            indent=2
        )
    )

    print("\n" + "=" * 60)
    print("DIAGNOSTICS COMPLETED SUCCESSFULLY")
    print("=" * 60)

    print(f"\nReports saved to:\n{OUT}")


if __name__ == "__main__":
    main()
