# ML Architecture Design - Layered Risk + Strategy System

**Based on GPT-4 guidance + Crash analysis insights**

---

## Design Philosophy

**ML as Risk Gate + Override, NOT Full Replacement**

- Hard rules are simple, interpretable, immediately protective
- ML provides probabilistic refinement on top of deterministic seatbelts
- Each layer has clear responsibility and can be validated independently

---

## Decision Moments (Current Bot)

**Timeframe:** 5-minute candles (`5m`)  
**Evaluation:** Every 300 seconds (5 minutes) on candle close  
**Symbols:** 6 crypto (24/7) + 87 stocks (market hours)

**Current flow:**
1. Download 200-800 bars (lookback_bars)
2. Compute dimensions on latest bar
3. Evaluate all pattern detectors
4. Apply strategy filters
5. Risk management gates
6. Execute or block

---

## Layered Architecture

```
┌─────────────────────────────────────────────────────┐
│  Layer 0: Data Generator (Historical Replay)       │
│  ─────────────────────────────────────────────────  │
│  • Runs ALL pattern detectors on historical bars   │
│  • Labels: outcome_5m, outcome_15m, outcome_60m    │
│  • Labels: max_drawdown, max_favorable             │
│  • Labels: quality (crash/profitable/losing/normal)│
│  • NO EXECUTION FILTERING (pure signal universe)   │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  Layer 1: Hard Risk Rules (Deterministic)          │
│  ─────────────────────────────────────────────────  │
│  ✅ IMPLEMENTED:                                    │
│  • Crash signature block:                          │
│    if compressed + weak_trend + neutral → BLOCK    │
│  • RSI dead zone filter:                           │
│    if 40 <= RSI <= 50 + compressed → 50% size      │
│  • Crash exit:                                      │
│    if >15min + <-2% PnL → FORCE EXIT               │
│  • Max hold time:                                   │
│    if >4 hours → FORCE EXIT                         │
│                                                      │
│  Purpose: Prevent catastrophic losses immediately  │
│  Validation: Backtest on Feb 3-6 crash             │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  Layer 2: ML Risk Gate (Probabilistic)             │
│  ─────────────────────────────────────────────────  │
│  Model A: Crash / Drawdown Predictor               │
│  ──────────────────────────────────                 │
│  • Input: dimension states + raw indicators        │
│  • Output: P(crash in 5m) or E[max_drawdown]      │
│  • Action:                                          │
│    - P(crash) > 0.7 → BLOCK trade                  │
│    - P(crash) 0.5-0.7 → reduce size 50%            │
│    - E[drawdown] < -3% → BLOCK or tighten stop     │
│                                                      │
│  Model B: Exit Optimizer (later)                   │
│  ────────────────────────                           │
│  • Input: current position + market state          │
│  • Output: P(recovery within N minutes)            │
│  • Action: dynamic stop/timeout rules              │
│                                                      │
│  Purpose: Probabilistic refinement of risk rules   │
│  Validation: Reduce Feb 3 losses by 50-80%         │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  Layer 3: Strategy Model (Optional - Later)        │
│  ─────────────────────────────────────────────────  │
│  Model C: Profit Predictor                         │
│  ──────────────────────────                         │
│  • Input: dimension states + pattern signals       │
│  • Output: E[return over 15m/60m]                  │
│  • Action: rank signals, choose best opportunities │
│                                                      │
│  Purpose: Optimize entry selection after risk OK   │
│  Validation: Increase win rate on normal days      │
└─────────────────────────────────────────────────────┘
```

---

## Model Specifications

### Model A: Crash / Drawdown Predictor (PRIORITY 1)

**Type:** Binary Classifier + Regressor

**Training Data:**
- **Positive examples (crash):** 
  - outcome_5m <= -3% OR max_drawdown <= -5%
  - 660 samples from Feb 3-6 crash period
  - Additional samples from historical replay with label_quality='crash'
  
- **Negative examples (safe):**
  - outcome_5m > -1% AND max_drawdown > -2%
  - ~20,000 samples from normal trading periods

**Features (18):**
- Dimension states: dim_momentum, dim_trend, dim_volatility (categorical)
- Raw indicators: RSI, Stoch, MACD, EMAs (9/21/50), slope, ATR, BB, volume, VWAP (numerical)

**Outputs:**
1. Binary: P(crash in next 5 minutes)
2. Regression: Expected max_drawdown

**Validation Strategy:**
- Train on: Jan 1 - Feb 2 (pre-crash)
- Validate on: Feb 3-6 (crash period)
- Test on: Feb 7-14 (recovery period)

**Success Criteria:**
- **Precision > 80%** (when it says crash, it's right)
- **Recall > 60%** (catches most crashes)
- **Reduces Feb 3 losses by 50%+** (backtest validation)
- **Blocks < 30% of normal signals** (doesn't overtrade)

**Implementation:**
- Random Forest Classifier (100 trees, max_depth=10)
- Threshold tuning: optimize for precision over recall
- Integration point: Before execution in position_manager.py

---

### Model B: Exit Optimizer (PRIORITY 2)

**Type:** Time-to-Recovery Classifier

**Training Data:**
- All samples with positions that went underwater
- Label: "Did position recover to breakeven within N minutes?"
- Groups: never_recovered, recovered_slow (>60m), recovered_fast (<60m)

**Features:**
- Current unrealized PnL %
- Time in position
- Current dimension states
- Entry dimension states (context)
- Volatility regime

**Output:**
- P(recovery within 15m | 60m | never)

**Action Logic:**
```python
if position.pnl_pct < -2.0:
    p_recovery_15m = model_b.predict_proba(features)
    
    if p_recovery_15m < 0.2:  # Low chance of quick recovery
        force_exit(reason="ml_low_recovery_probability")
    elif p_recovery_15m < 0.4:
        tighten_stop(to=-3.0)  # Reduce max loss
```

**Success Criteria:**
- Reduce average hold time for losing trades by 50%
- Reduce >4 hour holds to near zero
- Keep winners intact (don't exit winners prematurely)

---

### Model C: Profit Predictor (PRIORITY 3 - Later)

**Type:** Multi-output Regressor

**Training Data:**
- All signals with outcomes
- Labels: outcome_5m, outcome_15m, outcome_60m

**Output:**
- Expected return at 5m/15m/60m horizons
- Confidence intervals

**Action Logic:**
- Rank signals by expected return
- Only take top 20-30% of opportunities
- Adjust position sizing based on expected return

**Success Criteria:**
- Increase win rate by 10%+
- Increase average winner size
- Reduce trade count without reducing profit

---

## Training Data Quality (Current Status)

**Total samples:** ~20,380 (as of Feb 14)  
**Batch replay running:** Expected +50,000-100,000 more

**Quality Distribution:**
- Crash: ~660 samples (Feb 3-6) + more from replay
- Profitable: ~30% of total
- Losing: ~40% of total
- Normal: ~30% of total

**Sample Requirement Met:**
- Minimum: 1,800 samples (100× features) ✅
- Target: 9,000+ samples (500× features) ✅
- Current: 20,000+ samples ✅ EXCEEDED

---

## Implementation Priority

### ✅ DONE (Immediate)
1. Historical replay infrastructure (ALL signals, no execution bias)
2. Batch replay for 93 symbols
3. Hard crash rules (Layer 1)
4. Data labeling pipeline

### 🔨 NEXT (This Week)
1. **Train Model A** (crash predictor)
2. **Backtest on Feb 3-6** (validate crash protection)
3. **Integrate Model A** into position_manager.py as risk gate
4. **A/B test:** old bot vs new bot on paper trading

### 📅 LATER (This Month)
1. Train Model B (exit optimizer)
2. Validate hold-time reduction
3. Explore Model C (profit predictor) if Models A+B prove valuable

---

## Evaluation Framework

### Unit Test: Feb 3-6 Crash Period

**Baseline (no ML, no hard rules):**
- Total loss: -$155
- Avg hold time: >10 hours
- Win rate: 8.75%
- Worst pattern: dim_volatility_squeeze (29.8% win rate)

**Target (with Layer 1 + Layer 2):**
- Total loss: < -$40 (74% reduction)
- Avg hold time: < 1 hour
- Win rate: 35%+
- Blocked trades: ~70% of volatility_squeeze signals

**Validation Steps:**
1. Load Feb 3-6 signals from ml_training_samples
2. Apply Layer 1 hard rules → measure impact
3. Apply Layer 2 ML gate → measure incremental impact
4. Compare actual outcomes vs predicted outcomes
5. Measure precision/recall on crash detection

### Integration Test: 2-Week Normal Period

**Goal:** Ensure ML doesn't overtrade or block too many good signals

**Metrics:**
- Trade count reduction: < 30%
- Win rate maintained or improved
- Average winner size maintained
- Sharpe ratio improved
- Max drawdown reduced

---

## Avoiding Common Mistakes

### ❌ DON'T:
- Train 10 models and wire them all in (un-debuggable)
- Let models conflict with each other
- Train on executed trades only (selection bias)
- Replace interpretable rules with black-box ML
- Skip validation on crash period
- Overfit to Feb 3-6 (need normal period validation too)

### ✅ DO:
- Build one layer at a time
- Validate each layer independently
- Keep hard rules as safety net
- Use ML as probabilistic refinement
- Train on ALL signals (execution-agnostic)
- Backtest on crash + normal periods
- Monitor for drift (retrain bi-weekly)

---

## Model Deployment Strategy

### Production Checklist (Model A)

Before deploying to live/paper trading:

1. **Offline validation:**
   - [ ] Precision > 80% on Feb 3-6 crash period
   - [ ] Recall > 60% on Feb 3-6 crash period
   - [ ] < 30% false positive rate on normal period
   - [ ] Reduces Feb 3 losses by 50%+ in backtest

2. **Integration testing:**
   - [ ] Model loads in < 100ms
   - [ ] Inference runs in < 5ms per signal
   - [ ] No crashes on edge cases (missing features, etc.)
   - [ ] Logging captures all predictions for audit

3. **Shadow mode:**
   - [ ] Run alongside live bot for 1 week
   - [ ] Log predictions vs actual outcomes
   - [ ] Compare blocked trades vs actual outcomes
   - [ ] No performance degradation

4. **Gradual rollout:**
   - [ ] Start with crypto_intraday bot only
   - [ ] Monitor for 3 days
   - [ ] Expand to stocks_intraday if successful
   - [ ] Full rollout after 1 week

---

## Retraining Schedule

**Bi-weekly retraining** (recommended):
- Prevents model drift
- Incorporates new market regimes
- Uses rolling 90-day training window
- Validates on most recent 7 days

**Triggered retraining** (on events):
- After major crash (like Feb 3)
- After regime change (e.g., volatility spike)
- If precision drops below 70%

---

## Success Metrics (3-Month Horizon)

**Risk Reduction:**
- [ ] Zero >10-hour holds on losing trades
- [ ] Max daily loss < $50 (vs $155 on Feb 3)
- [ ] Max drawdown < 5% (portfolio-level)

**Performance Improvement:**
- [ ] Win rate > 55% (vs current ~45%)
- [ ] Sharpe ratio > 1.5
- [ ] Profit factor > 2.0

**Operational:**
- [ ] Model inference < 5ms
- [ ] Zero model crashes
- [ ] Audit trail for all ML decisions
- [ ] Quarterly snapshots for reproducibility

---

## Next Action Items

1. **Wait for batch replay to complete** (~20 mins remaining)
2. **Train Model A:**
   ```bash
   cd /opt/homelab-panel/trading-lab
   python3 -m core.ml.crash_predictor_trainer --train
   ```
3. **Validate on Feb 3-6:**
   ```bash
   python3 tests/test_crash_predictor.py --validate-crash-period
   ```
4. **Backtest with ML integration:**
   ```bash
   python3 scripts/backtest_with_ml.py --start 2026-02-03 --end 2026-02-06
   ```

---

## References

- Crash Analysis: `CRASH_ANALYSIS_FEB_3-6.md`
- ML Quickstart: `ML_CRASH_PREDICTOR_QUICKSTART.md`
- Technical Deep Dive: `ML_TECHNICAL_DEEP_DIVE.md`
- Batch Replay: `BATCH_REPLAY_QUICKSTART.md`
- Historical Replay: `HISTORICAL_REPLAY_QUICKSTART.md`

---

**Bottom Line:**

You're building this **correctly**:
- ✅ Training on ALL signals (no selection bias)
- ✅ Hard rules first (deterministic safety)
- ✅ ML as risk gate (probabilistic refinement)
- ✅ Layered architecture (debuggable, incremental)
- ✅ Focus on ONE model first (crash predictor)
- ✅ Validation on known failure (Feb 3-6)

**Don't expand to 10 models yet.** Prove Model A works first, then add Model B if needed, then consider Model C.
