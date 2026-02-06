"""
Buy Entry Classifier - Train an entry quality filter for buy signals.

Predicts whether a buy signal is a 'good' entry (strong reversal about to happen)
vs 'bad' entry (buying too early, price continues falling).

Key insight from data analysis (2026-02-25):
  Good buy entries: avg RSI 32.7, Stoch K 23.9, BB% 0.206, Volume ratio 1.106
  Bad buy entries:  avg RSI 36.5, Stoch K 28.9, BB% 0.303, Volume ratio 1.017

Target: label_quality='good' (1) vs label_quality='bad' (0)
Neutral samples are excluded — we only learn from clear good/bad outcomes.

Usage:
    python scripts/train_buy_entry_classifier.py
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.preprocessing import LabelEncoder

from core.common.paths import repo_root
from core.data.db import Database


# Feature columns — same as crash predictor for consistency
DIMENSION_FEATURES = [
    "dim_momentum",
    "dim_trend",
    "dim_volatility",
    "dim_participation",
    "dim_location",
    "dim_structure",
]

RAW_FEATURES = [
    "raw_rsi",
    "raw_stoch_k",
    "raw_macd_histogram",
    "raw_ema_9",
    "raw_ema_21",
    "raw_ema_50",
    "raw_slope_20",
    "raw_atr_pct",
    "raw_bb_bandwidth",
    "raw_bb_pct",
    "raw_volume_ratio",
    "raw_vwap_distance_pct",
]

CATEGORICAL_FEATURES = ["symbol"]


def load_buy_training_data(
    db: Database,
    start_date: str = "2026-02-03",
    end_date: str = "2026-02-22",
) -> pd.DataFrame:
    """Load buy-only samples from ml_training_samples, excluding neutral."""

    rows = db.query(
        """
        SELECT
            dim_momentum, dim_trend, dim_volatility,
            dim_participation, dim_location, dim_structure,
            raw_rsi, raw_stoch_k, raw_macd_histogram,
            raw_ema_9, raw_ema_21, raw_ema_50, raw_slope_20,
            raw_atr_pct, raw_bb_bandwidth, raw_bb_pct,
            raw_volume_ratio, raw_vwap_distance_pct,
            outcome_5m, outcome_15m, outcome_60m,
            max_drawdown, max_favorable, label_quality,
            symbol, pattern_id, confidence, created_at
        FROM ml_training_samples
        WHERE
            direction = 'buy'
            AND label_quality IN ('good', 'bad')
            AND outcome_5m IS NOT NULL
            AND DATE(created_at) BETWEEN ? AND ?
        ORDER BY created_at ASC
        """,
        (start_date, end_date),
    )

    df = pd.DataFrame([dict(row) for row in rows])
    print(f"Loaded {len(df)} buy samples (good+bad only) from {start_date} to {end_date}")

    if len(df) > 0 and "label_quality" in df.columns:
        dist = df["label_quality"].value_counts()
        for quality, count in dist.items():
            print(f"  {quality}: {count} ({count/len(df)*100:.1f}%)")

        print(f"\nKey feature averages:")
        for q in ["good", "bad"]:
            sub = df[df["label_quality"] == q]
            print(
                f"  {q}: RSI={sub['raw_rsi'].mean():.1f}  "
                f"Stoch={sub['raw_stoch_k'].mean():.1f}  "
                f"BB%={sub['raw_bb_pct'].mean():.3f}  "
                f"VolRatio={sub['raw_volume_ratio'].mean():.3f}  "
                f"60m_outcome={sub['outcome_60m'].mean():.4f}"
            )

    return df


def engineer_entry_label(df: pd.DataFrame) -> pd.Series:
    """Binary label: 1 = good entry, 0 = bad entry."""
    return (df["label_quality"] == "good").astype(int)


def prepare_features(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, LabelEncoder]]:
    """Encode categorical features and fill NaNs."""
    X = df[DIMENSION_FEATURES + RAW_FEATURES + CATEGORICAL_FEATURES].copy()

    encoders = {}
    for col in DIMENSION_FEATURES + CATEGORICAL_FEATURES:
        if col in X.columns:
            le = LabelEncoder()
            X[col] = X[col].fillna("unknown")
            X[col] = le.fit_transform(X[col])
            encoders[col] = le

    for col in RAW_FEATURES:
        if col in X.columns:
            X[col] = X[col].fillna(X[col].median())

    return X, encoders


def train_classifier(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    model_type: str = "random_forest",
) -> Any:
    if model_type == "random_forest":
        model = RandomForestClassifier(
            n_estimators=200,
            max_depth=10,
            min_samples_split=20,
            min_samples_leaf=10,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )
    elif model_type == "gradient_boosting":
        model = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            min_samples_split=20,
            min_samples_leaf=10,
            random_state=42,
        )
    else:
        raise ValueError(f"Unknown model_type: {model_type}")

    model.fit(X_train, y_train)
    return model


def evaluate_model(
    model: Any,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    feature_names: List[str],
    label: str = "Test",
) -> Dict[str, Any]:
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]

    print(f"\n{'='*60}")
    print(f"BUY ENTRY CLASSIFIER — {label.upper()}")
    print(f"{'='*60}")
    print(classification_report(y_test, y_pred, target_names=["Bad Entry", "Good Entry"]))

    cm = confusion_matrix(y_test, y_pred)
    print(f"Confusion Matrix:")
    print(f"  TN (bad→bad): {cm[0,0]}  FP (bad→good): {cm[0,1]}")
    print(f"  FN (good→bad): {cm[1,0]}  TP (good→good): {cm[1,1]}")

    roc_auc = roc_auc_score(y_test, y_proba)
    print(f"\nROC AUC: {roc_auc:.3f}")

    # Find threshold for ~70% precision on "good" class
    precision, recall, thresholds = precision_recall_curve(y_test, y_proba)
    high_prec_idx = np.where(precision[:-1] >= 0.70)[0]
    if len(high_prec_idx) > 0:
        optimal_idx = min(high_prec_idx[-1], len(thresholds) - 1)
        optimal_threshold = float(thresholds[optimal_idx])
        optimal_precision = float(precision[optimal_idx])
        optimal_recall = float(recall[optimal_idx])
    else:
        optimal_threshold = 0.60
        y_pred_t = (y_proba >= optimal_threshold).astype(int)
        optimal_precision = float(precision_score(y_test, y_pred_t, zero_division=0))
        optimal_recall = float(recall_score(y_test, y_pred_t, zero_division=0))

    print(f"\nOptimal threshold (≥70% precision): {optimal_threshold:.3f}")
    print(f"  Precision: {optimal_precision:.3f}  Recall: {optimal_recall:.3f}")

    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
        indices = np.argsort(importances)[::-1]
        print("\nTop 10 Feature Importances:")
        for i in range(min(10, len(feature_names))):
            idx = indices[i]
            print(f"  {i+1}. {feature_names[idx]}: {importances[idx]:.4f}")

    return {
        "roc_auc": float(roc_auc),
        "optimal_threshold": optimal_threshold,
        "precision": optimal_precision,
        "recall": optimal_recall,
        "confusion_matrix": cm.tolist(),
    }


def save_model(
    model: Any,
    encoders: Dict[str, LabelEncoder],
    metrics: Dict[str, Any],
    model_dir: Path,
) -> None:
    model_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(model, model_dir / "buy_entry_classifier.joblib")
    joblib.dump(encoders, model_dir / "encoders.joblib")

    metadata = {
        "trained_at": datetime.now().isoformat(),
        "model_type": "buy_entry_classifier",
        "description": "Predicts whether a buy signal will be a good entry (1) or bad entry (0)",
        "training_filter": "direction='buy', label_quality IN ('good','bad')",
        "metrics": metrics,
        "feature_names": DIMENSION_FEATURES + RAW_FEATURES + CATEGORICAL_FEATURES,
        "key_insight": {
            "good_entry": {"avg_rsi": 32.7, "avg_stoch_k": 23.9, "avg_bb_pct": 0.206, "avg_volume_ratio": 1.106},
            "bad_entry": {"avg_rsi": 36.5, "avg_stoch_k": 28.9, "avg_bb_pct": 0.303, "avg_volume_ratio": 1.017},
        },
    }

    with open(model_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\nModel saved to: {model_dir}")
    print(f"  buy_entry_classifier.joblib")
    print(f"  encoders.joblib")
    print(f"  metadata.json")
