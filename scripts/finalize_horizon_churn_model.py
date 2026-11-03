from pathlib import Path
import json
import re
import warnings

import joblib
import numpy as np
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "raw" / "churn" / "MP_Synthetics_50000_Rows.csv"
OUT = ROOT / "data" / "processed" / "final_churn_model"
MODEL_DIR = ROOT / "models"

RANDOM_STATE = 42
BETA = 1.0  # F1 balances precision and recall; change only with a documented business reason.


def snake(value):
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(value).strip())
    return re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()


def load_data():
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Dataset not found: {DATA_FILE}")

    df = pd.read_csv(DATA_FILE)
    df.columns = [snake(c) for c in df.columns]

    if "is_churned" not in df.columns:
        raise ValueError("Target column Is_Churned was not found.")

    df["is_churned"] = pd.to_numeric(df["is_churned"], errors="coerce")
    df = df[df["is_churned"].isin([0, 1])].copy()
    df["is_churned"] = df["is_churned"].astype(int)

    if "feature_adoption_rate" in df.columns:
        values = df["feature_adoption_rate"].astype(str).str.replace("%", "", regex=False)
        values = pd.to_numeric(values, errors="coerce")
        if values.notna().any() and values.max() > 1:
            values = values / 100
        df["feature_adoption_rate"] = values

    numeric = [
        c for c in [
            "monthly_recurring_revenue",
            "active_seats_used",
            "total_seats_allowed",
            "support_tickets_30d",
            "feature_adoption_rate",
        ] if c in df.columns
    ]
    categorical = [
        c for c in [
            "industry",
            "country",
            "company_size",
            "account_manager",
            "plan_tier",
            "billing_cycle",
        ] if c in df.columns
    ]

    if not numeric and not categorical:
        raise ValueError("No approved features found.")

    # payment_status, churn_risk_score, dates and identifiers intentionally excluded.
    features = numeric + categorical
    X = df[features].copy()
    y = df["is_churned"].copy()
    return X, y, numeric, categorical


def build_pipeline(numeric, categorical):
    transformers = []

    if numeric:
        transformers.append((
            "numeric",
            Pipeline([
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
            ]),
            numeric,
        ))

    if categorical:
        transformers.append((
            "categorical",
            Pipeline([
                ("imputer", SimpleImputer(strategy="most_frequent")),
                ("onehot", OneHotEncoder(handle_unknown="ignore")),
            ]),
            categorical,
        ))

    preprocess = ColumnTransformer(transformers=transformers)
    model = LogisticRegression(
        max_iter=2500,
        class_weight="balanced",
        random_state=RANDOM_STATE,
    )
    return Pipeline([("preprocessor", preprocess), ("model", model)])


def threshold_metrics(y, probabilities, threshold):
    predicted = (probabilities >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, predicted, labels=[0, 1]).ravel()
    precision = precision_score(y, predicted, zero_division=0)
    recall = recall_score(y, predicted, zero_division=0)
    f1 = f1_score(y, predicted, zero_division=0)
    return {
        "threshold": float(threshold),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "customers_flagged": int(predicted.sum()),
        "true_positive": int(tp),
        "false_positive": int(fp),
        "false_negative": int(fn),
        "true_negative": int(tn),
    }


def top_lift(y, probabilities):
    y_array = np.asarray(y)
    order = np.argsort(-probabilities)
    prevalence = float(y_array.mean())
    result = {}
    for pct in (1, 5, 10, 20):
        n = max(1, int(np.ceil(len(y_array) * pct / 100)))
        selected = y_array[order[:n]]
        rate = float(selected.mean())
        result[f"top_{pct}_percent"] = {
            "customers": int(n),
            "churned_customers": int(selected.sum()),
            "observed_churn_rate_pct": rate * 100,
            "lift": rate / prevalence if prevalence else None,
        }
    return result


def calibration_bins(y, probabilities, bins=10):
    frame = pd.DataFrame({
        "actual": np.asarray(y),
        "predicted_probability": probabilities,
    })
    # Quantile bins avoid empty equal-width bins with skewed scores.
    frame["bin"] = pd.qcut(
        frame["predicted_probability"],
        q=bins,
        duplicates="drop",
    )
    grouped = frame.groupby("bin", observed=True).agg(
        customers=("actual", "size"),
        mean_predicted_probability=("predicted_probability", "mean"),
        observed_churn_rate=("actual", "mean"),
        churned_customers=("actual", "sum"),
    ).reset_index()
    grouped["bin"] = grouped["bin"].astype(str)
    return grouped


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 66)
    print("HORIZON — FINAL CHURN MODEL VALIDATION")
    print("=" * 66)

    X, y, numeric, categorical = load_data()

    # 60% train, 20% validation for threshold selection, 20% untouched test.
    X_train, X_temp, y_train, y_temp = train_test_split(
        X, y, test_size=0.40, random_state=RANDOM_STATE, stratify=y
    )
    X_val, X_test, y_val, y_test = train_test_split(
        X_temp, y_temp, test_size=0.50,
        random_state=RANDOM_STATE, stratify=y_temp
    )

    print(
        f"Rows: {len(X)} | Train: {len(X_train)} | "
        f"Validation: {len(X_val)} | Final test: {len(X_test)}"
    )
    print(f"Features: {numeric + categorical}")
    print("Excluded: payment_status, churn_risk_score, identifiers and dates")

    pipeline = build_pipeline(numeric, categorical)
    print("\nTraining Logistic Regression...")
    pipeline.fit(X_train, y_train)

    val_prob = pipeline.predict_proba(X_val)[:, 1]
    test_prob = pipeline.predict_proba(X_test)[:, 1]

    # Choose threshold using validation data only; final test remains untouched.
    thresholds = np.round(np.arange(0.05, 0.951, 0.01), 2)
    val_rows = [threshold_metrics(y_val, val_prob, t) for t in thresholds]
    val_table = pd.DataFrame(val_rows)
    val_table.to_csv(OUT / "validation_threshold_metrics.csv", index=False)

    # Maximize validation F1. In a tie, prefer higher precision, then higher threshold.
    best_row = sorted(
        val_rows,
        key=lambda r: (r["f1"], r["precision"], r["threshold"]),
        reverse=True,
    )[0]
    chosen_threshold = best_row["threshold"]

    # Also report common operating points for decision-making.
    common_thresholds = [
        threshold_metrics(y_val, val_prob, t)
        for t in (0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, chosen_threshold)
    ]
    common_table = pd.DataFrame(common_thresholds).drop_duplicates(
        subset=["threshold"]
    ).sort_values("threshold")
    common_table.to_csv(OUT / "validation_selected_thresholds.csv", index=False)

    final_metrics = threshold_metrics(y_test, test_prob, chosen_threshold)
    final_metrics.update({
        "pr_auc_average_precision": float(average_precision_score(y_test, test_prob)),
        "roc_auc": float(roc_auc_score(y_test, test_prob)),
        "brier_score": float(brier_score_loss(y_test, test_prob)),
        "holdout_prevalence_pct": float(y_test.mean() * 100),
    })

    calibration = calibration_bins(y_test, test_prob)
    calibration.to_csv(OUT / "test_calibration_bins.csv", index=False)

    lift = top_lift(y_test, test_prob)

    # Save model artifact and metadata. Threshold is stored separately in metadata.
    model_path = MODEL_DIR / "horizon_churn_logistic_no_payment_status.joblib"
    joblib.dump(pipeline, model_path)

    report = {
        "project": "HORIZON",
        "model": "Logistic Regression",
        "status": "candidate_baseline_pending_business_review",
        "target": "is_churned",
        "feature_policy": {
            "included_numeric": numeric,
            "included_categorical": categorical,
            "excluded": [
                "payment_status",
                "churn_risk_score",
                "customer_id",
                "company_name",
                "signup_date",
                "last_active_date",
            ],
            "reason": (
                "payment_status timing is unverified; churn_risk_score "
                "provenance is unverified; identifiers and dates are excluded."
            ),
        },
        "split": {
            "method": "stratified 60/20/20 train/validation/test",
            "random_state": RANDOM_STATE,
            "train_rows": int(len(X_train)),
            "validation_rows": int(len(X_val)),
            "test_rows": int(len(X_test)),
            "train_churned": int(y_train.sum()),
            "validation_churned": int(y_val.sum()),
            "test_churned": int(y_test.sum()),
        },
        "threshold_selection": {
            "method": "maximum F1 on validation set only",
            "beta": BETA,
            "selected_threshold": chosen_threshold,
            "validation_metrics_at_selected_threshold": best_row,
            "note": (
                "Threshold is a provisional statistical choice. "
                "A business cost/benefit analysis may select a different threshold."
            ),
        },
        "final_untouched_test_metrics": final_metrics,
        "test_top_score_lift": lift,
        "calibration": {
            "brier_score": final_metrics["brier_score"],
            "bins_file": "test_calibration_bins.csv",
            "note": (
                "Brier score and quantile-bin comparison are diagnostic. "
                "No probability calibration adjustment was fitted."
            ),
        },
        "model_file": str(model_path.relative_to(ROOT)),
        "limitations": [
            "Synthetic dataset; not production validated.",
            "payment_status was excluded because its timing is unverified, not because leakage is proven.",
            "Threshold maximizes validation F1 and does not encode business intervention costs.",
            "Observed segment relationships are not causal.",
            "Model probabilities should not be described as calibrated individual churn probabilities without further validation.",
        ],
    }

    (OUT / "final_churn_model_report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("\n" + "=" * 66)
    print("VALIDATION THRESHOLD SELECTION")
    print("=" * 66)
    print(f"Selected threshold (validation F1): {chosen_threshold:.2f}")
    print(
        f"Validation precision: {best_row['precision']:.4f} | "
        f"recall: {best_row['recall']:.4f} | F1: {best_row['f1']:.4f}"
    )

    print("\nSelected validation thresholds:")
    print(common_table.to_string(index=False))

    print("\n" + "=" * 66)
    print("FINAL UNTOUCHED TEST RESULTS")
    print("=" * 66)
    for key, value in final_metrics.items():
        print(f"{key}: {value}")

    print("\nTop-score lift on final test:")
    print(json.dumps(lift, indent=2))

    print("\nCalibration bins:")
    print(calibration.to_string(index=False))

    print("\nSaved model:")
    print(model_path)
    print("\nReports:")
    print(OUT)
    print("\nFINAL MODEL VALIDATION COMPLETED")


if __name__ == "__main__":
    main()
