#!/usr/bin/env python3
"""
ML Crash Predictor Test Suite - Validate the model works correctly.

This script tests the crash predictor on:
1. Known crash samples (should predict high probability)
2. Known safe samples (should predict low probability)
3. Historical backtest (Feb 3-6 data)
4. Cross-validation metrics

Usage:
    python tests/test_crash_predictor.py
    python tests/test_crash_predictor.py --backtest
    python tests/test_crash_predictor.py --validate-threshold
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from core.common.env import load_dotenv
from core.common.paths import repo_root
from core.data.db import Database
from core.ml.crash_predictor import get_crash_predictor
from core.ml.crash_predictor_trainer import (
    load_crash_training_data,
    engineer_crash_label,
    prepare_features,
)


def test_crash_signature_detection():
    """Test that model correctly identifies known crash signature."""
    
    print("\n" + "="*80)
    print("TEST 1: CRASH SIGNATURE DETECTION")
    print("="*80)
    
    predictor = get_crash_predictor()
    
    if not predictor.is_loaded():
        print("❌ Model not loaded. Run training first:")
        print("   python -m core.ml.crash_predictor_trainer --train")
        return False
    
    # Known crash signature from Feb 3-6 analysis
    crash_snapshot = {
        "states": {
            "momentum": "neutral",
            "trend": "down_weak",
            "volatility": "compressed",
            "participation": "low",
            "location": "mid",
            "structure": "ranging",
        },
        "raw": {
            "rsi": 45.0,  # RSI danger zone (40-50)
            "stoch_k": 30.0,
            "macd_histogram": -0.5,
            "ema_9": 50000.0,
            "ema_21": 50100.0,
            "ema_50": 50200.0,
            "slope_20": -0.02,
            "atr_pct": 1.2,
            "bb_bandwidth": 0.015,  # Very compressed!
            "bb_pct": 0.3,
            "volume_ratio": 0.8,
            "vwap_distance_pct": -0.5,
        }
    }
    
    # Known safe conditions
    safe_snapshot = {
        "states": {
            "momentum": "oversold",
            "trend": "up_strong",
            "volatility": "expanding",
            "participation": "high",
            "location": "low",
            "structure": "trending",
        },
        "raw": {
            "rsi": 28.0,  # Oversold
            "stoch_k": 15.0,
            "macd_histogram": 0.8,
            "ema_9": 50000.0,
            "ema_21": 49800.0,
            "ema_50": 49500.0,
            "slope_20": 0.05,
            "atr_pct": 2.5,
            "bb_bandwidth": 0.045,  # Wide bands
            "bb_pct": 0.1,
            "volume_ratio": 1.5,
            "vwap_distance_pct": 0.2,
        }
    }
    
    # Test crash signature
    crash_prob = predictor.predict_crash_probability(crash_snapshot)
    should_block_crash, _, reason = predictor.should_block_trade(crash_snapshot)
    
    print("\n🚩 CRASH SIGNATURE TEST:")
    print(f"   Conditions: compressed + down_weak + neutral momentum")
    print(f"   RSI: 45 (danger zone)")
    print(f"   Crash Probability: {crash_prob:.2%}")
    print(f"   Should Block: {should_block_crash} ({reason})")
    
    crash_pass = crash_prob >= 0.60  # Should be at least 60% for crash signature
    print(f"   Result: {'✅ PASS' if crash_pass else '❌ FAIL'} (expected >= 60%)")
    
    # Test safe conditions
    safe_prob = predictor.predict_crash_probability(safe_snapshot)
    should_block_safe, _, _ = predictor.should_block_trade(safe_snapshot)
    
    print("\n✅ SAFE CONDITIONS TEST:")
    print(f"   Conditions: expanding + up_strong + oversold")
    print(f"   RSI: 28 (oversold)")
    print(f"   Crash Probability: {safe_prob:.2%}")
    print(f"   Should Block: {should_block_safe}")
    
    safe_pass = safe_prob <= 0.40  # Should be low for safe conditions
    print(f"   Result: {'✅ PASS' if safe_pass else '❌ FAIL'} (expected <= 40%)")
    
    return crash_pass and safe_pass


def test_threshold_validation():
    """Test different probability thresholds to find optimal balance."""
    
    print("\n" + "="*80)
    print("TEST 2: THRESHOLD VALIDATION")
    print("="*80)
    
    predictor = get_crash_predictor()
    
    if not predictor.is_loaded():
        print("❌ Model not loaded")
        return False
    
    load_dotenv()
    db = Database()
    
    # Load recent data
    df = load_crash_training_data(db, "2026-02-03", "2026-02-14")
    
    if len(df) == 0:
        print("❌ No test data available")
        return False
    
    y_true = engineer_crash_label(df)
    X, _ = prepare_features(df)
    
    # Get predictions
    crash_probs = predictor.model.predict_proba(X)[:, 1]
    
    # Test different thresholds
    thresholds = [0.50, 0.60, 0.70, 0.80, 0.90]
    
    print("\nThreshold Analysis:")
    print(f"{'Threshold':<12} {'Blocked':<10} {'Crashes Caught':<15} {'False Alarms':<15} {'Miss Rate':<12}")
    print("-" * 80)
    
    for thresh in thresholds:
        y_pred = (crash_probs >= thresh).astype(int)
        
        blocked = y_pred.sum()
        crashes_caught = ((y_pred == 1) & (y_true == 1)).sum()
        false_alarms = ((y_pred == 1) & (y_true == 0)).sum()
        missed_crashes = ((y_pred == 0) & (y_true == 1)).sum()
        
        total_crashes = y_true.sum()
        catch_rate = crashes_caught / total_crashes if total_crashes > 0 else 0
        miss_rate = missed_crashes / total_crashes if total_crashes > 0 else 0
        
        print(f"{thresh:<12.2f} {blocked:<10} {crashes_caught}/{total_crashes} ({catch_rate:.1%}){'':<3} "
              f"{false_alarms:<15} {miss_rate:<12.1%}")
    
    print(f"\nTotal samples: {len(df)}")
    print(f"Total crashes: {y_true.sum()} ({y_true.mean():.1%})")
    print(f"Total safe: {(~y_true.astype(bool)).sum()} ({(1-y_true.mean()):.1%})")
    
    return True


def backtest_feb_3_crash(verbose: bool = True):
    """Backtest: How many Feb 3 losses would the model have prevented?"""
    
    print("\n" + "="*80)
    print("TEST 3: FEBRUARY 3 CRASH BACKTEST")
    print("="*80)
    
    predictor = get_crash_predictor()
    
    if not predictor.is_loaded():
        print("❌ Model not loaded")
        return False
    
    load_dotenv()
    db = Database()
    
    # Load Feb 3 data specifically
    rows = db.query(
        """
        SELECT 
            id, created_at, symbol, pattern_id,
            dim_momentum, dim_trend, dim_volatility,
            outcome_5m, max_drawdown,
            raw_rsi, raw_stoch_k, raw_macd_histogram,
            raw_bb_bandwidth, raw_atr_pct
        FROM ml_training_samples
        WHERE DATE(created_at) = '2026-02-03'
          AND outcome_5m IS NOT NULL
        ORDER BY outcome_5m ASC
        """,
    )
    
    if not rows:
        print("❌ No Feb 3 data found")
        return False
    
    blocked_count = 0
    blocked_crashes = 0
    false_blocks = 0
    total_loss_prevented = 0.0
    
    results = []
    
    for row in rows:
        row_dict = dict(row)
        
        # Reconstruct dimension snapshot
        snapshot = {
            "states": {
                "momentum": row_dict.get("dim_momentum", "unknown"),
                "trend": row_dict.get("dim_trend", "unknown"),
                "volatility": row_dict.get("dim_volatility", "unknown"),
                "participation": "low",  # Default
                "location": "mid",
                "structure": "ranging",
            },
            "raw": {
                "rsi": row_dict.get("raw_rsi", 50.0),
                "stoch_k": row_dict.get("raw_stoch_k", 50.0),
                "macd_histogram": row_dict.get("raw_macd_histogram", 0.0),
                "ema_9": 50000.0,
                "ema_21": 50000.0,
                "ema_50": 50000.0,
                "slope_20": 0.0,
                "atr_pct": row_dict.get("raw_atr_pct", 1.0),
                "bb_bandwidth": row_dict.get("raw_bb_bandwidth", 0.02),
                "bb_pct": 0.5,
                "volume_ratio": 1.0,
                "vwap_distance_pct": 0.0,
            }
        }
        
        # Get model prediction
        should_block, crash_prob, reason = predictor.should_block_trade(snapshot)
        
        outcome_5m = row_dict.get("outcome_5m", 0.0) or 0.0
        is_actual_crash = outcome_5m <= -3.0
        
        if should_block:
            blocked_count += 1
            
            if is_actual_crash:
                blocked_crashes += 1
                # Assume $1000 position, calculate loss prevented
                loss_prevented = abs(outcome_5m / 100) * 1000
                total_loss_prevented += loss_prevented
            else:
                false_blocks += 1
        
        results.append({
            "pattern": row_dict["pattern_id"],
            "crash_prob": crash_prob,
            "blocked": should_block,
            "outcome_5m": outcome_5m,
            "is_crash": is_actual_crash,
        })
    
    total_samples = len(rows)
    total_crashes = sum(1 for r in results if r["is_crash"])
    
    print(f"\n📊 Backtest Results (Feb 3, 2026):")
    print(f"   Total signals: {total_samples}")
    print(f"   Actual crashes: {total_crashes} ({total_crashes/total_samples:.1%})")
    print(f"\n   Trades blocked by ML: {blocked_count} ({blocked_count/total_samples:.1%})")
    print(f"   Crashes prevented: {blocked_crashes}/{total_crashes} ({blocked_crashes/total_crashes:.1%})")
    print(f"   False blocks (blocked safe trades): {false_blocks}")
    print(f"\n   💰 Estimated loss prevented: ${total_loss_prevented:.2f}")
    
    if verbose:
        print("\n📋 Top 10 Worst Crashes (sorted by outcome):")
        print(f"{'Pattern':<30} {'Crash P':<10} {'Blocked':<10} {'Outcome':<10}")
        print("-" * 70)
        
        sorted_results = sorted(results, key=lambda x: x["outcome_5m"])[:10]
        for r in sorted_results:
            pattern_short = r["pattern"][:28]
            blocked_icon = "🛡️ YES" if r["blocked"] else "❌ NO"
            print(f"{pattern_short:<30} {r['crash_prob']:>6.1%}    {blocked_icon:<10} {r['outcome_5m']:>8.2f}%")
    
    # Calculate effectiveness
    effectiveness = blocked_crashes / total_crashes if total_crashes > 0 else 0
    false_alarm_rate = false_blocks / blocked_count if blocked_count > 0 else 0
    
    print(f"\n📈 Model Performance:")
    print(f"   Effectiveness (recall): {effectiveness:.1%}")
    print(f"   False alarm rate: {false_alarm_rate:.1%}")
    
    # Pass if caught >60% of crashes with <30% false alarms
    pass_test = effectiveness >= 0.60 and false_alarm_rate <= 0.30
    print(f"\n   Result: {'✅ PASS' if pass_test else '❌ FAIL'}")
    
    return pass_test


def test_model_info():
    """Test that model metadata is accessible."""
    
    print("\n" + "="*80)
    print("TEST 4: MODEL METADATA")
    print("="*80)
    
    predictor = get_crash_predictor()
    
    if not predictor.is_loaded():
        print("❌ Model not loaded")
        return False
    
    info = predictor.get_model_info()
    
    print(f"\n📦 Model Information:")
    print(f"   Status: {info.get('status')}")
    print(f"   Trained: {info.get('trained_at')}")
    print(f"   Optimal Threshold: {info.get('optimal_threshold', 0):.2f}")
    
    metrics = info.get('metrics', {})
    if metrics:
        print(f"\n📊 Training Metrics:")
        print(f"   ROC AUC: {metrics.get('roc_auc', 0):.3f}")
        print(f"   Precision: {metrics.get('precision', 0):.3f}")
        print(f"   Recall: {metrics.get('recall', 0):.3f}")
    
    print(f"\n   Model Path: {info.get('model_path')}")
    
    return True


def main():
    parser = argparse.ArgumentParser(description="Test ML crash predictor")
    parser.add_argument("--signature", action="store_true", help="Test crash signature detection")
    parser.add_argument("--threshold", action="store_true", help="Test threshold validation")
    parser.add_argument("--backtest", action="store_true", help="Backtest on Feb 3 crash")
    parser.add_argument("--info", action="store_true", help="Show model info")
    parser.add_argument("--all", action="store_true", help="Run all tests")
    
    args = parser.parse_args()
    
    load_dotenv()
    
    # Run all if no specific test selected
    run_all = args.all or not any([args.signature, args.threshold, args.backtest, args.info])
    
    results = []
    
    if run_all or args.signature:
        results.append(("Crash Signature Detection", test_crash_signature_detection()))
    
    if run_all or args.info:
        results.append(("Model Metadata", test_model_info()))
    
    if run_all or args.threshold:
        results.append(("Threshold Validation", test_threshold_validation()))
    
    if run_all or args.backtest:
        results.append(("Feb 3 Backtest", backtest_feb_3_crash()))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name:<40} {status}")
    
    total_pass = sum(1 for _, p in results if p)
    total_tests = len(results)
    
    print(f"\nPassed: {total_pass}/{total_tests}")
    
    if total_pass == total_tests:
        print("\n🎉 All tests passed! Model is working correctly.")
    else:
        print("\n⚠️ Some tests failed. Check model training or data quality.")


if __name__ == "__main__":
    main()
