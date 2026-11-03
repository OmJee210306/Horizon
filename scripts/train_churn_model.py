"""
HORIZON - Exploratory churn modelling pipeline
Run from the project root:
    python scripts/train_churn_model.py

This model uses the independent synthetic churn dataset only.
It does not join records to the primary SaaS billing dataset.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "raw" / "churn" / "MP_Synthetics_50000_Rows.csv"
MODEL_DIR = ROOT / "models"
REPORT_DIR = ROOT / "data" / "processed" / "churn_model"


def normalize_column_name(name: str) -> str:
    """Convert source headers to predictable snake_case."""
    name = str(name).strip()
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    name = re.sub(r"[^A-Za-z0-9]+", "_", name)
    return name.strip("_").lower()


def main() -> None:
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"Could not find churn CSV:\n{DATA_PATH}\n"
            "Check that the original file is in data/raw/churn/."
        )

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(DATA_PATH)
    df.columns = [normalize_column_name(c) for c in df.columns]

    target = "is_churned"
    required = [
        target,
        "industry",
        "country",
        "company_size",
        "account_manager",
        "plan_tier",
        "billing_cycle",
        "monthly_recurring_revenue",
        "payment_status",
        "active_seats_used",
        "total_seats_allowed",
        "support_tickets_30d",
        "feature_adoption_rate",
    ]
    missing = sorted(set(required) - set(df.columns))
    if missing:
        raise ValueError(
            "The churn CSV is missing expected columns: "
            + ", ".join(missing)
            + f"\nColumns found: {list(df.columns)}"
        )

    # Preserve source row count and report known date-quality issue.
    original_rows = len(df)
    date_anomaly_count = None
    if {"signup_date", "last_active_date"}.issubset(df.columns):
        signup = pd.to_datetime(df["signup_date"], errors="coerce")
        last_active = pd.to_datetime(df["last_active_date"], errors="coerce")
        date_anomaly_count = int((last_active < signup).sum())

    # Parse the target and remove only rows without a usable target.
    df[target] = pd.to_numeric(df[target], errors="coerce")
    before_target_filter = len(df)
    df = df[df[target].isin([0, 1])].copy()
    removed_missing_or_invalid_target = before_target_filter - len(df)
    df[target] = df[target].astype(int)

    # Percent strings such as "72%" become numeric proportions (0.72).
    adoption = (
        df["feature_adoption_rate"]
        .astype(str)
        .str.strip()
        .str.replace("%", "", regex=False)
    )
    df["feature_adoption_rate"] = pd.to_numeric(adoption, errors="coerce")
    if df["feature_adoption_rate"].dropna().gt(1).any():
        df["feature_adoption_rate"] = df["feature_adoption_rate"] / 100.0

    numeric_features = [
        "monthly_recurring_revenue",
        "active_seats_used",
        "total_seats_allowed",
        "support_tickets_30d",
        "feature_adoption_rate",
    ]
    categorical_features = [
        "industry",
        "country",
        "company_size",
        "account_manager",
        "plan_tier",
        "billing_cycle",
        "payment_status",
    ]

    for col in numeric_features:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in categorical_features:
        df[col] = df[col].astype("string").fillna("Unknown").astype(str)

    # Deliberately excluded:
    # - customer_id/company_name: identifiers, not useful generalizable predictors
    # - churn_risk_score: possible target leakage
    # - last_active_date: its timing relative to the churn outcome is unverified
    # - signup_date: no defensible prediction snapshot/reference date is supplied
    feature_columns = numeric_features + categorical_features
    X = df[feature_columns].copy()
    y = df[target].copy()

    class_counts = y.value_counts().sort_index().to_dict()
    if len(class_counts) != 2 or min(class_counts.values()) < 2:
        raise ValueError(f"Both target classes need at least 2 rows. Counts: {class_counts}")

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.20,
        random_state=42,
        stratify=y,
    )

    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]
    )
    preprocessor = ColumnTransformer(
        transformers=[
            ("numeric", numeric_pipeline, numeric_features),
            ("categorical", categorical_pipeline, categorical_features),
        ],
        remainder="drop",
    )

    candidates = {
        "logistic_regression": LogisticRegression(
            max_iter=2000,
            class_weight="balanced",
            random_state=42,
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=250,
            max_depth=14,
            min_samples_leaf=5,
            class_weight="balanced_subsample",
            random_state=42,
            n_jobs=-1,
        ),
    }

    results = {}
    fitted_pipelines = {}

    for name, estimator in candidates.items():
        pipeline = Pipeline(
            steps=[
                ("preprocessor", preprocessor),
                ("model", estimator),
            ]
        )
        print(f"\nTraining {name} ...")
        pipeline.fit(X_train, y_train)

        probabilities = pipeline.predict_proba(X_test)[:, 1]
        predictions = (probabilities >= 0.50).astype(int)

        metrics = {
            "average_precision_pr_auc": float(average_precision_score(y_test, probabilities)),
            "roc_auc": float(roc_auc_score(y_test, probabilities)),
            "precision_at_0_50": float(precision_score(y_test, predictions, zero_division=0)),
            "recall_at_0_50": float(recall_score(y_test, predictions, zero_division=0)),
            "f1_at_0_50": float(f1_score(y_test, predictions, zero_division=0)),
            "accuracy_at_0_50": float(accuracy_score(y_test, predictions)),
            "confusion_matrix_labels_0_1": confusion_matrix(
                y_test, predictions, labels=[0, 1]
            ).tolist(),
            "classification_report": classification_report(
                y_test, predictions, labels=[0, 1],
                target_names=["not_churned", "churned"],
                output_dict=True,
                zero_division=0,
            ),
        }
        results[name] = metrics
        fitted_pipelines[name] = pipeline
        print(
            f"{name}: PR-AUC={metrics['average_precision_pr_auc']:.4f}, "
            f"ROC-AUC={metrics['roc_auc']:.4f}, "
            f"precision={metrics['precision_at_0_50']:.4f}, "
            f"recall={metrics['recall_at_0_50']:.4f}, "
            f"F1={metrics['f1_at_0_50']:.4f}"
        )

    # Select using PR-AUC because the positive class is rare.
    best_name = max(
        results,
        key=lambda model_name: results[model_name]["average_precision_pr_auc"],
    )
    best_pipeline = fitted_pipelines[best_name]
    model_path = MODEL_DIR / "churn_model.joblib"
    joblib.dump(best_pipeline, model_path)

    best_probabilities = best_pipeline.predict_proba(X_test)[:, 1]
    prediction_output = pd.DataFrame(
        {
            "actual_is_churned": y_test.to_numpy(),
            "predicted_churn_probability": best_probabilities,
            "predicted_is_churned_at_0_50": (best_probabilities >= 0.50).astype(int),
        },
        index=y_test.index,
    ).sort_index()
    prediction_output.to_csv(REPORT_DIR / "holdout_predictions.csv", index_label="source_row")

    report = {
        "project": "HORIZON",
        "purpose": "Exploratory churn modelling on an independent synthetic dataset",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_file": str(DATA_PATH.relative_to(ROOT)),
        "source_rows": original_rows,
        "rows_used": int(len(df)),
        "rows_removed_for_missing_or_invalid_target": int(removed_missing_or_invalid_target),
        "target": target,
        "class_counts_0_not_churned_1_churned": {
            str(k): int(v) for k, v in class_counts.items()
        },
        "churn_prevalence": float(y.mean()),
        "train_rows": int(len(X_train)),
        "test_rows": int(len(X_test)),
        "split": "80/20 stratified; random_state=42",
        "date_anomaly_last_active_before_signup": date_anomaly_count,
        "features_used": feature_columns,
        "excluded_fields_and_reasons": {
            "customer_id": "Identifier; excluded to reduce memorization",
            "company_name": "Identifier-like field; excluded to reduce memorization",
            "churn_risk_score": "Possible target leakage; excluded pending provenance review",
            "last_active_date": "Outcome timing is unverified; excluded to reduce temporal leakage",
            "signup_date": "No defensible prediction snapshot/reference date supplied",
        },
        "threshold_for_reported_classification_metrics": 0.50,
        "model_selection_metric": "average_precision_pr_auc",
        "models": results,
        "selected_model": best_name,
        "model_artifact": str(model_path.relative_to(ROOT)),
        "limitations": [
            "The churn dataset is synthetic and independent of the primary SaaS billing dataset.",
            "Results are exploratory and are not evidence of production performance.",
            "The holdout comparison is an initial evaluation; a later untouched validation set or temporal validation is recommended.",
            "The 0.50 threshold is a reporting baseline, not a business-optimized intervention threshold.",
            "PR-AUC should be compared with the positive-class prevalence baseline.",
        ],
    }

    report_path = REPORT_DIR / "model_evaluation.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n" + "=" * 62)
    print(f"Selected model: {best_name}")
    print(f"PR-AUC: {results[best_name]['average_precision_pr_auc']:.4f}")
    print(f"ROC-AUC: {results[best_name]['roc_auc']:.4f}")
    print(f"Model saved: {model_path}")
    print(f"Evaluation saved: {report_path}")
    print(f"Holdout predictions saved: {REPORT_DIR / 'holdout_predictions.csv'}")
    print("=" * 62)


if __name__ == "__main__":
    main()
