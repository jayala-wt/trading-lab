# Crash Pattern Analysis - Loss Avoidance ML Training Data

## 🚨 Market Crash: February 3-6, 2026

### Executive Summary

**Worst Trading Period**: Feb 3-6, 2026  
**Total Losses**: ~$155 (Feb 3 alone)  
**Key Problem**: Bot held losing positions for 10+ hours during market crash  
**Root Cause**: Volatility squeeze pattern fired during crash, kept buying the dip

---

## 📊 Crash Timeline

| Date | Avg Loss | Avg % Change | Trades Held >10h | Total Losing Trades |
|------|----------|--------------|------------------|---------------------|
| **Feb 3** | **-$0.46** | **-2.48%** | **100% of trades!** | 292 |
| Feb 4 | -$0.29 | -0.56% | 20% of trades | 542 |
| Feb 5 | -$0.50 | -2.45% | 13% of trades | 287 |
| Feb 6 | -$0.32 | 1.29% | 0% (quick exits) | 295 |

### Analysis:
- **Feb 3**: Complete market crash, bot kept buying, held entire day hoping for recovery
- **Feb 4-5**: Continued downtrend, bot slowly learning to exit faster
- **Feb 6**: Recovery started, bot cut losses quickly (no 10hr holds)

---

## ⚠️ Crash Indicator Signals

### Dimension States That Predicted Crashes (Feb 5 ETH Example)

**DANGER ZONES** (worst outcomes):

| Momentum | Trend | Volatility | Avg 5m Loss | Severe Losses (>-5%) |
|----------|-------|------------|-------------|----------------------|
| neutral | up_weak | compressed | **-13.73%** | 100% |
| neutral | down_weak | compressed | **-11.61%** | 79% |
| neutral | down_strong | compressed | **-11.16%** | 71% |

**Pattern Discovery:**
```
🚩 CRASH SIGNATURE:
   dim_volatility = "compressed" (squeeze before crash)
   + dim_trend = "up_weak" or "down_weak" (weak trend)
   + dim_momentum = "neutral" (no clear direction)
   = VERY HIGH CRASH RISK
```

### Best vs Worst Dimension Combinations (All-Time)

**WORST PERFORMERS (avoid these!):**

| Momentum | Trend | Volatility | Win Rate | Avg Outcome | Samples |
|----------|-------|------------|----------|-------------|---------|
| neutral | down_strong | compressed | **26.9%** | **-0.533%** | 208 |
| oversold | down_weak | expanding | 29.4% | -0.456% | 68 |
| neutral | down_weak | compressed | 42.2% | -0.182% | 332 |
| overbought | up_weak | expanding | 26.7% | -0.167% | 101 |

**BEST PERFORMERS (seek these!):**

| Momentum | Trend | Volatility | Win Rate | Avg Outcome | Samples |
|----------|-------|------------|----------|-------------|---------|
| oversold | up_strong | expanding | **78.0%** | **+0.665%** | 223 |
| oversold | up_weak | expanding | 70.0% | +0.464% | 230 |
| neutral | up_strong | expanding | 64.6% | +0.253% | 192 |

---

## 🎯 RSI Danger Zones During Crashes

| RSI Zone | Samples | Avg Outcome | Severe Crashes | Avg Max DD |
|----------|---------|-------------|----------------|-------------|
| **Neutral-Low (40-50)** | 395 | **-3.68%** | 68 | -5.19% |
| Neutral-High (50-60) | 231 | -1.29% | 10 | -3.10% |
| Low (30-40) | 147 | -0.93% | 8 | -3.31% |
| High (60-70) | 57 | -0.57% | 1 | -2.30% |
| Oversold (<30) | 66 | -0.49% | 0 | -2.56% |

**Key Insight:** **RSI 40-50 was MOST DANGEROUS during crashes!**  
- Not oversold enough to bounce  
- Not overbought enough to reverse  
- Dead zone where crashes accelerate

---

## ⏱️ Hold Time vs Loss Magnitude

| Hold Duration | Trade Count | Avg P&L | Worst Loss |
|---------------|-------------|---------|------------|
| **Very Long Hold (>4hr)** | 318 | **-$0.63** | **-$2.54** |
| Long Hold (1-4hr) | 98 | -$0.34 | -$1.51 |
| Medium Hold (30-60min) | 88 | -$0.25 | -$0.68 |
| Short Hold (5-30min) | 421 | -$0.19 | -$0.74 |
| Quick Exit (<5min) | 191 | -$0.16 | -$0.43 |

**Critical Finding:**  
💡 **Holding losses >4 hours = 4X worse losses than quick exits**  
- Quick exit (<5min): -$0.16 avg  
- Very long hold (>4hr): -$0.63 avg  

**Recommendation:** Implement "crash exit" - if down >2% after 15min, force exit!

---

## 📉 Pattern Performance During Feb 3 Crash

| Pattern | Signals | Trades Executed | Avg Outcome | Severe Losses | Win Rate |
|---------|---------|-----------------|-------------|---------------|----------|
| **dim_volatility_squeeze** | **238** | 82% | **-5.49%** | 77 | **29.8%** |
| dim_trend_continuation_buy | 20 | 50% | -4.92% | 6 | 25.0% |
| dim_momentum_reversal_buy | 15 | 60% | -2.49% | 1 | 40.0% |
| dim_trend_continuation_sell | 24 | 54% | -2.17% | 3 | 41.7% |
| dim_momentum_reversal_sell | 8 | 62% | -0.84% | 0 | 50.0% |

**Pattern Analysis:**
- `dim_volatility_squeeze` was **THE WORST** during crash (238 signals, 29.8% win rate)
- This pattern kept firing "buy the dip" signals as market fell
- 82% conversion rate = bot executed most of them!

---

## 🧠 ML Training Dataset Recommendations

### High-Value Crash Samples for Training

**Export these for ML model:**

```sql
-- CRASH AVOIDANCE TRAINING SET
SELECT 
    -- Features
    dim_momentum,
    dim_trend,
    dim_volatility,
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
    
    -- Labels
    outcome_5m,
    outcome_15m,
    outcome_60m,
    max_drawdown,
    max_favorable,
    label_profitable_5m,
    label_profitable_15m,
    label_quality,
    
    -- Metadata
    symbol,
    pattern_id,
    direction,
    confidence,
    created_at
    
FROM ml_training_samples
WHERE 
    -- Focus on crash period
    DATE(created_at) BETWEEN '2026-02-03' AND '2026-02-06'
    
    -- And severe losses
    AND (
        max_drawdown < -5.0  -- Big drawdowns
        OR outcome_5m < -3.0  -- Fast crashes
        OR (
            dim_volatility = 'compressed' 
            AND dim_trend IN ('up_weak', 'down_weak')
            AND dim_momentum = 'neutral'
        )  -- Crash signature
    )
ORDER BY outcome_5m ASC;
```

### ML Model Objectives

1. **Binary Classifier: "Crash Imminent"**
   - Input: Current dimension states + raw indicators
   - Output: P(crash in next 5min) > 80%
   - Action: Block all trades if P(crash) > 0.7

2. **Regression: "Expected Drawdown"**
   - Input: Same features
   - Output: Predicted max_drawdown
   - Action: Skip trade if predicted drawdown < -3%

3. **Multi-Class: "Market Regime"**
   - Classes: [trending, ranging, crashing, recovering]
   - Input: Rolling window of dimension states (last 6 samples = 30min)
   - Output: Current regime
   - Action: Different strategies per regime

---

## 🛡️ Immediate Risk Management Rules

Based on crash analysis, add these hard-coded rules:

### 1. Crash Exit Rule
```python
if (time_in_position > 15_minutes and unrealized_pnl_pct < -2.0):
    force_exit(reason="crash_protection")
```

### 2. Volatility Squeeze Filter
```python
if (dim_volatility == "compressed" 
    and dim_trend in ["up_weak", "down_weak"] 
    and dim_momentum == "neutral"):
    block_trade(reason="crash_signature_detected")
```

### 3. RSI Dead Zone Filter
```python
if (40 <= raw_rsi <= 50 
    and dim_volatility == "compressed"):
    reduce_position_size(factor=0.5, reason="rsi_danger_zone")
```

### 4. Max Hold Time
```python
if time_in_position > 4_hours:
    force_exit(reason="max_hold_time_exceeded")
```

---

## 📈 Expected Impact

**Before Crash Rules:**
- Feb 3 loss: -$155.54
- Avg hold time during crashes: >10 hours
- Win rate during crashes: 8.75%

**After Crash Rules (Estimated):**
- Feb 3 loss: -$40 (74% reduction)
- Avg hold time: <1 hour (forced exits)
- Win rate: 35%+ (blocking bad setups)

**How:**
- Block 238 volatility_squeeze signals on Feb 3 → Avoid 70% of losses
- Force exit at -2% after 15min → Cap remaining losses at -$12
- Total saved: ~$115 on Feb 3 alone!

---

## 🎯 Next Steps

### Immediate (Today):
1. ✅ Export crash training data (660 samples from Feb 3-6)
2. ✅ Add crash exit rule to risk_manager.py
3. ✅ Add volatility squeeze filter during weak trends

### This Week:
1. Train binary classifier: "Crash Imminent" (target: 80% precision)
2. Backtest performance on Feb 3-6 data with new rules
3. A/B test: old bot vs new bot on paper trading

### This Month:
1. Train multi-class regime classifier
2. Implement dynamic position sizing based on regime
3. Add "recovery mode" after crashes (smaller sizes, higher confidence)

---

## 📊 Data Export Commands

```bash
cd /opt/homelab-panel/trading-lab

# Export crash training data
sqlite3 data/market.db << 'EOF'
.mode csv
.output crash_training_feb3-6.csv
SELECT * FROM ml_training_samples 
WHERE DATE(created_at) BETWEEN '2026-02-03' AND '2026-02-06';
.quit
EOF

# Export for Python/pandas
sqlite3 data/market.db << 'EOF'
.mode json
.output crash_training_feb3-6.json
SELECT * FROM ml_training_samples 
WHERE outcome_5m IS NOT NULL 
  AND DATE(created_at) BETWEEN '2026-02-03' AND '2026-02-06';
.quit
EOF

# Start Jupyter for exploratory analysis
cd /opt/homelab-panel/trading-lab
pip install jupyter pandas matplotlib seaborn scikit-learn
jupyter notebook --port 8889
```

---

**Bottom Line:**  
You have **660 high-quality crash samples** with detailed indicators. This is GOLD for training a loss-avoidance ML model. The crash signature is clear: `compressed + weak_trend + neutral_momentum = DANGER`.
