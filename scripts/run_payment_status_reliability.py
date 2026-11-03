from pathlib import Path
import json
import re
import warnings

import numpy as np
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
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
DATA_FILE = (
    ROOT / "data" / "raw" / "churn"
    / "MP_Synthetics_50000_Rows.csv"
)
OUT = ROOT / "data" / "processed" / "model_reliability"

RANDOM_STATE = 42
TEST_SIZE = 0.20
THRESHOLD = 0.50


def snake(value):
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(value).strip())
    return re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()


def load_and_prepare():
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Dataset not found: {DATA_FILE}")

    df = pd.read_csv(DATA_FILE)
    df.columns = [snake(c) for c in df.columns]

    if "is_churned" not in df.columns:
        raise ValueError("Required target column 'Is_Churned' was not found.")

    df["is_churned"] = pd.to_numeric(df["is_churned"], errors="coerce")
    df = df[df["is_churned"].isin([0, 1])].copy()
    df["is_churned"] = df["is_churned"].astype(int)

    # Convert percentage strings such as "65%" into numeric proportions.
    if "feature_adoption_rate" in df.columns:
        adoption = (
            df["feature_adoption_rate"]
            .astype(str)
            .str.replace("%", "", regex=False)
        )
        adoption = pd.to_numeric(adoption, errors="coerce")
        if adoption.notna().any() and adoption.max() > 1:
            adoption = adoption / 100
        df["feature_adoption_rate"] = adoption

    # Exclude identifiers and fields whose timing/provenance is unsafe.
    numeric_candidates = [
        "monthly_recurring_revenue",
        "active_seats_used",
        "total_seats_allowed",
        "support_tickets_30d",
        "feature_adoption_rate",
    ]
    categorical_candidates = [
        "industry",
        "country",
        "company_size",
        "account_manager",
        "plan_tier",
        "billing_cycle",
        "payment_status",
    ]

    numeric_features = [c for c in numeric_candidates if c in df.columns]
    categorical_features = [c for c in categorical_candidates if c in df.columns]

    if not numeric_features and not categorical_features:
        raise ValueError("No approved model features were found in the dataset.")

    return df, numeric_features, categorical_features


def make_pipeline(numeric_features, categorical_features, model_name):
    transformers = []

    if numeric_features:
        numeric_pipe = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ])
        transformers.append(("numeric", numeric_pipe, numeric_features))

    if categorical_features:
        categorical_pipe = Pipeline([
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ])
        transformers.append(("categorical", categorical_pipe, categorical_features))

    preprocessor = ColumnTransformer(
        transformers=transformers,
        remainder="drop",
    )

    if model_name == "logistic_regression":
        estimator = LogisticRegression(
            max_iter=2000,
            class_weight="balanced",
            random_state=RANDOM_STATE,
        )
    elif model_name == "random_forest":
        estimator = RandomForestClassifier(
            n_estimators=400,
            min_samples_leaf=5,
            class_weight="balanced_subsample",
            random_state=RANDOM_STATE,
            n_jobs=-1,
        )
    else:
        raise ValueError(f"Unknown model: {model_name}")

    return Pipeline([
        ("preprocessor", preprocessor),
        ("model", estimator),
    ])


def evaluate(y_true, probabilities, threshold):
    predictions = (probabilities >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(
        y_true, predictions, labels=[0, 1]
    ).ravel()

    prevalence = float(np.mean(y_true))
    order = np.argsort(-probabilities)
    top_lift = {}

    for fraction in (0.01, 0.05, 0.10, 0.20):
        count = max(1, int(np.ceil(len(y_true) * fraction)))
        selected = y_true.iloc[order[:count]]
        selected_rate = float(selected.mean())
        top_lift[f"top_{int(fraction * 100)}pct"] = {
            "customers_flagged": int(count),
            "churned_customers": int(selected.sum()),
            "observed_churn_rate_pct": selected_rate * 100,
            "lift_vs_holdout_prevalence": (
                selected_rate / prevalence if prevalence > 0 else None
            ),
        }

    return {
        "pr_auc_average_precision": float(average_precision_score(y_true, probabilities)),
        "roc_auc": float(roc_auc_score(y_true, probabilities)),
        "precision_at_threshold": float(precision_score(
            y_true, predictions, zero_division=0
        )),
        "recall_at_threshold": float(recall_score(
            y_true, predictions, zero_division=0
        )),
        "f1_at_threshold": float(f1_score(
            y_true, predictions, zero_division=0
        )),
        "threshold": float(threshold),
        "confusion_matrix": {
            "true_negative": int(tn),
            "false_positive": int(fp),
            "false_negative": int(fn),
            "true_positive": int(tp),
        },
        "top_score_lift": top_lift,
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("=" * 64)
    print("HORIZON — PAYMENT STATUS MODEL RELIABILITY TEST")
    print("=" * 64)

    df, numeric_features, categorical_features = load_and_prepare()
    y = df["is_churned"]

    # One fixed stratified split is reused for every experiment.
    train_idx, test_idx = train_test_split(
        np.arange(len(df)),
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
        stratify=y,
    )

    X_all = df[numeric_features + categorical_features].copy()
    X_without_payment = df[
        numeric_features
        + [c for c in categorical_features if c != "payment_status"]
    ].copy()

    y_train = y.iloc[train_idx]
    y_test = y.iloc[test_idx]

    experiments = [
        ("with_payment_status", X_all, categorical_features),
        (
            "without_payment_status",
            X_without_payment,
            [c for c in categorical_features if c != "payment_status"],
        ),
    ]

    all_results = []
    prediction_frames = []

    for model_name in ("logistic_regression", "random_forest"):
        for experiment_name, X, cats in experiments:
            print(f"\nTraining {model_name} — {experiment_name}...")

            pipeline = make_pipeline(numeric_features, cats, model_name)
            pipeline.fit(X.iloc[train_idx], y_train)

            probabilities = pipeline.predict_proba(X.iloc[test_idx])[:, 1]
            metrics = evaluate(y_test, probabilities, THRESHOLD)

            result = {
                "model": model_name,
                "experiment": experiment_name,
                "feature_count_before_encoding": int(
                    len(numeric_features) + len(cats)
                ),
                "numeric_features": numeric_features,
                "categorical_features": cats,
                "holdout_rows": int(len(y_test)),
                "holdout_churn_prevalence_pct": float(y_test.mean() * 100),
                **metrics,
            }
            all_results.append(result)

            prediction_frames.append(pd.DataFrame({
                "row_index": test_idx,
                "actual_is_churned": y_test.to_numpy(),
                "model": model_name,
                "experiment": experiment_name,
                "predicted_churn_probability": probabilities,
                "predicted_at_0_50": (probabilities >= THRESHOLD).astype(int),
            }))

            print(
                f"  PR-AUC: {metrics['pr_auc_average_precision']:.4f} | "
                f"ROC-AUC: {metrics['roc_auc']:.4f} | "
                f"Precision: {metrics['precision_at_threshold']:.4f} | "
                f"Recall: {metrics['recall_at_threshold']:.4f}"
            )

    # Build a concise comparison table and calculate the impact of removing
    # payment_status for each algorithm.
    comparison_rows = []
    for model_name in ("logistic_regression", "random_forest"):
        with_status = next(
            r for r in all_results
            if r["model"] == model_name
            and r["experiment"] == "with_payment_status"
        )
        without_status = next(
            r for r in all_results
            if r["model"] == model_name
            and r["experiment"] == "without_payment_status"
        )

        comparison_rows.append({
            "model": model_name,
            "pr_auc_with_payment_status": with_status["pr_auc_average_precision"],
            "pr_auc_without_payment_status": without_status["pr_auc_average_precision"],
            "pr_auc_change_after_removal": (
                without_status["pr_auc_average_precision"]
                - with_status["pr_auc_average_precision"]
            ),
            "roc_auc_with_payment_status": with_status["roc_auc"],
            "roc_auc_without_payment_status": without_status["roc_auc"],
            "precision_with_payment_status": with_status["precision_at_threshold"],
            "precision_without_payment_status": without_status["precision_at_threshold"],
            "recall_with_payment_status": with_status["recall_at_threshold"],
            "recall_without_payment_status": without_status["recall_at_threshold"],
            "f1_with_payment_status": with_status["f1_at_threshold"],
            "f1_without_payment_status": without_status["f1_at_threshold"],
        })

    comparison = pd.DataFrame(comparison_rows)
    comparison.to_csv(OUT / "payment_status_model_comparison.csv", index=False)

    predictions = pd.concat(prediction_frames, ignore_index=True)
    predictions.to_csv(OUT / "holdout_predictions.csv", index=False)

    # Examine observed churn by payment status on the full dataset.
    payment_summary = None
    if "payment_status" in df.columns:
        payment_summary = (
            df.groupby("payment_status", dropna=False)["is_churned"]
            .agg(
                customer_count="size",
                churned_customers="sum",
                observed_churn_rate="mean",
            )
            .reset_index()
        )
        payment_summary["observed_churn_rate_pct"] = (
            payment_summary["observed_churn_rate"] * 100
        )
        payment_summary.to_csv(
            OUT / "payment_status_observed_churn.csv",
            index=False,
        )

    report = {
        "project": "HORIZON",
        "purpose": (
            "Controlled holdout comparison of churn models with and "
            "without payment_status."
        ),
        "dataset_rows": int(len(df)),
        "churned_rows": int(y.sum()),
        "overall_churn_rate_pct": float(y.mean() * 100),
        "split": {
            "method": "80/20 stratified train_test_split",
            "random_state": RANDOM_STATE,
            "train_rows": int(len(train_idx)),
            "holdout_rows": int(len(test_idx)),
            "holdout_churned": int(y_test.sum()),
            "holdout_churn_rate_pct": float(y_test.mean() * 100),
        },
        "threshold": THRESHOLD,
        "features": {
            "numeric": numeric_features,
            "categorical_with_payment_status": categorical_features,
            "categorical_without_payment_status": [
                c for c in categorical_features if c != "payment_status"
            ],
            "excluded": [
                "customer_id",
                "company_name",
                "churn_risk_score",
                "signup_date",
                "last_active_date",
            ],
        },
        "model_configuration": {
            "logistic_regression": {
                "max_iter": 2000,
                "class_weight": "balanced",
                "random_state": RANDOM_STATE,
            },
            "random_forest": {
                "n_estimators": 400,
                "min_samples_leaf": 5,
                "class_weight": "balanced_subsample",
                "random_state": RANDOM_STATE,
                "n_jobs": -1,
            },
            "preprocessing": (
                "Median imputation and standard scaling for numeric features; "
                "most-frequent imputation and one-hot encoding for categorical features."
            ),
        },
        "results": all_results,
        "payment_status_observed_churn": (
            payment_summary.to_dict(orient="records")
            if payment_summary is not None else None
        ),
        "interpretation_caution": (
            "This comparison measures predictive dependence on payment_status; "
            "it does not prove temporal leakage. Confirm when payment_status was "
            "recorded relative to the prediction point. The models are evaluated "
            "on a synthetic dataset and are not production validated."
        ),
    }

    (OUT / "payment_status_reliability_report.json").write_text(
        json.dumps(report, indent=2, default=str),
        encoding="utf-8",
    )

    print("\n" + "=" * 64)
    print("COMPARISON")
    print("=" * 64)
    print(comparison.to_string(index=False))
    if payment_summary is not None:
        print("\nObserved churn by payment status:")
        print(payment_summary.to_string(index=False))

    print("\nCompleted. Reports saved to:")
    print(OUT)
    print("\nFiles created:")
    print("- payment_status_reliability_report.json")
    print("- payment_status_model_comparison.csv")
    print("- holdout_predictions.csv")
    if payment_summary is not None:
        print("- payment_status_observed_churn.csv")


if __name__ == "__main__":
    main()
