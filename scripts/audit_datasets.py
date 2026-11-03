
from pathlib import Path
import json
import pandas as pd
from datetime import datetime, date

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUTPUT = ROOT / "data" / "processed"
OUTPUT.mkdir(parents=True, exist_ok=True)

SOURCES = {
    "primary": RAW / "primary",
    "churn": RAW / "churn",
    "sample_lab": RAW / "sample_lab",
    "benchmarks": RAW / "benchmarks",
}

SENSITIVE_HINTS = (
    "password", "passwd", "secret", "token", "api_key",
    "apikey", "cvv", "card_number", "credit_card",
    "private_key", "authorization"
)


def safe_value(value):
    if pd.isna(value):
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def inspect_dataframe(df, name):
    columns = []

    for col in df.columns:
        series = df[col]
        columns.append({
            "name": str(col),
            "dtype": str(series.dtype),
            "missing": int(series.isna().sum()),
            "missing_pct": round(float(series.isna().mean() * 100), 2),
            "unique": int(series.nunique(dropna=True)),
            "sensitive_name_warning": any(
                hint in str(col).lower() for hint in SENSITIVE_HINTS
            ),
        })

    numeric_summary = {}
    for col in df.select_dtypes(include="number").columns:
        numeric_summary[str(col)] = {
            "min": safe_value(df[col].min()),
            "max": safe_value(df[col].max()),
            "mean": safe_value(df[col].mean()),
            "median": safe_value(df[col].median()),
        }

    date_candidates = {}
    for col in df.columns:
        if any(word in str(col).lower() for word in
               ("date", "time", "created", "updated", "signup")):
            parsed = pd.to_datetime(df[col], errors="coerce")
            valid = parsed.dropna()
            if not valid.empty:
                date_candidates[str(col)] = {
                    "valid_dates": int(len(valid)),
                    "min": str(valid.min()),
                    "max": str(valid.max()),
                }

    return {
        "name": name,
        "rows": int(len(df)),
        "columns_count": int(len(df.columns)),
        "duplicate_rows": int(df.duplicated().sum()),
        "columns": columns,
        "numeric_summary": numeric_summary,
        "date_candidates": date_candidates,
    }


def inspect_json(value, name):
    result = {
        "name": name,
        "json_type": type(value).__name__,
        "top_level_keys": [],
        "collections": [],
        "sensitive_key_warnings": [],
    }

    if isinstance(value, dict):
        result["top_level_keys"] = list(map(str, value.keys()))

        for key, item in value.items():
            if any(hint in str(key).lower() for hint in SENSITIVE_HINTS):
                result["sensitive_key_warnings"].append(str(key))

            if isinstance(item, list):
                entry = {
                    "collection": str(key),
                    "records": len(item),
                    "sample_fields": [],
                }
                if item and isinstance(item[0], dict):
                    entry["sample_fields"] = list(map(str, item[0].keys()))
                    for field in item[0].keys():
                        if any(hint in str(field).lower()
                               for hint in SENSITIVE_HINTS):
                            result["sensitive_key_warnings"].append(
                                f"{key}.{field}"
                            )
                result["collections"].append(entry)

    elif isinstance(value, list):
        result["records"] = len(value)
        if value and isinstance(value[0], dict):
            result["sample_fields"] = list(map(str, value[0].keys()))

    result["sensitive_key_warnings"] = sorted(
        set(result["sensitive_key_warnings"])
    )
    return result


def find_files(folder):
    if not folder.exists():
        return []
    return [
        p for p in folder.iterdir()
        if p.is_file() and not p.name.startswith("~$") and not p.name.startswith(".")
    ]



def main():
    report = {
        "project": "HORIZON",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "datasets": [],
        "errors": [],
    }

    for source_name, folder in SOURCES.items():
        files = find_files(folder)

        if not files:
            report["errors"].append(
                f"No files found in {folder.relative_to(ROOT)}"
            )
            continue

        for path in files:
            try:
                suffix = path.suffix.lower()

                if suffix == ".csv":
                    df = pd.read_csv(path, low_memory=False)
                    result = inspect_dataframe(df, path.name)

                elif suffix in (".xlsx", ".xls"):
                    excel = pd.ExcelFile(path)
                    sheets = []
                    for sheet in excel.sheet_names:
                        df = pd.read_excel(path, sheet_name=sheet)
                        sheet_result = inspect_dataframe(
                            df, f"{path.name} :: {sheet}"
                        )
                        sheets.append(sheet_result)

                    result = {
                        "name": path.name,
                        "file_type": "Excel",
                        "sheets": sheets,
                    }

                elif suffix == ".json":
                    with path.open("r", encoding="utf-8") as f:
                        value = json.load(f)
                    result = inspect_json(value, path.name)

                else:
                    report["errors"].append(
                        f"Unsupported file: {path.name}"
                    )
                    continue

                result["source_folder"] = source_name
                report["datasets"].append(result)
                print(f"[OK] Audited {source_name}/{path.name}")

            except Exception as exc:
                report["errors"].append(
                    f"{path.name}: {type(exc).__name__}: {exc}"
                )
                print(f"[ERROR] {path.name}: {exc}")

    json_path = OUTPUT / "dataset_audit.json"
    md_path = OUTPUT / "dataset_audit.md"

    json_path.write_text(
        json.dumps(report, indent=2, default=str),
        encoding="utf-8"
    )

    lines = [
        "# HORIZON — Dataset Audit",
        "",
        f"Generated: {report['generated_at']}",
        "",
    ]

    for dataset in report["datasets"]:
        lines.extend([
            f"## {dataset['name']}",
            f"Source folder: {dataset.get('source_folder', 'Unknown')}",
        ])

        if "rows" in dataset:
            lines.extend([
                f"- Rows: {dataset['rows']:,}",
                f"- Columns: {dataset['columns_count']}",
                f"- Duplicate rows: {dataset['duplicate_rows']:,}",
                "",
                "| Column | Type | Missing | Missing % | Unique | Sensitive-name warning |",
                "|---|---|---:|---:|---:|---|",
            ])

            for col in dataset["columns"]:
                lines.append(
                    f"| {col['name']} | {col['dtype']} | "
                    f"{col['missing']} | {col['missing_pct']}% | "
                    f"{col['unique']} | {col['sensitive_name_warning']} |"
                )

            if dataset["date_candidates"]:
                lines.extend(["", "### Date candidates"])
                for col, info in dataset["date_candidates"].items():
                    lines.append(
                        f"- **{col}**: {info['min']} to {info['max']} "
                        f"({info['valid_dates']} valid values)"
                    )

        elif "sheets" in dataset:
            for sheet in dataset["sheets"]:
                lines.extend([
                    "",
                    f"### {sheet['name']}",
                    f"- Rows: {sheet['rows']:,}",
                    f"- Columns: {sheet['columns_count']}",
                    f"- Duplicate rows: {sheet['duplicate_rows']:,}",
                    "",
                    "| Column | Type | Missing | Missing % | Unique |",
                    "|---|---|---:|---:|---:|",
                ])

                for col in sheet["columns"]:
                    lines.append(
                        f"| {col['name']} | {col['dtype']} | "
                        f"{col['missing']} | {col['missing_pct']}% | "
                        f"{col['unique']} |"
                    )

                if sheet["date_candidates"]:
                    lines.extend(["", "#### Date candidates"])
                    for col, info in sheet["date_candidates"].items():
                        lines.append(
                            f"- **{col}**: {info['min']} to {info['max']}"
                        )

        else:
            lines.extend([
                f"- JSON type: {dataset.get('json_type')}",
                f"- Top-level keys: {dataset.get('top_level_keys', [])}",
            ])
            for collection in dataset.get("collections", []):
                lines.append(
                    f"- Collection `{collection['collection']}`: "
                    f"{collection['records']} records"
                )

        warnings = dataset.get("sensitive_key_warnings", [])
        if warnings:
            lines.extend([
                "",
                "**Sensitive-looking field names detected:**",
                ", ".join(warnings),
            ])

        lines.append("")

    if report["errors"]:
        lines.extend(["## Audit errors"])
        lines.extend(f"- {error}" for error in report["errors"])

    md_path.write_text("\n".join(lines), encoding="utf-8")

    print("\nAudit completed.")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {md_path}")
    print(f"Errors: {len(report['errors'])}")


if __name__ == "__main__":
    main()
