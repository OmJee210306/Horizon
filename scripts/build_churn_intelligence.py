"""
HORIZON - Churn Intelligence and Explainability
Run from project root:
    python scripts/build_churn_intelligence.py

Uses the previously trained Logistic Regression pipeline and the independent
synthetic churn dataset. Does not join to primary SaaS billing records.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance
from sklearn.metrics import average_precision_score
from sklearn.model_selection import train_test_split


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "raw" / "churn" / "MP_Synthetics_50000_Rows.csv"
MODEL_PATH = ROOT / "models" / "churn_model.joblib"
OUT_DIR = ROOT / "data" / "processed" / "churn_intelligence"

TARGET = "is_churned"
NUMERIC_FEATURES = [
    "monthly_recurring_revenue",
    "active_seats_used",
    "total_seats_allowed",
    "support_tickets_30d",
    "feature_adoption_rate",
]
CATEGORICAL_FEATURES = [
    "industry",
    "country",
    "company_size",
    "account_manager",
    "plan_tier",
    "billing_cycle",
    "payment_status",
]
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


def normalize_column_name(name: str) -> str:
    name = str(name).strip()
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    name = re.sub(r"[^A-Za-z0-9]+", "_", name)
    return name.strip("_").lower()


def load_and_prepare() -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {DATA_PATH}")
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Model not found: {MODEL_PATH}. Run scripts/train_churn_model.py first."
        )

    raw = pd.read_csv(DATA_PATH)
    raw.columns = [normalize_column_name(c) for c in raw.columns]
    required = set(FEATURES + [TARGET])
    missing = sorted(required - set(raw.columns))
    if missing:
        raise ValueError(f"Missing expected columns: {missing}")

    raw[TARGET] = pd.to_numeric(raw[TARGET], errors="coerce")
    valid = raw[TARGET].isin([0, 1])
    raw = raw.loc[valid].copy()
    raw[TARGET] = raw[TARGET].astype(int)

    adoption = (
        raw["feature_adoption_rate"]
        .astype(str)
        .str.strip()
        .str.replace("%", "", regex=False)
    )
    raw["feature_adoption_rate"] = pd.to_numeric(adoption, errors="coerce")
    if raw["feature_adoption_rate"].dropna().gt(1).any():
        raw["feature_adoption_rate"] /= 100.0

    for col in NUMERIC_FEATURES:
        raw[col] = pd.to_numeric(raw[col], errors="coerce")
    for col in CATEGORICAL_FEATURES:
        raw[col] = raw[col].astype("string").fillna("Unknown").astype(str)

    X = raw[FEATURES].copy()
    y = raw[TARGET].copy()
    return raw, X, y


def get_risk_tier(percentile_rank: float) -> str:
    # Priority bands by rank, not absolute calibrated churn probability.
    if percentile_rank >= 0.99:
        return "Critical"
    if percentile_rank >= 0.95:
        return "High"
    if percentile_rank >= 0.80:
        return "Medium"
    return "Monitor"


def recommendation(tier: str) -> str:
    actions = {
        "Critical": "Immediate human review; contact customer to understand risk and agree a retention plan.",
        "High": "Proactive account-manager outreach; review adoption, support issues and plan fit.",
        "Medium": "Targeted engagement; offer onboarding, feature education or a usage check-in.",
        "Monitor": "Continue routine monitoring; use standard product education and support channels.",
    }
    return actions[tier]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw, X, y = load_and_prepare()
    model = joblib.load(MODEL_PATH)

    # Recreate the original holdout split to make permutation results comparable
    # with the model evaluation already reported.
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )

    print("Calculating holdout permutation importance (PR-AUC)...")
    perm = permutation_importance(
        model,
        X_test,
        y_test,
        scoring="average_precision",
        n_repeats=5,
        random_state=42,
        n_jobs=-1,
    )
    importance = pd.DataFrame({
        "feature": FEATURES,
        "mean_pr_auc_decrease": perm.importances_mean,
        "std_pr_auc_decrease": perm.importances_std,
    }).sort_values("mean_pr_auc_decrease", ascending=False)
    importance.to_csv(OUT_DIR / "model_feature_importance.csv", index=False)

    # Actual observed churn rates by categorical segment.
    categorical_rows = []
    for col in CATEGORICAL_FEATURES:
        grouped = raw.groupby(col, dropna=False)[TARGET].agg(
            customer_count="size",
            churned_customers="sum",
            churn_rate="mean",
        ).reset_index()
        grouped = grouped.rename(columns={col: "segment"})
        grouped.insert(0, "dimension", col)
        grouped["churn_rate_pct"] = grouped["churn_rate"] * 100
        categorical_rows.append(grouped)
    categorical_summary = pd.concat(categorical_rows, ignore_index=True)
    categorical_summary.to_csv(
        OUT_DIR / "observed_churn_by_segment.csv", index=False
    )

    # Numeric decile analysis. qcut duplicates are handled for low-cardinality data.
    numeric_rows = []
    for col in NUMERIC_FEATURES:
        values = raw[col]
        try:
            bins = pd.qcut(values, q=10, duplicates="drop")
            temp = pd.DataFrame({"band": bins, TARGET: raw[TARGET]})
            grouped = temp.groupby("band", observed=True)[TARGET].agg(
                customer_count="size",
                churned_customers="sum",
                churn_rate="mean",
            ).reset_index()
            grouped["dimension"] = col
            grouped["band"] = grouped["band"].astype(str)
            grouped["churn_rate_pct"] = grouped["churn_rate"] * 100
            numeric_rows.append(grouped)
        except (ValueError, TypeError):
            continue
    if numeric_rows:
        numeric_summary = pd.concat(numeric_rows, ignore_index=True)
        numeric_summary.to_csv(
            OUT_DIR / "observed_churn_numeric_bands.csv", index=False
        )

    # Score every row in this synthetic dataset.
    print("Scoring all valid customer rows and calculating model contributions...")
    probabilities = model.predict_proba(X)[:, 1]
    percentile_ranks = pd.Series(probabilities).rank(pct=True, method="average").to_numpy()
    tiers = [get_risk_tier(float(p)) for p in percentile_ranks]

    # Explain Logistic Regression scores using signed contributions:
    # transformed feature value multiplied by its fitted coefficient.
    # This is a model-level explanation, not causal attribution.
    estimator = model.named_steps.get("model")
    preprocessor = model.named_steps.get("preprocessor")
    if estimator is None or preprocessor is None or not hasattr(estimator, "coef_"):
        raise TypeError(
            "The saved model is not the expected Logistic Regression pipeline. "
            "Retrain with scripts/train_churn_model.py."
        )

    transformed = preprocessor.transform(X)
    coefficients = estimator.coef_[0]
    feature_names = preprocessor.get_feature_names_out()

    contributions = transformed.multiply(coefficients) if hasattr(transformed, "multiply") else transformed * coefficients
    contribution_frame = pd.DataFrame.sparse.from_spmatrix(
        contributions.tocsr() if hasattr(contributions, "tocsr") else contributions,
        columns=feature_names,
        index=raw.index,
    ) if hasattr(contributions, "tocsr") else pd.DataFrame(
        contributions, columns=feature_names, index=raw.index
    )

    # Include source identifiers only as display/reference fields, never predictors.
    scored = pd.DataFrame(index=raw.index)
    if "customer_id" in raw.columns:
        scored["customer_id"] = raw["customer_id"].astype(str)
    if "company_name" in raw.columns:
        scored["company_name"] = raw["company_name"].astype(str)

    scored["predicted_churn_probability"] = probabilities
    scored["risk_percentile"] = percentile_ranks * 100
    scored["priority_tier"] = tiers
    scored["recommended_action"] = [recommendation(t) for t in tiers]
    scored["actual_is_churned"] = y

    # Top three positive model contributions per customer.
    top_reasons = []
    for row_idx in range(len(contribution_frame)):
        row = contribution_frame.iloc[row_idx]
        positive = row[row > 0].sort_values(ascending=False).head(3)
        reasons = [
            f"{str(name).replace('numeric__', '').replace('categorical__', '')} "
            f"(+{float(value):.3f})"
            for name, value in positive.items()
        ]
        top_reasons.append("; ".join(reasons) if reasons else "No positive feature contribution")
    scored["top_model_contributors"] = top_reasons

    scored = scored.sort_values(
        ["risk_percentile", "predicted_churn_probability"], ascending=False
    )
    scored.to_csv(OUT_DIR / "customer_churn_intelligence.csv", index=False)

    # Tier summary includes actual outcome rate for retrospective analysis.
    tier_summary = scored.groupby("priority_tier", sort=False).agg(
        customer_count=("priority_tier", "size"),
        average_model_score=("predicted_churn_probability", "mean"),
        actual_churned_customers=("actual_is_churned", "sum"),
        observed_churn_rate=("actual_is_churned", "mean"),
    ).reset_index()
    tier_summary["observed_churn_rate_pct"] = tier_summary["observed_churn_rate"] * 100
    tier_summary.to_csv(OUT_DIR / "priority_tier_summary.csv", index=False)

    report = {
        "project": "HORIZON",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": str(DATA_PATH.relative_to(ROOT)),
        "model": str(MODEL_PATH.relative_to(ROOT)),
        "rows_scored": int(len(scored)),
        "model_type": type(estimator).__name__,
        "model_pr_auc_on_recreated_holdout": float(
            average_precision_score(
                y_test, model.predict_proba(X_test)[:, 1]
            )
        ),
        "tier_definitions": {
            "Critical": "Top 1% by model score percentile",
            "High": "Next 4% (95th to below 99th percentile)",
            "Medium": "Next 15% (80th to below 95th percentile)",
            "Monitor": "Remaining 80%",
        },
        "explainability_method": (
            "Signed Logistic Regression coefficient contributions on the transformed "
            "feature space. Positive contributions push the model score upward; "
            "they are not causal explanations."
        ),
        "permutation_importance_method": (
            "Holdout permutation importance using average precision (PR-AUC), "
            "5 repeats, random_state=42."
        ),
        "limitations": [
            "Dataset is synthetic and independent of primary SaaS billing data.",
            "Priority tiers are relative ranking bands, not calibrated risk categories.",
            "Model scores are not calibrated probabilities of future churn.",
            "Feature contributions describe model behaviour, not causation.",
            "Observed segment churn rates are retrospective associations, not causal effects.",
            "Recommended actions are illustrative playbook suggestions, not validated interventions.",
            "The dataset has no defined prediction timestamp; this limits real-world deployment claims.",
        ],
    }
    (OUT_DIR / "intelligence_summary.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    print("\nPRIORITY TIER SUMMARY")
    print(tier_summary.to_string(index=False))
    print("\nTOP MODEL FEATURES (PERMUTATION IMPORTANCE)")
    print(importance.head(12).to_string(index=False))
    print("\nCreated outputs in:")
    print(OUT_DIR)
    print("- model_feature_importance.csv")
    print("- observed_churn_by_segment.csv")
    print("- observed_churn_numeric_bands.csv")
    print("- customer_churn_intelligence.csv")
    print("- priority_tier_summary.csv")
    print("- intelligence_summary.json")


if __name__ == "__main__":
    main()
