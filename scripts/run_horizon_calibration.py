from pathlib import Path
import json
import re
import warnings

import joblib
import numpy as np
import pandas as pd

from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    log_loss,
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
OUT = ROOT / "data" / "processed" / "calibration_experiment"
MODEL_DIR = ROOT / "models"
RANDOM_STATE = 42


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
        raise ValueError("No approved model features found.")

    return df[numeric + categorical].copy(), df["is_churned"], numeric, categorical


def build_base_pipeline(numeric, categorical):
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

    preprocessor = ColumnTransformer(transformers=transformers)
    estimator = LogisticRegression(
        max_iter=2500,
        class_weight="balanced",
        random_state=RANDOM_STATE,
    )
    return Pipeline([
        ("preprocessor", preprocessor),
        ("model", estimator),
    ])


def metrics_at_threshold(y, probabilities, threshold):
    pred = (probabilities >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {
        "threshold": float(threshold),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
        "customers_flagged": int(pred.sum()),
        "true_positive": int(tp),
        "false_positive": int(fp),
        "false_negative": int(fn),
        "true_negative": int(tn),
    }


def calibration_table(y, probabilities, bins=10):
    frame = pd.DataFrame({
        "actual": np.asarray(y),
        "predicted_probability": probabilities,
    })
    frame["bin"] = pd.qcut(
        frame["predicted_probability"],
        q=bins,
        duplicates="drop",
    )
    table = frame.groupby("bin", observed=True).agg(
        customers=("actual", "size"),
        mean_predicted_probability=("predicted_probability", "mean"),
        observed_churn_rate=("actual", "mean"),
        churned_customers=("actual", "sum"),
    ).reset_index()
    table["bin"] = table["bin"].astype(str)
    return table


def top_lift(y, probabilities):
    actual = np.asarray(y)
    order = np.argsort(-probabilities)
    prevalence = float(actual.mean())
    result = {}
    for pct in (1, 5, 10, 20):
        count = max(1, int(np.ceil(len(actual) * pct / 100)))
        selected = actual[order[:count]]
        rate = float(selected.mean())
        result[f"top_{pct}_percent"] = {
            "customers": int(count),
            "churned_customers": int(selected.sum()),
            "observed_churn_rate_pct": rate * 100,
            "lift": rate / prevalence if prevalence else None,
        }
    return result


def probability_metrics(y, probabilities):
    return {
        "pr_auc_average_precision": float(average_precision_score(y, probabilities)),
        "roc_auc": float(roc_auc_score(y, probabilities)),
        "brier_score": float(brier_score_loss(y, probabilities)),
        "log_loss": float(log_loss(y, probabilities, labels=[0, 1])),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 68)
    print("HORIZON — SIGMOID PROBABILITY CALIBRATION EXPERIMENT")
    print("=" * 68)

    X, y, numeric, categorical = load_data()

    # Recreate the same stratified 60/20/20 split used for final model validation.
    X_train, X_temp, y_train, y_temp = train_test_split(
        X, y, test_size=0.40, random_state=RANDOM_STATE, stratify=y
    )
    X_val, X_test, y_val, y_test = train_test_split(
        X_temp, y_temp, test_size=0.50,
        random_state=RANDOM_STATE, stratify=y_temp
    )

    print(
        f"Rows: {len(X)} | Train: {len(X_train)} | "
        f"Validation: {len(X_val)} | Test: {len(X_test)}"
    )
    print("Calibration: sigmoid (Platt scaling), fitted using 5-fold CV on training data.")
    print("Validation selects the calibrated threshold; test remains untouched.")

    base = build_base_pipeline(numeric, categorical)
    calibrated = CalibratedClassifierCV(
        estimator=base,
        method="sigmoid",
        cv=5,
        ensemble=True,
    )

    print("\nFitting calibrated model...")
    calibrated.fit(X_train, y_train)

    val_prob = calibrated.predict_proba(X_val)[:, 1]
    test_prob = calibrated.predict_proba(X_test)[:, 1]

    # Choose threshold on validation only using F1.
    val_thresholds = []
    for threshold in np.round(np.arange(0.01, 0.501, 0.005), 3):
        val_thresholds.append(
            metrics_at_threshold(y_val, val_prob, threshold)
        )

    val_table = pd.DataFrame(val_thresholds)
    val_table.to_csv(OUT / "calibrated_validation_thresholds.csv", index=False)

    best = sorted(
        val_thresholds,
        key=lambda r: (r["f1"], r["precision"], r["threshold"]),
        reverse=True,
    )[0]
    selected_threshold = best["threshold"]

    # Compare uncalibrated and calibrated probabilities on the same untouched test set.
    uncalibrated_path = MODEL_DIR / "horizon_churn_logistic_no_payment_status.joblib"
    uncalibrated_test_prob = None
    uncalibrated_metrics = None

    if uncalibrated_path.exists():
        uncalibrated_model = joblib.load(uncalibrated_path)
        uncalibrated_test_prob = uncalibrated_model.predict_proba(X_test)[:, 1]
        uncalibrated_metrics = probability_metrics(y_test, uncalibrated_test_prob)

    calibrated_metrics = probability_metrics(y_test, test_prob)
    calibrated_threshold_metrics = metrics_at_threshold(
        y_test, test_prob, selected_threshold
    )

    calibration = calibration_table(y_test, test_prob)
    calibration.to_csv(OUT / "calibrated_test_bins.csv", index=False)

    lift = top_lift(y_test, test_prob)

    # Save the calibrated artifact separately; do not overwrite the uncalibrated baseline.
    calibrated_path = MODEL_DIR / "horizon_churn_logistic_no_payment_status_calibrated.joblib"
    joblib.dump(calibrated, calibrated_path)

    report = {
        "project": "HORIZON",
        "experiment": "sigmoid_probability_calibration",
        "calibration_method": "sigmoid (Platt scaling)",
        "calibration_fit": "5-fold cross-validation on training partition only",
        "split": {
            "method": "stratified 60/20/20 train/validation/test",
            "random_state": RANDOM_STATE,
            "train_rows": int(len(X_train)),
            "validation_rows": int(len(X_val)),
            "test_rows": int(len(X_test)),
            "test_churned": int(y_test.sum()),
            "test_churn_rate_pct": float(y_test.mean() * 100),
        },
        "features": {
            "numeric": numeric,
            "categorical": categorical,
            "excluded": [
                "payment_status",
                "churn_risk_score",
                "customer_id",
                "company_name",
                "signup_date",
                "last_active_date",
            ],
        },
        "uncalibrated_test_probability_metrics": uncalibrated_metrics,
        "calibrated_test_probability_metrics": calibrated_metrics,
        "calibrated_threshold_selection": {
            "method": "maximum F1 on validation partition",
            "selected_threshold": selected_threshold,
            "validation_metrics": best,
            "final_test_metrics_at_selected_threshold": calibrated_threshold_metrics,
        },
        "calibrated_test_top_score_lift": lift,
        "calibration_bins_file": "calibrated_test_bins.csv",
        "model_file": str(calibrated_path.relative_to(ROOT)),
        "cautions": [
            "Calibration is assessed on a synthetic dataset.",
            "The test set is held out from model fitting and threshold selection.",
            "Sigmoid calibration can improve probability reliability but does not establish production validity.",
            "Payment status remains excluded because its measurement timing is unknown.",
            "The selected threshold optimizes F1, not a documented business cost function.",
        ],
    }

    (OUT / "calibration_experiment_report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("\n" + "=" * 68)
    print("TEST-SET PROBABILITY METRIC COMPARISON")
    print("=" * 68)
    if uncalibrated_metrics:
        print("Uncalibrated:", json.dumps(uncalibrated_metrics, indent=2))
    else:
        print("Uncalibrated model file not found; comparison skipped.")
    print("Calibrated:", json.dumps(calibrated_metrics, indent=2))

    print("\nSelected calibrated threshold:", selected_threshold)
    print("Validation metrics:", json.dumps(best, indent=2))
    print("\nCalibrated test metrics at selected threshold:")
    print(json.dumps(calibrated_threshold_metrics, indent=2))

    print("\nCalibrated test bins:")
    print(calibration.to_string(index=False))

    print("\nTop-score lift:")
    print(json.dumps(lift, indent=2))

    print("\nSaved calibrated model:")
    print(calibrated_path)
    print("\nReports saved to:")
    print(OUT)
    print("\nCALIBRATION EXPERIMENT COMPLETED")


if __name__ == "__main__":
    main()
