
from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)

issues = []
summary = []


def add(source, severity, check, detail):
    issues.append({
        "source": source,
        "severity": severity,
        "check": check,
        "detail": str(detail)
    })


def load_primary():
    files = list((RAW / "primary").glob("*.xlsx"))
    if not files:
        add("primary", "ERROR", "file", "No Excel file found")
        return None

    df = pd.read_excel(files[0])
    df.columns = df.columns.astype(str).str.strip()

    expected = [
        "invoice_id", "invoice_date", "invoice_status",
        "account_id", "region", "segment", "subscription_id",
        "plan_name", "seats", "mrr", "amount_due", "amount_paid"
    ]

    missing = [c for c in expected if c not in df.columns]
    if missing:
        add("primary", "WARNING", "expected_columns",
            f"Columns not found: {missing}")

    summary.append({
        "source": "primary",
        "rows": len(df),
        "columns": len(df.columns)
    })

    for col in ["invoice_id", "account_id", "subscription_id"]:
        if col in df.columns:
            count = int(df[col].isna().sum())
            if count:
                add("primary", "WARNING", f"{col}_missing", count)

    if "invoice_id" in df.columns:
        count = int(df["invoice_id"].duplicated().sum())
        if count:
            add("primary", "WARNING", "duplicate_invoice_id", count)

    if "invoice_date" in df.columns:
        dates = pd.to_datetime(df["invoice_date"], errors="coerce")
        count = int(dates.isna().sum())
        if count:
            add("primary", "WARNING", "invalid_invoice_dates", count)

    for col in ["seats", "mrr", "amount_due", "amount_paid"]:
        if col in df.columns:
            values = pd.to_numeric(df[col], errors="coerce")
            invalid = int(values.isna().sum())
            negative = int((values < 0).sum())
            if invalid:
                add("primary", "WARNING", f"{col}_non_numeric", invalid)
            if negative:
                add("primary", "WARNING", f"{col}_negative", negative)

    if {"amount_due", "amount_paid"}.issubset(df.columns):
        due = pd.to_numeric(df["amount_due"], errors="coerce")
        paid = pd.to_numeric(df["amount_paid"], errors="coerce")
        count = int((paid > due).sum())
        if count:
            add("primary", "REVIEW", "paid_exceeds_due", count)

    if "invoice_status" in df.columns:
        summary.append({
            "source": "primary_invoice_status",
            "distribution": df["invoice_status"]
                .value_counts(dropna=False).to_dict()
        })

    return df


def validate_churn():
    files = list((RAW / "churn").glob("*.csv"))
    if not files:
        add("churn", "ERROR", "file", "No CSV file found")
        return

    df = pd.read_csv(files[0], low_memory=False)
    df.columns = df.columns.astype(str).str.strip()

    summary.append({
        "source": "churn",
        "rows": len(df),
        "columns": len(df.columns)
    })

    if "Customer_ID" in df.columns:
        count = int(df["Customer_ID"].duplicated().sum())
        if count:
            add("churn", "WARNING", "duplicate_customer_id", count)

    if "Is_Churned" in df.columns:
        target = pd.to_numeric(df["Is_Churned"], errors="coerce")
        invalid = int((~target.isin([0, 1])).sum())
        if invalid:
            add("churn", "ERROR", "invalid_target_values", invalid)

        summary.append({
            "source": "churn_target_distribution",
            "distribution": target.value_counts(dropna=False).to_dict()
        })

    if {"Signup_Date", "Last_Active_Date"}.issubset(df.columns):
        signup = pd.to_datetime(df["Signup_Date"], errors="coerce")
        active = pd.to_datetime(df["Last_Active_Date"], errors="coerce")
        count = int((active < signup).sum())
        if count:
            add("churn", "WARNING", "last_active_before_signup", count)

    if {"Active_Seats_Used", "Total_Seats_Allowed"}.issubset(df.columns):
        used = pd.to_numeric(df["Active_Seats_Used"], errors="coerce")
        allowed = pd.to_numeric(df["Total_Seats_Allowed"], errors="coerce")
        count = int((used > allowed).sum())
        if count:
            add("churn", "REVIEW", "used_seats_exceed_allowed", count)

    if "Feature_Adoption_Rate" in df.columns:
        adoption = pd.to_numeric(
            df["Feature_Adoption_Rate"].astype(str).str.replace("%", ""),
            errors="coerce"
        )
        count = int(((adoption < 0) | (adoption > 100)).sum())
        if count:
            add("churn", "WARNING", "feature_adoption_out_of_range", count)

    if "Churn_Risk_Score" in df.columns:
        add(
            "churn", "REVIEW", "possible_target_leakage",
            "Churn_Risk_Score requires investigation before model training."
        )


def validate_json_sources():
    folders = {
        "sample_lab": RAW / "sample_lab",
        "benchmarks": RAW / "benchmarks"
    }

    for source, folder in folders.items():
        files = list(folder.glob("*.json"))
        if not files:
            add(source, "ERROR", "file", "No JSON file found")
            continue

        for path in files:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))

                if source == "sample_lab":
                    sensitive = []
                    hints = (
                        "password", "token", "apikey", "api_key",
                        "cvv", "card_number", "secret"
                    )

                    def scan_keys(obj, prefix=""):
                        if isinstance(obj, dict):
                            for key, value in obj.items():
                                full = f"{prefix}.{key}" if prefix else key
                                if any(h in key.lower() for h in hints):
                                    sensitive.append(full)
                                scan_keys(value, full)
                        elif isinstance(obj, list):
                            for item in obj[:2]:
                                scan_keys(item, prefix)

                    scan_keys(data)
                    add(
                        source, "REVIEW", "sensitive_fields",
                        f"Sensitive-looking field names: {sorted(set(sensitive))}"
                    )

                    if isinstance(data, dict):
                        summary.append({
                            "source": source,
                            "collections": {
                                k: len(v) for k, v in data.items()
                                if isinstance(v, list)
                            }
                        })

                else:
                    rows = data.get("rows", []) if isinstance(data, dict) else []
                    summary.append({
                        "source": source,
                        "benchmark_records": len(rows),
                        "license": data.get("license"),
                        "provider": data.get("source")
                    })

                    if not rows:
                        add(source, "WARNING", "benchmark_rows",
                            "No benchmark rows found")

            except Exception as exc:
                add(source, "ERROR", "json_read", exc)


def main():
    print("Starting HORIZON data validation...")

    load_primary()
    validate_churn()
    validate_json_sources()

    report = {
        "project": "HORIZON",
        "summary": summary,
        "issues": issues,
        "issue_count": len(issues)
    }

    json_path = OUT / "data_quality_report.json"
    md_path = OUT / "data_quality_report.md"

    json_path.write_text(
        json.dumps(report, indent=2, default=str),
        encoding="utf-8"
    )

    lines = [
        "# HORIZON — Data Quality Report",
        "",
        f"Total findings: {len(issues)}",
        "",
        "## Dataset summary",
        "",
        "```json",
        json.dumps(summary, indent=2, default=str),
        "```",
        "",
        "## Findings",
        ""
    ]

    for item in issues:
        lines.append(
            f"- **{item['severity']} | {item['source']} | "
            f"{item['check']}**: {item['detail']}"
        )

    if not issues:
        lines.append("No issues detected by these checks.")

    md_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"Validation completed. Findings: {len(issues)}")
    print(f"Report: {md_path}")
    print(f"JSON: {json_path}")


if __name__ == "__main__":
    main()
