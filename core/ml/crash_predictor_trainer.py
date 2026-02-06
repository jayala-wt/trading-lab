"""
Crash Predictor ML Trainer - Train a loss-avoidance model.

This model predicts the probability of a 'bad' quality signal based on:
- Dimension states (momentum, trend, volatility, etc.)
- Raw indicator values (RSI, MACD, ATR, etc.)

Target: label_quality='bad' (outcome_60m < -0.5% OR max_drawdown < -2.0%)
Balanced dataset: ~25% bad, ~53% neutral, ~23% good

Crash signature from Feb 3-6 analysis:
  compressed + weak_trend + neutral_momentum = DANGER

Usage:
    python -m core.ml.crash_predictor_trainer --train
    python -m core.ml.crash_predictor_trainer --evaluate
"""
from __future__ import annotations

import argparse
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
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

import os
from core.common.env import load_dotenv
from core.common.paths import repo_root
from core.data.db import Database


# Crash definition thresholds
CRASH_THRESHOLD_5M = -3.0  # Loss >= 3% in 5min = crash
CRASH_THRESHOLD_DRAWDOWN = -5.0  # Max drawdown >= 5% = severe crash
CRASH_THRESHOLD_60M = -5.0  # Loss >= 5% in 60min = prolonged crash

# Feature columns
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

# Categorical metadata features
CATEGORICAL_FEATURES = [
    "symbol",  # Each symbol has unique volatility characteristics
]


def load_crash_training_data(
    db: Database,
    start_date: str = "2026-02-03",
    end_date: str = "2026-02-14",
) -> pd.DataFrame:
    """Load ML training samples from crash period and recent data."""
    
    rows = db.query(
        """
        SELECT 
            -- Dimension features
            dim_momentum,
            dim_trend,
            dim_volatility,
            dim_participation,
            dim_location,
            dim_structure,
            
            -- Raw indicator features
            raw_rsi,
            raw_stoch_k,
            raw_macd_histogram,
            raw_ema_9,
            raw_ema_21,
            raw_ema_50,
            raw_slope_20,
            raw_atr_pct,
            raw_bb_bandwidth,
            raw_bb_pct,
            raw_volume_ratio,
            raw_vwap_distance_pct,
            
            -- Outcomes (labels)
            outcome_5m,
            outcome_15m,
            outcome_60m,
            max_drawdown,
            max_favorable,
            label_quality,
            
            -- Metadata
            symbol,
            pattern_id,
            direction,
            confidence,
            created_at
            
        FROM ml_training_samples
        WHERE 
            outcome_5m IS NOT NULL
            AND DATE(created_at) BETWEEN ? AND ?
        ORDER BY created_at ASC
        """,
        (start_date, end_date),
    )
    
    df = pd.DataFrame([dict(row) for row in rows])
    
    print(f"Loaded {len(df)} training samples from {start_date} to {end_date}")
    
    # Print quality distribution
    if len(df) > 0 and "label_quality" in df.columns:
        quality_dist = df["label_quality"].value_counts()
        print(f"Quality distribution:")
        for quality, count in quality_dist.items():
            pct = (count / len(df)) * 100
            print(f"  {quality}: {count} ({pct:.1f}%)")
        
        # Print crash signature stats (Feb 3 pattern)
        crash_signature = df[
            (df["dim_volatility"] == "compressed")
            & (df["dim_trend"].isin(["up_weak", "down_weak"]))
            & (df["dim_momentum"] == "neutral")
        ]
        if len(crash_signature) > 0:
            bad_in_signature = (crash_signature["label_quality"] == "bad").sum()
            print(f"Crash signature samples: {len(crash_signature)} ({bad_in_signature} bad, {bad_in_signature/len(crash_signature)*100:.1f}%)")
    
    return df


def engineer_crash_label(df: pd.DataFrame) -> pd.Series:
    """Create binary label for 'bad' quality signals (loss avoidance).
    
    Uses label_quality='bad' which captures:
    - outcome_60m < -0.5% OR max_drawdown < -2.0%
    
    This is more balanced (25% of data) than extreme crashes (1.1%),
    giving the model enough examples to learn patterns.
    """
    
    # Target: Predict 'bad' quality signals (avoid losses)
    crash = (df["label_quality"] == "bad").astype(int)
    
    return crash


def prepare_features(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, LabelEncoder]]:
    """Prepare features for ML model, encode categorical dimensions."""
    
    X = df[DIMENSION_FEATURES + RAW_FEATURES + CATEGORICAL_FEATURES].copy()
    
    # Encode categorical dimension features
    encoders = {}
    for col in DIMENSION_FEATURES:
        if col in X.columns:
            le = LabelEncoder()
            # Handle NaN values
            X[col] = X[col].fillna("unknown")
            X[col] = le.fit_transform(X[col])
            encoders[col] = le
    
    # Encode categorical metadata features (symbol, direction, etc.)
    for col in CATEGORICAL_FEATURES:
        if col in X.columns:
            le = LabelEncoder()
            X[col] = X[col].fillna("unknown")
            X[col] = le.fit_transform(X[col])
            encoders[col] = le
    
    # Fill NaN in raw features with median
    for col in RAW_FEATURES:
        if col in X.columns:
            X[col] = X[col].fillna(X[col].median())
    
    return X, encoders


def train_crash_predictor(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    model_type: str = "random_forest",
) -> Any:
    """Train crash prediction model."""
    
    if model_type == "random_forest":
        model = RandomForestClassifier(
            n_estimators=200,
            max_depth=10,
            min_samples_split=20,
            min_samples_leaf=10,
            class_weight="balanced",  # Handle imbalanced data
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
) -> Dict[str, Any]:
    """Evaluate crash predictor and return metrics."""
    
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]  # Probability of crash
    
    # Classification metrics
    print("\n" + "="*60)
    print("CRASH PREDICTOR EVALUATION")
    print("="*60)
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, target_names=["Safe", "Crash"]))
    
    print("\nConfusion Matrix:")
    cm = confusion_matrix(y_test, y_pred)
    print(f"TN: {cm[0,0]}, FP: {cm[0,1]}")
    print(f"FN: {cm[1,0]}, TP: {cm[1,1]}")
    
    # ROC AUC
    roc_auc = roc_auc_score(y_test, y_proba)
    print(f"\nROC AUC Score: {roc_auc:.3f}")
    
    # Find optimal threshold for high precision (avoid false alarms)
    precision, recall, thresholds = precision_recall_curve(y_test, y_proba)
    
    # Find threshold with precision >= 0.8
    # Note: precision_recall_curve returns n+1 precision/recall but n thresholds
    # So we need to clamp index to len(thresholds)-1
    high_precision_idx = np.where(precision[:-1] >= 0.80)[0]  # Exclude last element
    if len(high_precision_idx) > 0:
        optimal_idx = min(high_precision_idx[-1], len(thresholds) - 1)  # Clamp to valid range
        optimal_threshold = thresholds[optimal_idx]
        optimal_precision = precision[optimal_idx]
        optimal_recall = recall[optimal_idx]
        
        print(f"\nOptimal Threshold (>80% precision): {optimal_threshold:.3f}")
        print(f"  Precision: {optimal_precision:.3f}")
        print(f"  Recall: {optimal_recall:.3f}")
    else:
        optimal_threshold = 0.7
        # Use default threshold metrics
        y_pred_default = (y_proba >= optimal_threshold).astype(int)
        optimal_precision = precision_score(y_test, y_pred_default, zero_division=0)
        optimal_recall = recall_score(y_test, y_pred_default, zero_division=0)
        print(f"\nUsing default threshold: {optimal_threshold}")
        print(f"  Precision: {optimal_precision:.3f}")
        print(f"  Recall: {optimal_recall:.3f}")
    
    # Feature importance
    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
        indices = np.argsort(importances)[::-1]
        
        print("\nTop 10 Most Important Features:")
        for i in range(min(10, len(feature_names))):
            idx = indices[i]
            print(f"  {i+1}. {feature_names[idx]}: {importances[idx]:.4f}")
    
    metrics = {
        "roc_auc": roc_auc,
        "optimal_threshold": optimal_threshold,
        "confusion_matrix": cm.tolist(),
        "precision": optimal_precision,
        "recall": optimal_recall,
    }
    
    return metrics


def save_model(
    model: Any,
    encoders: Dict[str, LabelEncoder],
    metrics: Dict[str, Any],
    model_dir: Path,
) -> None:
    """Save trained model, encoders, and metadata."""
    
    model_dir.mkdir(parents=True, exist_ok=True)
    
    # Save model
    model_path = model_dir / "crash_predictor.joblib"
    joblib.dump(model, model_path)
    print(f"\nModel saved to: {model_path}")
    
    # Save encoders
    encoders_path = model_dir / "encoders.joblib"
    joblib.dump(encoders, encoders_path)
    print(f"Encoders saved to: {encoders_path}")
    
    # Save metadata
    metadata = {
        "trained_at": datetime.now().isoformat(),
        "metrics": metrics,
        "feature_names": DIMENSION_FEATURES + RAW_FEATURES,
        "crash_thresholds": {
            "outcome_5m": CRASH_THRESHOLD_5M,
            "max_drawdown": CRASH_THRESHOLD_DRAWDOWN,
            "outcome_60m": CRASH_THRESHOLD_60M,
        },
    }
    
    metadata_path = model_dir / "metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"Metadata saved to: {metadata_path}")


def main():
    parser = argparse.ArgumentParser(description="Train crash predictor ML model")
    parser.add_argument(
        "--train",
        action="store_true",
        help="Train new model on crash data",
    )
    parser.add_argument(
        "--evaluate",
        action="store_true",
        help="Evaluate existing model",
    )
    parser.add_argument(
        "--start-date",
        default="2026-02-03",
        help="Start date for training data (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        default="2026-02-14",
        help="End date for training data (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--model-type",
        choices=["random_forest", "gradient_boosting"],
        default="random_forest",
        help="Type of model to train",
    )
    
    args = parser.parse_args()
    
    load_dotenv(repo_root() / ".env")
    db_path = Path(os.getenv("TRADING_LAB_DB_PATH", str(repo_root() / "data" / "market.db")))
    db = Database(db_path)
    model_dir = repo_root() / "trading-lab" / "models" / "crash_predictor"
    
    if args.train:
        print("Loading crash training data...")
        df = load_crash_training_data(db, args.start_date, args.end_date)
        
        if len(df) == 0:
            print("No training data found!")
            return
        
        # Engineer crash label (predicts label_quality='bad')
        y = engineer_crash_label(df)
        print(f"\nBad quality samples (target=1): {y.sum()} ({y.mean()*100:.1f}%)")
        print(f"Good/Neutral samples (target=0): {(~y.astype(bool)).sum()} ({(1-y.mean())*100:.1f}%)")
        
        # Prepare features
        X, encoders = prepare_features(df)
        
        # Time-based split (NO RANDOM SHUFFLE - prevents look-ahead bias)
        # Train: oldest 70%, Val: next 15%, Test: newest 15%
        n = len(X)
        train_end = int(n * 0.70)
        val_end = int(n * 0.85)
        
        X_train = X.iloc[:train_end]
        y_train = y.iloc[:train_end]
        
        X_val = X.iloc[train_end:val_end]
        y_val = y.iloc[train_end:val_end]
        
        X_test = X.iloc[val_end:]
        y_test = y.iloc[val_end:]
        
        print(f"\n📊 TIME-BASED SPLITS (no look-ahead bias):")
        print(f"  Training set:   {len(X_train)} samples ({y_train.mean()*100:.1f}% bad)")
        print(f"  Validation set: {len(X_val)} samples ({y_val.mean()*100:.1f}% bad)")
        print(f"  Test set:       {len(X_test)} samples ({y_test.mean()*100:.1f}% bad)")
        print(f"  Date ranges:")
        print(f"    Train: {df.iloc[:train_end]['created_at'].min()} to {df.iloc[:train_end]['created_at'].max()}")
        print(f"    Val:   {df.iloc[train_end:val_end]['created_at'].min()} to {df.iloc[train_end:val_end]['created_at'].max()}")
        print(f"    Test:  {df.iloc[val_end:]['created_at'].min()} to {df.iloc[val_end:]['created_at'].max()}")
        
        # Train model
        print(f"\nTraining {args.model_type} model...")
        model = train_crash_predictor(X_train, y_train, args.model_type)
        
        # Evaluate on validation set first
        print("\n" + "="*60)
        print("VALIDATION SET EVALUATION")
        print("="*60)
        val_metrics = evaluate_model(model, X_val, y_val, X.columns.tolist())
        
        # Evaluate on test set
        print("\n" + "="*60)
        print("TEST SET EVALUATION (FINAL)")
        print("="*60)
        metrics = evaluate_model(model, X_test, y_test, X.columns.tolist())
        
        # Store both validation and test metrics
        metrics['val_metrics'] = val_metrics
        
        # Save
        save_model(model, encoders, metrics, model_dir)
        
        print("\n✅ Training complete!")
        
    elif args.evaluate:
        print("Loading model...")
        model_path = model_dir / "crash_predictor.joblib"
        
        if not model_path.exists():
            print(f"Model not found at {model_path}")
            print("Run with --train first")
            return
        
        model = joblib.load(model_path)
        encoders = joblib.load(model_dir / "encoders.joblib")
        
        # Load test data
        df = load_crash_training_data(db, args.start_date, args.end_date)
        y = engineer_crash_label(df)
        X, _ = prepare_features(df)
        
        # Evaluate
        evaluate_model(model, X, y, X.columns.tolist())
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
