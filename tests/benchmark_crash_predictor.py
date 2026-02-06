#!/usr/bin/env python3
"""
ML Crash Predictor Performance Benchmark

Tests inference speed to ensure it doesn't impact trading execution.
Target: <10ms per prediction (100+ predictions/second)

Usage:
    python tests/benchmark_crash_predictor.py
"""
from __future__ import annotations

import time
import statistics
from typing import List

from core.common.env import load_dotenv
from core.ml.crash_predictor import get_crash_predictor


def generate_test_snapshots(count: int) -> List[dict]:
    """Generate random market snapshots for testing."""
    import random
    
    snapshots = []
    
    momentum_states = ["oversold", "neutral", "overbought"]
    trend_states = ["down_strong", "down_weak", "up_weak", "up_strong"]
    volatility_states = ["compressed", "normal", "expanding"]
    
    for _ in range(count):
        snapshot = {
            "states": {
                "momentum": random.choice(momentum_states),
                "trend": random.choice(trend_states),
                "volatility": random.choice(volatility_states),
                "participation": random.choice(["low", "normal", "high"]),
                "location": random.choice(["low", "mid", "high"]),
                "structure": random.choice(["trending", "ranging"]),
            },
            "raw": {
                "rsi": random.uniform(20, 80),
                "stoch_k": random.uniform(0, 100),
                "macd_histogram": random.uniform(-2, 2),
                "ema_9": random.uniform(45000, 55000),
                "ema_21": random.uniform(45000, 55000),
                "ema_50": random.uniform(45000, 55000),
                "slope_20": random.uniform(-0.05, 0.05),
                "atr_pct": random.uniform(0.5, 3.0),
                "bb_bandwidth": random.uniform(0.01, 0.05),
                "bb_pct": random.uniform(0, 1),
                "volume_ratio": random.uniform(0.5, 2.0),
                "vwap_distance_pct": random.uniform(-1, 1),
            }
        }
        snapshots.append(snapshot)
    
    return snapshots


def benchmark_single_prediction(predictor, snapshot: dict) -> float:
    """Measure time for single prediction in milliseconds."""
    start = time.perf_counter()
    _ = predictor.predict_crash_probability(snapshot)
    end = time.perf_counter()
    return (end - start) * 1000  # Convert to milliseconds


def benchmark_batch_predictions(predictor, snapshots: List[dict]) -> dict:
    """Benchmark multiple predictions and return statistics."""
    
    print(f"\n🔬 Running {len(snapshots)} predictions...")
    
    timings = []
    
    for snapshot in snapshots:
        timing = benchmark_single_prediction(predictor, snapshot)
        timings.append(timing)
    
    return {
        "count": len(timings),
        "mean": statistics.mean(timings),
        "median": statistics.median(timings),
        "min": min(timings),
        "max": max(timings),
        "stdev": statistics.stdev(timings) if len(timings) > 1 else 0,
        "p95": sorted(timings)[int(len(timings) * 0.95)],
        "p99": sorted(timings)[int(len(timings) * 0.99)],
    }


def benchmark_model_loading() -> dict:
    """Measure model loading time (happens once at startup)."""
    
    print("\n⏱️  Benchmarking model loading (startup cost)...")
    
    # Clear any cached instance
    from core.ml import crash_predictor
    crash_predictor._crash_predictor = None
    
    start = time.perf_counter()
    predictor = get_crash_predictor()
    end = time.perf_counter()
    
    loading_time = (end - start) * 1000
    
    return {
        "loading_time_ms": loading_time,
        "model_loaded": predictor.is_loaded(),
    }


def test_concurrent_predictions(predictor, snapshots: List[dict]) -> dict:
    """Test if predictions can handle rapid-fire requests."""
    
    print("\n🚀 Testing rapid-fire predictions (simulated trading load)...")
    
    start = time.perf_counter()
    
    predictions = []
    for snapshot in snapshots[:100]:  # 100 rapid predictions
        prob = predictor.predict_crash_probability(snapshot)
        predictions.append(prob)
    
    end = time.perf_counter()
    
    total_time_ms = (end - start) * 1000
    throughput = len(predictions) / (total_time_ms / 1000)  # predictions/second
    
    return {
        "predictions": len(predictions),
        "total_time_ms": total_time_ms,
        "avg_time_per_prediction_ms": total_time_ms / len(predictions),
        "throughput_per_second": throughput,
    }


def main():
    load_dotenv()
    
    print("="*80)
    print("ML CRASH PREDICTOR PERFORMANCE BENCHMARK")
    print("="*80)
    
    # Load model
    loading_stats = benchmark_model_loading()
    
    print(f"✅ Model loaded: {loading_stats['model_loaded']}")
    print(f"⏱️  Loading time: {loading_stats['loading_time_ms']:.2f}ms (one-time startup cost)")
    
    predictor = get_crash_predictor()
    
    if not predictor.is_loaded():
        print("\n❌ Model not loaded. Train first:")
        print("   python -m core.ml.crash_predictor_trainer --train")
        return
    
    # Generate test data
    print("\n📊 Generating test snapshots...")
    test_snapshots = generate_test_snapshots(1000)
    print(f"✅ Generated {len(test_snapshots)} test snapshots")
    
    # Benchmark single predictions
    print("\n" + "="*80)
    print("SINGLE PREDICTION PERFORMANCE")
    print("="*80)
    
    stats = benchmark_batch_predictions(predictor, test_snapshots)
    
    print(f"\n📊 Statistics ({stats['count']} predictions):")
    print(f"   Mean:     {stats['mean']:.3f}ms")
    print(f"   Median:   {stats['median']:.3f}ms")
    print(f"   Min:      {stats['min']:.3f}ms")
    print(f"   Max:      {stats['max']:.3f}ms")
    print(f"   Std Dev:  {stats['stdev']:.3f}ms")
    print(f"   95th %:   {stats['p95']:.3f}ms")
    print(f"   99th %:   {stats['p99']:.3f}ms")
    
    # Performance evaluation
    print("\n🎯 Performance Evaluation:")
    
    if stats['p95'] < 5.0:
        print("   ✅ EXCELLENT: 95% of predictions < 5ms")
    elif stats['p95'] < 10.0:
        print("   ✅ GOOD: 95% of predictions < 10ms")
    elif stats['p95'] < 20.0:
        print("   ⚠️  ACCEPTABLE: 95% of predictions < 20ms")
    else:
        print("   ❌ SLOW: 95% of predictions >= 20ms (optimization needed)")
    
    # Throughput test
    print("\n" + "="*80)
    print("THROUGHPUT TEST (Concurrent Load)")
    print("="*80)
    
    throughput_stats = test_concurrent_predictions(predictor, test_snapshots)
    
    print(f"\n📊 Rapid-fire test results:")
    print(f"   Predictions:      {throughput_stats['predictions']}")
    print(f"   Total time:       {throughput_stats['total_time_ms']:.2f}ms")
    print(f"   Avg per pred:     {throughput_stats['avg_time_per_prediction_ms']:.3f}ms")
    print(f"   Throughput:       {throughput_stats['throughput_per_second']:.0f} predictions/second")
    
    print("\n🎯 Throughput Evaluation:")
    
    if throughput_stats['throughput_per_second'] > 500:
        print("   ✅ EXCELLENT: Can handle 500+ signals/second")
    elif throughput_stats['throughput_per_second'] > 200:
        print("   ✅ GOOD: Can handle 200+ signals/second")
    elif throughput_stats['throughput_per_second'] > 100:
        print("   ✅ ACCEPTABLE: Can handle 100+ signals/second")
    else:
        print("   ⚠️  WARNING: Throughput < 100 predictions/second")
    
    # Real-world comparison
    print("\n" + "="*80)
    print("REAL-WORLD IMPACT ANALYSIS")
    print("="*80)
    
    avg_pred_time = stats['mean']
    
    print(f"\n⏱️  Average prediction time: {avg_pred_time:.3f}ms")
    print(f"\n📈 Impact on trading:")
    print(f"   Per signal check:         +{avg_pred_time:.2f}ms delay")
    print(f"   Per position exit check:  +{avg_pred_time:.2f}ms delay")
    
    # Typical trading latency budget
    print(f"\n🎯 Latency budget analysis:")
    print(f"   Network latency (API):    ~50-200ms")
    print(f"   Order execution:          ~10-50ms")
    print(f"   ML prediction:            ~{avg_pred_time:.2f}ms")
    print(f"   Total added latency:      {avg_pred_time / (50 + avg_pred_time) * 100:.1f}% of API call")
    
    if avg_pred_time < 10:
        print(f"\n   ✅ ML overhead is NEGLIGIBLE compared to network/execution latency")
    elif avg_pred_time < 50:
        print(f"\n   ✅ ML overhead is ACCEPTABLE (< execution latency)")
    else:
        print(f"\n   ⚠️  ML overhead is NOTICEABLE (optimization recommended)")
    
    # Final verdict
    print("\n" + "="*80)
    print("FINAL VERDICT")
    print("="*80)
    
    if stats['p95'] < 10 and throughput_stats['throughput_per_second'] > 100:
        print("\n✅ PERFORMANCE: EXCELLENT")
        print("   The ML model is fast enough for high-frequency trading.")
        print("   No optimization needed.")
    elif stats['p95'] < 20:
        print("\n✅ PERFORMANCE: GOOD")
        print("   The ML model is suitable for live trading.")
        print("   Minor optimizations could further improve speed.")
    else:
        print("\n⚠️  PERFORMANCE: NEEDS OPTIMIZATION")
        print("   Consider:")
        print("   - Reducing number of trees (200 → 100)")
        print("   - Using simpler model (Gradient Boosting)")
        print("   - Caching recent predictions")
    
    print("\n" + "="*80)


if __name__ == "__main__":
    main()
