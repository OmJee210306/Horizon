"""
HORIZON - Churn threshold and prioritization analysis
Recreates the original stratified holdout split and evaluates the saved model.
Run from project root:
    python scripts/analyze_churn_thresholds.py
"""

import re
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "raw" / "churn" / "MP_Synthetics_50000_Rows.csv"
MODEL_PATH = ROOT / "models" / "churn_model.joblib"
OUT_DIR = ROOT / "data" / "processed" / "churn_model"


def normalize_column_name(name):
    name = str(name).strip()
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    name = re.sub(r"[^A-Za-z0-9]+", "_", name)
    return name.strip("_").lower()


def main():
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {DATA_PATH}")
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Trained model not found: {MODEL_PATH}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(DATA_PATH)
    df.columns = [normalize_column_name(c) for c in df.columns]

    target = "is_churned"
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
    feature_columns = numeric_features + categorical_features

    df[target] = pd.to_numeric(df[target], errors="coerce")
    df = df[df[target].isin([0, 1])].copy()
    df[target] = df[target].astype(int)

    adoption = (
        df["feature_adoption_rate"]
        .astype(str)
        .str.strip()
        .str.replace("%", "", regex=False)
    )
    df["feature_adoption_rate"] = pd.to_numeric(adoption, errors="coerce")
    if df["feature_adoption_rate"].dropna().gt(1).any():
        df["feature_adoption_rate"] /= 100.0

    for col in numeric_features:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in categorical_features:
        df[col] = df[col].astype("string").fillna("Unknown").astype(str)

    X = df[feature_columns]
    y = df[target]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )

    model = joblib.load(MODEL_PATH)
    probabilities = model.predict_proba(X_test)[:, 1]
    prevalence = float(y_test.mean())

    rows = []
    for threshold in np.arange(0.01, 1.00, 0.01):
        predictions = (probabilities >= threshold).astype(int)
        tn, fp, fn, tp = confusion_matrix(
            y_test, predictions, labels=[0, 1]
        ).ravel()
        rows.append({
            "threshold": round(float(threshold), 2),
            "precision": float(precision_score(y_test, predictions, zero_division=0)),
            "recall": float(recall_score(y_test, predictions, zero_division=0)),
            "f1": float(f1_score(y_test, predictions, zero_division=0)),
            "true_positives": int(tp),
            "false_positives": int(fp),
            "false_negatives": int(fn),
            "true_negatives": int(tn),
            "customers_flagged": int(tp + fp),
        })

    threshold_df = pd.DataFrame(rows)
    threshold_df.to_csv(OUT_DIR / "threshold_analysis.csv", index=False)

    # Rank customers by predicted churn probability; report top 1%, 5%, 10%, 20%.
    ranked = pd.DataFrame({
        "source_row": y_test.index,
        "actual_is_churned": y_test.to_numpy(),
        "predicted_churn_probability": probabilities,
    }).sort_values("predicted_churn_probability", ascending=False)

    top_rows = []
    n = len(ranked)
    for fraction in [0.01, 0.05, 0.10, 0.20]:
        count = max(1, int(np.ceil(n * fraction)))
        segment = ranked.head(count)
        segment_rate = float(segment["actual_is_churned"].mean())
        top_rows.append({
            "top_fraction": fraction,
            "customers_reviewed": count,
            "churned_customers_found": int(segment["actual_is_churned"].sum()),
            "churn_rate_in_segment": segment_rate,
            "overall_test_churn_rate": prevalence,
            "lift_over_test_baseline": (
                segment_rate / prevalence if prevalence > 0 else None
            ),
        })

    top_df = pd.DataFrame(top_rows)
    top_df.to_csv(OUT_DIR / "top_customer_lift.csv", index=False)
    ranked.to_csv(OUT_DIR / "ranked_holdout_customers.csv", index=False)

    print("\nMODEL RANKING QUALITY")
    print(f"Holdout prevalence: {prevalence:.4%}")
    print(f"PR-AUC: {average_precision_score(y_test, probabilities):.4f}")
    print(f"ROC-AUC: {roc_auc_score(y_test, probabilities):.4f}")

    print("\nTHRESHOLD OPTIONS")
    selected_thresholds = [0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70]
    display = threshold_df[
        threshold_df["threshold"].isin(selected_thresholds)
    ][[
        "threshold", "precision", "recall", "f1",
        "customers_flagged", "true_positives", "false_positives",
        "false_negatives"
    ]]
    print(display.to_string(index=False))

    print("\nTOP-RANKED CUSTOMER SEGMENTS")
    print(top_df.to_string(index=False))

    print("\nSaved:")
    print(OUT_DIR / "threshold_analysis.csv")
    print(OUT_DIR / "top_customer_lift.csv")
    print(OUT_DIR / "ranked_holdout_customers.csv")
    print("\nNote: This is a synthetic-data evaluation. Threshold choice needs a business cost/benefit assumption.")


if __name__ == "__main__":
    main()
