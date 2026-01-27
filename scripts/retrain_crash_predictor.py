#!/usr/bin/env python3
"""
Bi-Weekly ML Training Pipeline - Continuous learning for crash predictor.

This script should be run every 2 weeks to retrain the crash predictor
with new data, growing the dataset over time.

Features:
- Incremental learning: Uses all historical data
- Version control: Keeps backups of previous models
- Metrics tracking: Logs performance over time
- Cloud export: Optionally exports training data to cloud storage

Usage:
    # Manual run
    python scripts/retrain_crash_predictor.py
    
    # Scheduled with cron (every 2 weeks on Sunday 2am)
    0 2 */14 * 0 cd /opt/homelab-panel/trading-lab && python scripts/retrain_crash_predictor.py
"""
from __future__ import annotations

import argparse
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from core.common.env import load_dotenv
from core.common.paths import repo_root
from core.data.db import Database, log_dev_event
from core.ml.crash_predictor_trainer import (
    load_crash_training_data,
    engineer_crash_label,
    prepare_features,
    train_crash_predictor,
    evaluate_model,
    save_model,
)


def backup_existing_model(model_dir: Path) -> bool:
    """Backup existing model before retraining."""
    model_path = model_dir / "crash_predictor.joblib"
    
    if not model_path.exists():
        print("No existing model to backup")
        return False
    
    # Create backup with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = model_dir / "backups" / timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy model files
    for file in ["crash_predictor.joblib", "encoders.joblib", "metadata.json"]:
        src = model_dir / file
        if src.exists():
            dst = backup_dir / file
            shutil.copy2(src, dst)
            print(f"Backed up: {file} -> {backup_dir.name}/")
    
    return True


def cleanup_old_backups(model_dir: Path, keep_last: int = 5) -> None:
    """Keep only the N most recent backups."""
    backup_dir = model_dir / "backups"
    
    if not backup_dir.exists():
        return
    
    backups = sorted([d for d in backup_dir.iterdir() if d.is_dir()])
    
    if len(backups) > keep_last:
        for old_backup in backups[:-keep_last]:
            print(f"Deleting old backup: {old_backup.name}")
            shutil.rmtree(old_backup)


def export_to_cloud(db: Database, export_type: str = "incremental") -> None:
    """
    Export training data to Namecheap Stellar DB (cloud storage).
    
    Args:
        db: Database connection
        export_type: "full" or "incremental" (only new data since last export)
    """
    print("\n🌩️  Cloud Export to Namecheap Stellar DB")
    print("=" * 60)
    
    # TODO: Implement cloud export logic
    # This would use the Namecheap Stellar DB API to upload training data
    # For now, we'll export to a local file that can be uploaded
    
    export_dir = repo_root() / "trading-lab" / "data" / "ml_exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if export_type == "full":
        # Export all training data
        rows = db.query(
            "SELECT * FROM ml_training_samples ORDER BY created_at ASC"
        )
        filename = f"crash_training_full_{timestamp}.csv"
    else:
        # Export only last 30 days
        cutoff = (datetime.now() - timedelta(days=30)).isoformat()
        rows = db.query(
            "SELECT * FROM ml_training_samples WHERE created_at > ? ORDER BY created_at ASC",
            (cutoff,),
        )
        filename = f"crash_training_incremental_{timestamp}.csv"
    
    import csv
    
    export_path = export_dir / filename
    
    if rows:
        keys = rows[0].keys()
        with open(export_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))
        
        print(f"✅ Exported {len(rows)} samples to {export_path}")
        print(f"📁 Size: {export_path.stat().st_size / 1024:.1f} KB")
        print("\nTo upload to Namecheap Stellar DB:")
        print(f"  1. Log in to your Namecheap Stellar DB dashboard")
        print(f"  2. Upload {export_path.name}")
        print(f"  3. Or use API: curl -F 'file=@{export_path}' https://stellar.namecheap.com/api/upload")
    else:
        print("⚠️  No data to export")


def main():
    parser = argparse.ArgumentParser(
        description="Bi-weekly ML training pipeline for crash predictor"
    )
    parser.add_argument(
        "--start-date",
        help="Start date for training data (YYYY-MM-DD). Default: 30 days ago",
    )
    parser.add_argument(
        "--end-date",
        help="End date for training data (YYYY-MM-DD). Default: today",
    )
    parser.add_argument(
        "--skip-backup",
        action="store_true",
        help="Skip backing up existing model",
    )
    parser.add_argument(
        "--export-cloud",
        choices=["none", "incremental", "full"],
        default="incremental",
        help="Export training data to cloud storage",
    )
    parser.add_argument(
        "--model-type",
        choices=["random_forest", "gradient_boosting"],
        default="random_forest",
        help="Type of model to train",
    )
    
    args = parser.parse_args()
    
    # Load environment variables from .env file
    env_path = repo_root() / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    
    # Initialize database connection
    db_path = repo_root() / "data" / "market.db"
    db = Database(db_path)
    model_dir = repo_root() / "models" / "crash_predictor"
    
    # Determine date range
    if args.end_date:
        end_date = args.end_date
    else:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    if args.start_date:
        start_date = args.start_date
    else:
        # Use all data from crash period onwards
        start_date = "2026-02-03"
    
    print("\n" + "=" * 60)
    print("🔄 BI-WEEKLY CRASH PREDICTOR RETRAINING")
    print("=" * 60)
    print(f"Training period: {start_date} to {end_date}")
    print(f"Model type: {args.model_type}")
    print()
    
    # Backup existing model
    if not args.skip_backup:
        backup_existing_model(model_dir)
        cleanup_old_backups(model_dir, keep_last=5)
    
    # Load training data
    print("\n📊 Loading training data...")
    df = load_crash_training_data(db, start_date, end_date)
    
    if len(df) == 0:
        print("❌ No training data found!")
        return
    
    print(f"✅ Loaded {len(df)} samples")
    
    # Engineer labels
    y = engineer_crash_label(df)
    crash_count = y.sum()
    safe_count = len(y) - crash_count
    
    print(f"\n📈 Dataset composition:")
    print(f"  Crash samples: {crash_count} ({crash_count/len(y)*100:.1f}%)")
    print(f"  Safe samples: {safe_count} ({safe_count/len(y)*100:.1f}%)")
    
    # Prepare features
    print("\n🔧 Preparing features...")
    X, encoders = prepare_features(df)
    
    # Train model (use all data for production model)
    print(f"\n🤖 Training {args.model_type} model...")
    model = train_crash_predictor(X, y, args.model_type)
    
    # Evaluate on full dataset (for reference)
    print("\n📊 Evaluating model performance...")
    metrics = evaluate_model(model, X, y, X.columns.tolist())
    
    # Save model
    print("\n💾 Saving model...")
    save_model(model, encoders, metrics, model_dir)
    
    # Log training event
    log_dev_event(
        db,
        "INFO",
        "ml_training_completed",
        f"Retrained crash predictor on {len(df)} samples",
        {
            "start_date": start_date,
            "end_date": end_date,
            "total_samples": len(df),
            "crash_samples": int(crash_count),
            "safe_samples": int(safe_count),
            "model_type": args.model_type,
            "metrics": metrics,
        },
    )
    
    # Export to cloud
    if args.export_cloud != "none":
        export_to_cloud(db, args.export_cloud)
    
    print("\n" + "=" * 60)
    print("✅ RETRAINING COMPLETE!")
    print("=" * 60)
    print(f"Model saved to: {model_dir}")
    print(f"ROC AUC: {metrics.get('roc_auc', 0):.3f}")
    print(f"Precision: {metrics.get('precision', 0):.3f}")
    print(f"Recall: {metrics.get('recall', 0):.3f}")
    print()
    print("Next steps:")
    print("  1. Restart trading bot to load new model")
    print("  2. Monitor crash detection in production")
    print("  3. Run this script again in 2 weeks")
    print()


if __name__ == "__main__":
    main()
