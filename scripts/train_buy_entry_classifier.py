#!/usr/bin/env python3
"""
Buy Entry Classifier Training Script.

Trains a model to predict whether a buy signal is a good entry (reversal is real)
or a bad entry (buying too early, price continues falling).

Root cause identified 2026-02-25:
  - Bad buys enter when RSI ~36.5, Stoch ~28.9, BB% ~0.303 (not fully oversold)
  - Good buys enter when RSI ~32.7, Stoch ~23.9, BB% ~0.206 + higher volume confirmation

Usage:
    cd /opt/homelab-panel/trading-lab
    PYTHONPATH=/opt/homelab-panel/trading-lab python3 scripts/train_buy_entry_classifier.py
"""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

from core.common.paths import repo_root
from core.data.db import Database, log_dev_event
from core.ml.buy_entry_trainer import (
    load_buy_training_data,
    engineer_entry_label,
    prepare_features,
    train_classifier,
    evaluate_model,
    save_model,
)


def backup_existing(model_dir: Path) -> None:
    model_path = model_dir / "buy_entry_classifier.joblib"
    if not model_path.exists():
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = model_dir / "backups" / timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)
    for f in ["buy_entry_classifier.joblib", "encoders.joblib", "metadata.json"]:
        src = model_dir / f
        if src.exists():
            shutil.copy2(src, backup_dir / f)
    print(f"Backed up existing model → {backup_dir.name}/")


def main():
    parser = argparse.ArgumentParser(description="Train buy entry quality classifier")
    parser.add_argument("--start-date", default="2026-02-03")
    parser.add_argument("--end-date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument(
        "--model-type",
        choices=["random_forest", "gradient_boosting"],
        default="random_forest",
    )
    parser.add_argument("--skip-backup", action="store_true")
    args = parser.parse_args()

    db_path = repo_root() / "data" / "market.db"
    db = Database(db_path)
    model_dir = repo_root() / "models" / "buy_entry_classifier"

    print("\n" + "=" * 60)
    print("BUY ENTRY CLASSIFIER TRAINING")
    print("=" * 60)
    print(f"Period: {args.start_date} → {args.end_date}")
    print(f"Model:  {args.model_type}")
    print(f"Target: buy signals only, good(1) vs bad(0), neutral excluded")
    print()

    if not args.skip_backup:
        backup_existing(model_dir)

    # Load data
    print("\n📊 Loading training data...")
    df = load_buy_training_data(db, args.start_date, args.end_date)

    if len(df) < 100:
        print(f"❌ Too few samples ({len(df)}). Need at least 100.")
        return

    y = engineer_entry_label(df)
    print(f"\nLabel distribution:")
    print(f"  Good entries (1): {y.sum()} ({y.mean()*100:.1f}%)")
    print(f"  Bad entries  (0): {(~y.astype(bool)).sum()} ({(1-y.mean())*100:.1f}%)")

    # Features
    print("\n🔧 Preparing features...")
    X, encoders = prepare_features(df)

    # Time-based split (no look-ahead bias)
    n = len(X)
    train_end = int(n * 0.70)
    val_end = int(n * 0.85)

    X_train, y_train = X.iloc[:train_end], y.iloc[:train_end]
    X_val,   y_val   = X.iloc[train_end:val_end], y.iloc[train_end:val_end]
    X_test,  y_test  = X.iloc[val_end:], y.iloc[val_end:]

    print(f"\n📊 Time-based splits:")
    print(f"  Train:      {len(X_train)} ({y_train.mean()*100:.1f}% good)")
    print(f"  Validation: {len(X_val)} ({y_val.mean()*100:.1f}% good)")
    print(f"  Test:       {len(X_test)} ({y_test.mean()*100:.1f}% good)")

    # Train
    print(f"\n🤖 Training {args.model_type}...")
    model = train_classifier(X_train, y_train, args.model_type)

    # Evaluate
    val_metrics = evaluate_model(model, X_val, y_val, X.columns.tolist(), label="Validation")
    test_metrics = evaluate_model(model, X_test, y_test, X.columns.tolist(), label="Test (Final)")
    test_metrics["val_metrics"] = val_metrics

    # Save
    print("\n💾 Saving model...")
    save_model(model, encoders, test_metrics, model_dir)

    # Log to devloop
    log_dev_event(
        db,
        "INFO",
        "ml_training_completed",
        f"Trained buy_entry_classifier on {len(df)} buy samples",
        {
            "model": "buy_entry_classifier",
            "total_samples": len(df),
            "good_samples": int(y.sum()),
            "bad_samples": int((~y.astype(bool)).sum()),
            "roc_auc": test_metrics.get("roc_auc"),
            "optimal_threshold": test_metrics.get("optimal_threshold"),
            "precision": test_metrics.get("precision"),
            "recall": test_metrics.get("recall"),
        },
    )

    print("\n" + "=" * 60)
    print("✅ TRAINING COMPLETE")
    print("=" * 60)
    print(f"ROC AUC:           {test_metrics.get('roc_auc', 0):.3f}")
    print(f"Optimal threshold: {test_metrics.get('optimal_threshold', 0):.3f}")
    print(f"Precision:         {test_metrics.get('precision', 0):.3f}")
    print(f"Recall:            {test_metrics.get('recall', 0):.3f}")
    print()
    print("Next steps:")
    print("  1. Restart trading bots to load new model")
    print("  2. Executor will gate buys using this model automatically")
    print("  3. Retrain in 2 weeks with fresh data")


if __name__ == "__main__":
    main()
