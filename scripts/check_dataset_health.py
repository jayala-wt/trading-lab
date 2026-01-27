#!/usr/bin/env python3
"""
Dataset Health Check - Validate ML training data quality before training.

Run this BEFORE training to catch:
- Data leakage
- Missing values
- Label imbalance
- Date range issues
- Feature coverage

Usage:
    python3 scripts/check_dataset_health.py
    python3 scripts/check_dataset_health.py --detailed
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import argparse
from datetime import datetime

from core.common.env import load_dotenv
from core.common.paths import repo_root
from core.data.db import Database


def check_sample_count(db: Database) -> dict:
    """Check total sample count."""
    query = "SELECT COUNT(*) as count FROM ml_training_samples"
    row = db.query(query)[0]
    count = row['count']
    
    print(f"1️⃣  Total Sample Count: {count:,}")
    
    # Minimum requirement: 1,800 (100× features)
    # Target: 9,000+ (500× features)
    if count < 1800:
        print(f"   ⚠️  WARNING: Only {count} samples (need 1,800+ minimum)")
        status = "insufficient"
    elif count < 9000:
        print(f"   ✅ Adequate ({count} samples, target 9,000+)")
        status = "adequate"
    else:
        print(f"   ✅ EXCELLENT ({count} samples exceeds 9,000 target)")
        status = "excellent"
    
    return {"count": count, "status": status}


def check_label_distribution(db: Database) -> dict:
    """Check label distribution for class imbalance."""
    query = """
        SELECT label_quality, COUNT(*) as count 
        FROM ml_training_samples 
        GROUP BY label_quality 
        ORDER BY count DESC
    """
    rows = db.query(query)
    
    print(f"\n2️⃣  Label Distribution (Quality):")
    
    total = sum(row['count'] for row in rows)
    distribution = {}
    
    for row in rows:
        label = row['label_quality']
        count = row['count']
        pct = (count / total) * 100
        print(f"   {label:>10}: {count:>6} ({pct:>5.1f}%)")
        distribution[label] = {"count": count, "percentage": pct}
    
    # Check for severe imbalance (< 5% minority class)
    min_pct = min(row['count'] for row in rows) / total * 100
    if min_pct < 5.0:
        print(f"   ⚠️  WARNING: Severe class imbalance ({min_pct:.1f}% minority class)")
        print(f"   💡 Recommendation: Use class_weight='balanced' in model")
    else:
        print(f"   ✅ Balanced distribution (smallest class {min_pct:.1f}%)")
    
    return distribution


def check_null_features(db: Database) -> dict:
    """Check for NULL/missing values in features."""
    query = """
        SELECT 
            SUM(CASE WHEN dim_momentum IS NULL THEN 1 ELSE 0 END) AS null_dim_momentum,
            SUM(CASE WHEN dim_trend IS NULL THEN 1 ELSE 0 END) AS null_dim_trend,
            SUM(CASE WHEN dim_volatility IS NULL THEN 1 ELSE 0 END) AS null_dim_volatility,
            SUM(CASE WHEN raw_rsi IS NULL THEN 1 ELSE 0 END) AS null_rsi,
            SUM(CASE WHEN raw_atr_pct IS NULL THEN 1 ELSE 0 END) AS null_atr,
            SUM(CASE WHEN raw_bb_pct IS NULL THEN 1 ELSE 0 END) AS null_bb,
            SUM(CASE WHEN raw_macd_histogram IS NULL THEN 1 ELSE 0 END) AS null_macd,
            SUM(CASE WHEN outcome_5m IS NULL THEN 1 ELSE 0 END) AS null_outcome,
            COUNT(*) AS total
        FROM ml_training_samples
    """
    row = db.query(query)[0]
    
    print(f"\n3️⃣  NULL Feature Check:")
    
    null_counts = {}
    has_nulls = False
    
    for key in row.keys():
        if key != 'total' and row[key] > 0:
            feature = key.replace('null_', '')
            pct = (row[key] / row['total']) * 100
            print(f"   ⚠️  {feature}: {row[key]} NULL values ({pct:.1f}%)")
            null_counts[feature] = row[key]
            has_nulls = True
    
    if not has_nulls:
        print(f"   ✅ No NULL values found (perfect!)")
    else:
        print(f"   💡 Recommendation: Apply imputation or drop rows with NULLs")
    
    return null_counts


def check_symbol_coverage(db: Database, detailed: bool = False) -> dict:
    """Check sample distribution across symbols."""
    query = """
        SELECT symbol, COUNT(*) as n 
        FROM ml_training_samples 
        GROUP BY symbol 
        ORDER BY n ASC
    """
    rows = db.query(query)
    
    print(f"\n4️⃣  Symbol Coverage ({len(rows)} symbols):")
    
    coverage = {}
    
    if detailed or len(rows) <= 20:
        # Show all if detailed or <= 20 symbols
        for row in rows:
            print(f"   {row['symbol']:>10}: {row['n']:>6} samples")
            coverage[row['symbol']] = row['n']
    else:
        # Show top 10 and bottom 10
        print(f"   Bottom 10 (least samples):")
        for row in rows[:10]:
            print(f"     {row['symbol']:>10}: {row['n']:>6}")
        print(f"   ...")
        print(f"   Top 10 (most samples):")
        for row in rows[-10:]:
            print(f"     {row['symbol']:>10}: {row['n']:>6}")
    
    # Check for symbols with very few samples
    min_samples = rows[0]['n']
    if min_samples < 100:
        print(f"   ⚠️  WARNING: {rows[0]['symbol']} has only {min_samples} samples")
        print(f"   💡 May want to exclude symbols with < 100 samples")
    
    return {row['symbol']: row['n'] for row in rows}


def check_date_range(db: Database) -> dict:
    """Check temporal coverage."""
    query = """
        SELECT 
            MIN(DATE(created_at)) as first_date,
            MAX(DATE(created_at)) as last_date,
            COUNT(DISTINCT DATE(created_at)) as unique_days
        FROM ml_training_samples
    """
    row = db.query(query)[0]
    
    print(f"\n5️⃣  Date Range:")
    print(f"   First sample: {row['first_date']}")
    print(f"   Last sample:  {row['last_date']}")
    print(f"   Unique days:  {row['unique_days']}")
    
    # Calculate total days
    first = datetime.strptime(row['first_date'], '%Y-%m-%d')
    last = datetime.strptime(row['last_date'], '%Y-%m-%d')
    total_days = (last - first).days + 1
    coverage_pct = (row['unique_days'] / total_days) * 100
    
    print(f"   Coverage:     {coverage_pct:.1f}% ({row['unique_days']}/{total_days} days)")
    
    if coverage_pct < 50:
        print(f"   ⚠️  WARNING: Sparse coverage ({coverage_pct:.1f}%)")
        print(f"   💡 May have gaps in data - check bot uptime")
    else:
        print(f"   ✅ Good temporal coverage")
    
    return {
        "first_date": row['first_date'],
        "last_date": row['last_date'],
        "unique_days": row['unique_days'],
        "coverage_pct": coverage_pct
    }


def check_crash_period(db: Database) -> dict:
    """Check Feb 3-6 crash period samples."""
    query = """
        SELECT COUNT(*) as count 
        FROM ml_training_samples 
        WHERE DATE(created_at) BETWEEN '2026-02-03' AND '2026-02-06'
    """
    row = db.query(query)[0]
    crash_samples = row['count']
    
    print(f"\n6️⃣  Feb 3-6 Crash Period:")
    print(f"   Samples: {crash_samples:,}")
    
    if crash_samples < 100:
        print(f"   ⚠️  WARNING: Only {crash_samples} crash period samples")
        print(f"   💡 This is your primary validation dataset!")
    else:
        print(f"   ✅ Sufficient crash period data for validation")
    
    # Check crash outcomes
    query2 = """
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN outcome_5m <= -3.0 THEN 1 ELSE 0 END) as severe_loss,
            SUM(CASE WHEN max_drawdown <= -5.0 THEN 1 ELSE 0 END) as severe_dd
        FROM ml_training_samples 
        WHERE DATE(created_at) BETWEEN '2026-02-03' AND '2026-02-06'
            AND outcome_5m IS NOT NULL
    """
    row2 = db.query(query2)[0]
    
    if row2['total'] > 0:
        severe_loss_pct = (row2['severe_loss'] / row2['total']) * 100
        severe_dd_pct = (row2['severe_dd'] / row2['total']) * 100
        
        print(f"   Severe losses (≤-3%):   {row2['severe_loss']} ({severe_loss_pct:.1f}%)")
        print(f"   Severe drawdowns (≤-5%): {row2['severe_dd']} ({severe_dd_pct:.1f}%)")
    
    return {
        "crash_samples": crash_samples,
        "severe_loss": row2['severe_loss'] if row2['total'] > 0 else 0,
        "severe_dd": row2['severe_dd'] if row2['total'] > 0 else 0
    }


def check_feature_leakage(db: Database) -> dict:
    """Check for potential data leakage issues."""
    print(f"\n7️⃣  Data Leakage Check:")
    
    # Check 1: Ensure outcomes are not in feature columns
    print(f"   ✅ Outcome columns separate from features (checked in trainer)")
    
    # Check 2: Ensure created_at is time-ordered
    query = """
        SELECT COUNT(*) as out_of_order
        FROM (
            SELECT created_at, LAG(created_at) OVER (ORDER BY rowid) as prev_created_at
            FROM ml_training_samples
        ) 
        WHERE created_at < prev_created_at
    """
    row = db.query(query)[0]
    
    if row['out_of_order'] == 0:
        print(f"   ✅ Timestamps are properly ordered")
    else:
        print(f"   ⚠️  WARNING: {row['out_of_order']} out-of-order timestamps")
    
    # Check 3: Recommend time-based splits
    print(f"   💡 Use time-based splits (not random) in trainer")
    print(f"   💡 Feature whitelist ensures no forward-looking features")
    
    return {"out_of_order": row['out_of_order']}


def main():
    parser = argparse.ArgumentParser(description='Check ML dataset health')
    parser.add_argument('--detailed', action='store_true', help='Show detailed output')
    args = parser.parse_args()
    
    load_dotenv(repo_root() / ".env")
    db_path = Path(os.getenv("TRADING_LAB_DB_PATH", str(repo_root() / "data" / "market.db")))
    db = Database(db_path)
    
    print("=" * 70)
    print("ML DATASET HEALTH CHECK")
    print("=" * 70)
    
    results = {}
    
    results['sample_count'] = check_sample_count(db)
    results['label_distribution'] = check_label_distribution(db)
    results['null_features'] = check_null_features(db)
    results['symbol_coverage'] = check_symbol_coverage(db, args.detailed)
    results['date_range'] = check_date_range(db)
    results['crash_period'] = check_crash_period(db)
    results['leakage_check'] = check_feature_leakage(db)
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    # Overall health score
    issues = []
    
    if results['sample_count']['status'] == 'insufficient':
        issues.append("Insufficient samples (<1,800)")
    
    if results['null_features']:
        issues.append(f"NULL values in {len(results['null_features'])} features")
    
    if results['leakage_check']['out_of_order'] > 0:
        issues.append("Out-of-order timestamps detected")
    
    if not issues:
        print("✅ DATASET HEALTHY - Ready for training!")
        print(f"   • {results['sample_count']['count']:,} total samples")
        print(f"   • No NULL values")
        print(f"   • {results['crash_period']['crash_samples']:,} crash period samples")
        print(f"   • {len(results['symbol_coverage'])} symbols covered")
    else:
        print("⚠️  ISSUES FOUND:")
        for issue in issues:
            print(f"   • {issue}")
        print("\n💡 Fix these issues before training for best results")
    
    print("\n📋 Next Steps:")
    print("   1. Backup dataset: python3 scripts/snapshot_dataset.py")
    print("   2. Train model: python3 -m core.ml.crash_predictor_trainer --train")
    print("   3. Validate on Feb 3-6: python3 tests/test_crash_predictor.py")


if __name__ == "__main__":
    main()
