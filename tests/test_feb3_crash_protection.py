#!/usr/bin/env python3
"""
Test Model A against Feb 3-6 crash period.

Validates if the model would have prevented the catastrophic Feb 3 losses.

Expected baseline (no model):
- Total loss: -$155 (Feb 3 alone)
- Avg hold time: >10 hours
- Win rate: 8.75%

Goal: Block ≥50% of losing trades while maintaining acceptable false positive rate.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import joblib
import pandas as pd
import numpy as np
from datetime import datetime

from core.common.env import load_dotenv
from core.common.paths import repo_root
from core.data.db import Database

# Same features as trainer
DIMENSION_FEATURES = [
    "dim_momentum", "dim_trend", "dim_volatility",
    "dim_participation", "dim_location", "dim_structure",
]

RAW_FEATURES = [
    "raw_rsi", "raw_stoch_k", "raw_macd_histogram",
    "raw_ema_9", "raw_ema_21", "raw_ema_50",
    "raw_slope_20", "raw_atr_pct", "raw_bb_bandwidth",
    "raw_bb_pct", "raw_volume_ratio", "raw_vwap_distance_pct",
]

CATEGORICAL_FEATURES = [
    "symbol",  # Each symbol has unique volatility characteristics
]

def load_model():
    """Load trained model and encoders."""
    model_dir = repo_root() / "trading-lab" / "models" / "crash_predictor"
    
    print("Loading trained model...")
    model = joblib.load(model_dir / "crash_predictor.joblib")
    encoders = joblib.load(model_dir / "encoders.joblib")
    
    # Load metadata
    import json
    with open(model_dir / "metadata.json") as f:
        metadata = json.load(f)
    
    print(f"  Model type: {metadata.get('model_type', 'random_forest')}")
    print(f"  Trained: {metadata.get('trained_at', 'unknown')}")
    print(f"  Training samples: {metadata.get('training_samples', 'unknown')}")
    
    return model, encoders, metadata


def load_feb3_samples(db: Database):
    """Load samples from Feb 3-6 crash period."""
    print("\nLoading Feb 3-6 crash period samples...")
    
    rows = db.query("""
        SELECT 
            -- Dimension states (categorical)
            dim_momentum, dim_trend, dim_volatility,
            dim_participation, dim_location, dim_structure,
            
            -- Raw indicators (numerical)
            raw_rsi, raw_stoch_k, raw_macd_histogram,
            raw_ema_9, raw_ema_21, raw_ema_50,
            raw_slope_20, raw_atr_pct, raw_bb_bandwidth,
            raw_bb_pct, raw_volume_ratio, raw_vwap_distance_pct,
            
            -- Outcomes (for evaluation)
            outcome_5m, outcome_15m, outcome_60m,
            max_drawdown, max_favorable, label_quality,
            
            -- Metadata
            symbol, pattern_id, direction, confidence, created_at
            
        FROM ml_training_samples
        WHERE DATE(created_at) BETWEEN '2026-02-03' AND '2026-02-06'
        ORDER BY created_at ASC
    """)
    
    df = pd.DataFrame([dict(row) for row in rows])
    print(f"  Loaded {len(df)} samples")
    
    if len(df) > 0:
        quality_dist = df["label_quality"].value_counts()
        print(f"  Quality distribution:")
        for quality, count in quality_dist.items():
            pct = (count / len(df)) * 100
            print(f"    {quality}: {count} ({pct:.1f}%)")
    
    return df


def prepare_features(df: pd.DataFrame, encoders: dict):
    """Prepare features using same encoding as training."""
    X = df[DIMENSION_FEATURES + RAW_FEATURES + CATEGORICAL_FEATURES].copy()
    
    # Encode categorical dimension features
    for col in DIMENSION_FEATURES:
        if col in X.columns and col in encoders:
            le = encoders[col]
            # Handle unknown categories
            X[col] = X[col].fillna("unknown")
            
            # Map unknown categories to first class
            known_classes = set(le.classes_)
            X[col] = X[col].apply(lambda x: x if x in known_classes else le.classes_[0])
            X[col] = le.transform(X[col])
    
    # Encode categorical metadata features (symbol, etc.)
    for col in CATEGORICAL_FEATURES:
        if col in X.columns and col in encoders:
            le = encoders[col]
            # Handle unknown categories
            X[col] = X[col].fillna("unknown")
            
            # Map unknown categories to first class
            known_classes = set(le.classes_)
            X[col] = X[col].apply(lambda x: x if x in known_classes else le.classes_[0])
            X[col] = le.transform(X[col])
    
    # Fill NaN in numerical features
    for col in RAW_FEATURES:
        if col in X.columns:
            X[col] = X[col].fillna(X[col].median())
    
    return X


def evaluate_crash_protection(df: pd.DataFrame, y_pred_proba: np.ndarray, threshold: float = 0.5):
    """Evaluate if model would have prevented Feb 3 losses."""
    
    print(f"\n{'='*70}")
    print(f"CRASH PROTECTION EVALUATION (threshold={threshold:.2f})")
    print(f"{'='*70}")
    
    # Predicted bad signals
    would_block = y_pred_proba >= threshold
    
    # Actual bad signals
    actual_bad = df["label_quality"] == "bad"
    
    # True positives: correctly blocked bad signals
    tp = (would_block & actual_bad).sum()
    
    # False positives: blocked good/neutral signals
    fp = (would_block & ~actual_bad).sum()
    
    # False negatives: missed bad signals
    fn = (~would_block & actual_bad).sum()
    
    # True negatives: correctly allowed good/neutral
    tn = (~would_block & ~actual_bad).sum()
    
    print(f"\nConfusion Matrix:")
    print(f"  True Positives (blocked bad):     {tp:4d}")
    print(f"  False Positives (blocked good):   {fp:4d}")
    print(f"  False Negatives (missed bad):     {fn:4d}")
    print(f"  True Negatives (allowed good):    {tn:4d}")
    
    # Metrics
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    print(f"\nMetrics:")
    print(f"  Precision: {precision:.1%} (when model says bad, it's right {precision:.1%} of time)")
    print(f"  Recall:    {recall:.1%} (catches {recall:.1%} of actual bad signals)")
    print(f"  F1 Score:  {f1:.3f}")
    
    # Financial impact
    print(f"\n{'='*70}")
    print(f"FINANCIAL IMPACT ANALYSIS")
    print(f"{'='*70}")
    
    # Baseline (no model)
    baseline_bad = actual_bad.sum()
    baseline_good = (~actual_bad).sum()
    baseline_bad_outcome = df[actual_bad]["outcome_60m"].sum() if baseline_bad > 0 else 0
    baseline_good_outcome = df[~actual_bad]["outcome_60m"].sum() if baseline_good > 0 else 0
    baseline_total = baseline_bad_outcome + baseline_good_outcome
    
    print(f"\nBaseline (NO MODEL):")
    print(f"  Bad signals:  {baseline_bad:4d} (avg outcome: {baseline_bad_outcome/baseline_bad if baseline_bad > 0 else 0:+.2f}%)")
    print(f"  Good signals: {baseline_good:4d} (avg outcome: {baseline_good_outcome/baseline_good if baseline_good > 0 else 0:+.2f}%)")
    print(f"  Total outcome: {baseline_total:+.2f}%")
    
    # With model (blocked = no trade)
    allowed_mask = ~would_block
    allowed_bad = (allowed_mask & actual_bad).sum()
    allowed_good = (allowed_mask & ~actual_bad).sum()
    
    allowed_bad_outcome = df[allowed_mask & actual_bad]["outcome_60m"].sum() if allowed_bad > 0 else 0
    allowed_good_outcome = df[allowed_mask & ~actual_bad]["outcome_60m"].sum() if allowed_good > 0 else 0
    model_total = allowed_bad_outcome + allowed_good_outcome
    
    print(f"\nWith Model (threshold={threshold:.2f}):")
    print(f"  Blocked:     {would_block.sum():4d} signals (prevented trading)")
    print(f"  Allowed bad:  {allowed_bad:4d} (avg outcome: {allowed_bad_outcome/allowed_bad if allowed_bad > 0 else 0:+.2f}%)")
    print(f"  Allowed good: {allowed_good:4d} (avg outcome: {allowed_good_outcome/allowed_good if allowed_good > 0 else 0:+.2f}%)")
    print(f"  Total outcome: {model_total:+.2f}%")
    
    # Improvement
    improvement = model_total - baseline_total
    improvement_pct = (improvement / abs(baseline_total)) * 100 if baseline_total != 0 else 0
    
    print(f"\n{'🎯 IMPROVEMENT' if improvement > 0 else '⚠️  REGRESSION'}:")
    print(f"  Absolute: {improvement:+.2f}% outcome improvement")
    print(f"  Relative: {improvement_pct:+.1f}% reduction in losses" if baseline_total < 0 else f"{improvement_pct:+.1f}% increase in gains")
    
    # Opportunity cost (blocked good signals)
    blocked_good_outcome = df[would_block & ~actual_bad]["outcome_60m"].sum() if fp > 0 else 0
    print(f"  Opportunity cost: {blocked_good_outcome:.2f}% (from blocking {fp} good signals)")
    
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision, "recall": recall, "f1": f1,
        "baseline_outcome": baseline_total,
        "model_outcome": model_total,
        "improvement": improvement,
        "improvement_pct": improvement_pct,
        "blocked_count": would_block.sum(),
        "opportunity_cost": blocked_good_outcome,
    }


def test_multiple_thresholds(df: pd.DataFrame, y_pred_proba: np.ndarray):
    """Test multiple thresholds to find optimal."""
    print(f"\n{'='*70}")
    print(f"THRESHOLD OPTIMIZATION")
    print(f"{'='*70}")
    
    thresholds = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    
    results = []
    for thresh in thresholds:
        result = evaluate_crash_protection(df, y_pred_proba, thresh)
        result["threshold"] = thresh
        results.append(result)
    
    # Find best threshold (maximize improvement)
    best = max(results, key=lambda x: x["improvement"])
    
    print(f"\n{'='*70}")
    print(f"BEST THRESHOLD: {best['threshold']:.2f}")
    print(f"{'='*70}")
    print(f"  Improvement: {best['improvement']:+.2f}% ({best['improvement_pct']:+.1f}%)")
    print(f"  Precision: {best['precision']:.1%}")
    print(f"  Recall: {best['recall']:.1%}")
    print(f"  Blocked: {best['blocked_count']} signals")
    
    return results


def analyze_crash_signature(df: pd.DataFrame, y_pred_proba: np.ndarray):
    """Analyze model predictions on crash signature pattern."""
    print(f"\n{'='*70}")
    print(f"CRASH SIGNATURE PATTERN ANALYSIS")
    print(f"{'='*70}")
    
    # Crash signature: compressed + weak_trend + neutral_momentum
    crash_sig_mask = (
        (df["dim_volatility"] == "compressed")
        & (df["dim_trend"].isin(["up_weak", "down_weak"]))
        & (df["dim_momentum"] == "neutral")
    )
    
    crash_sig_samples = df[crash_sig_mask]
    crash_sig_proba = y_pred_proba[crash_sig_mask]
    
    print(f"\nCrash signature samples: {crash_sig_mask.sum()}")
    
    if crash_sig_mask.sum() > 0:
        avg_proba = crash_sig_proba.mean()
        bad_in_sig = (crash_sig_samples["label_quality"] == "bad").sum()
        bad_pct = (bad_in_sig / len(crash_sig_samples)) * 100
        
        print(f"  Actual bad rate: {bad_in_sig}/{len(crash_sig_samples)} ({bad_pct:.1f}%)")
        print(f"  Avg predicted probability: {avg_proba:.1%}")
        print(f"  Model awareness: {'✅ DETECTS pattern' if avg_proba > 0.4 else '⚠️  MISSES pattern'}")
        
        # Avg outcomes
        avg_outcome_5m = crash_sig_samples["outcome_5m"].mean()
        avg_outcome_60m = crash_sig_samples["outcome_60m"].mean()
        avg_drawdown = crash_sig_samples["max_drawdown"].mean()
        
        print(f"\n  Avg outcomes in crash signature:")
        print(f"    5min:     {avg_outcome_5m:+.2f}%")
        print(f"    60min:    {avg_outcome_60m:+.2f}%")
        print(f"    Drawdown: {avg_drawdown:+.2f}%")


def main():
    import os
    load_dotenv(repo_root() / ".env")
    db_path = Path(os.getenv("TRADING_LAB_DB_PATH", str(repo_root() / "data" / "market.db")))
    db = Database(db_path)
    print(f"Using database: {db_path}")
    
    # Load model
    model, encoders, metadata = load_model()
    
    # Load Feb 3-6 samples
    df = load_feb3_samples(db)
    
    if len(df) == 0:
        print("No Feb 3-6 samples found!")
        return
    
    # Prepare features
    X = prepare_features(df, encoders)
    
    # Predict
    print("\nPredicting crash probabilities...")
    y_pred_proba = model.predict_proba(X)[:, 1]  # Probability of class 1 (bad)
    
    # Evaluate at default threshold
    print(f"\nModel predictions:")
    print(f"  Min probability:  {y_pred_proba.min():.3f}")
    print(f"  Max probability:  {y_pred_proba.max():.3f}")
    print(f"  Mean probability: {y_pred_proba.mean():.3f}")
    print(f"  Median probability: {np.median(y_pred_proba):.3f}")
    
    # Test multiple thresholds
    results = test_multiple_thresholds(df, y_pred_proba)
    
    # Analyze crash signature
    analyze_crash_signature(df, y_pred_proba)
    
    print(f"\n{'='*70}")
    print(f"✅ Validation complete!")
    print(f"{'='*70}")


if __name__ == "__main__":
    from pathlib import Path
    import os
    
    main()
