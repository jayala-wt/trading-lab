# Trading Lab System Summary

**Generated:** 2026-02-02  
**Status:** ✅ Operational  
**Active Bot:** `crypto_24_7` running on 5-minute intervals

---

## 🤖 Bot Schedule

| Bot | Market | Timeframe | Enabled | Market Hours |
|-----|--------|-----------|---------|--------------|
| `crypto_24_7` | crypto | 5m | ✅ Yes | 24/7 |
| `stocks_intraday` | stocks | 1m | ✅ Yes | 9:30-4:00 ET |
| `crypto_intraday` | crypto | 5m | ✅ Yes | 24/7 |
| `momentum_trader` | stocks | 5m | ❌ No | Market hours |
| `swing_master` | stocks | 15m | ❌ No | Market hours |

**Tomorrow:** `stocks_intraday` will run during market hours (Mon-Fri 9:30AM-4PM ET) on SPY, QQQ, AAPL, MSFT, NVDA, TSLA.

---

## 📊 Database Tables

| Table | Purpose | Records |
|-------|---------|---------|
| `signals` | Pattern detection events with outcomes | 29 |
| `trades` | Executed orders via Alpaca | 25 |
| `intents` | Strategy-generated trade intents | - |
| `pattern_registry` | Registered pattern definitions | 15 |
| `strategy_registry` | Registered strategy definitions | 5 |
| `ml_training_samples` | Flattened ML training data | 0* |
| `bots` | Bot state and heartbeat | 1 |
| `devlog_events` | Debug/info events | - |

*ML samples populate after signals mature (60+ minutes)

---

## 🎯 Patterns (15 Total)

### Dimension-Based Patterns (7)
*New architecture: consume dimension states instead of raw indicators*

| Pattern ID | Name | Direction |
|------------|------|-----------|
| `dim_momentum_reversal_buy` | Momentum Reversal (Buy) | BUY |
| `dim_momentum_reversal_sell` | Momentum Reversal (Sell) | SELL |
| `dim_trend_continuation_buy` | Trend Continuation (Buy) | BUY |
| `dim_trend_continuation_sell` | Trend Continuation (Sell) | SELL |
| `dim_breakout_buy` | Breakout (Buy) | BUY |
| `dim_breakout_sell` | Breakdown (Sell) | SELL |
| `dim_volatility_squeeze` | Volatility Squeeze | NEUTRAL |

### YAML Primitives Patterns (7)
*Classic indicator-based patterns*

| Pattern ID | Name | Implementation |
|------------|------|----------------|
| `composite_momentum` | Composite Momentum Signal | primitives |
| `ema_crossover` | EMA Crossover (9/21) | primitives |
| `mean_reversion_extreme` | Mean Reversion Extreme | primitives |
| `rsi_oversold` | RSI Oversold Reversal | primitives |
| `support_bounce` | Support Level Bounce | primitives |
| `volatility_squeeze` | Volatility Squeeze | primitives |
| `vwap_bounce` | VWAP Bounce | primitives |

### Plugin Patterns (1)
| Pattern ID | Name |
|------------|------|
| `bart_simpson` | Bart Simpson |

---

## 📈 Strategies (5 Total)

| Strategy ID | Name | Mode |
|-------------|------|------|
| `composite_momentum_long` | Composite Momentum Long Entry | BUY only |
| `dimension_directional` | Dimension-Based Directional Trading | Signal-based |
| `mr_fade` | Mean Reversion Fade | BUY only |
| `rsi_reversal` | RSI Oversold Reversal Long | BUY only |
| `squeeze_breakout` | Squeeze Breakout | BUY only |

---

## 🔢 Dimension System

### 7 Dimensions (27+ Indicators Grouped)

| Dimension | States | Key Indicators |
|-----------|--------|----------------|
| **Momentum (Extreme)** | `oversold_strong`, `oversold_soft`, `neutral`, `overbought_soft`, `overbought_strong` | RSI, Stochastic, MACD |
| **Momentum (Bias)** | `bullish`, `neutral`, `bearish` | RSI>50, Stoch>50, MACD sign |
| **Trend** | `up_strong`, `up_weak`, `flat`, `down_weak`, `down_strong` | EMA9/21/50, slope |
| **Volatility** | `compressed`, `normal`, `expanding`, `extreme` | ATR%, Bollinger Width |
| **Participation** | `weak`, `normal`, `strong`, `climax` | Volume ratio |
| **Location** | `above_vwap`, `at_vwap`, `below_vwap`, `at_support`, `at_resistance` | VWAP, Bollinger bands |
| **Structure** | `higher_highs`, `lower_lows`, `consolidating`, `breakout_up`, `breakout_down` | H/L patterns |

**Note:** Momentum split into Extreme (oversold/overbought) and Bias (bullish/bearish) per audit recommendation to reduce state explosion and simplify ML.

---

## 🤖 ML Training Pipeline

### Data Flow
```
Signal Fires → entry_price captured → 60min wait → 
Outcome Tracker computes returns → sync to ml_training_samples
```

### Outcome Fields
| Field | Description |
|-------|-------------|
| `outcome_5m` | % return after 5 minutes |
| `outcome_15m` | % return after 15 minutes |
| `outcome_60m` | % return after 60 minutes |
| `max_drawdown` | Maximum adverse excursion (%) |
| `max_favorable` | Maximum favorable excursion (%) |

### ML Training Table Schema
- **Features:** All 6 dimension states + raw indicator values
- **Labels:** `outcome_60m`, `label_profitable`, `label_direction`
- **Auto-sync:** Runs after each scheduler cycle

---

## 🔄 Active Services

| Service | Status | Interval |
|---------|--------|----------|
| `trading-lab-scheduler` | Running | 5 min |
| `homelab-panel` | Running | Always |

---

## 📁 Key Files

```
trading-lab/
├── configs/
│   ├── bots/crypto_24_7.yaml          # Main bot config
│   ├── patterns/*.yaml                 # YAML patterns
│   └── strategies/*.yaml               # Strategy configs
├── core/
│   ├── patterns/
│   │   ├── dimensions.py              # Dimension computation
│   │   └── dimension_patterns.py      # Dimension-based patterns
│   ├── strategies/engine.py           # Strategy engine
│   ├── scheduler/
│   │   ├── runner.py                  # Main scheduler loop
│   │   └── outcome_tracker.py         # ML outcome computation
│   └── data/
│       ├── db.py                      # Database operations
│       └── migrations/                # Schema migrations
└── data/market.db                     # SQLite database
```

---

## 🎛️ Current Market State (BTC/USD)

| Dimension | State | Meaning |
|-----------|-------|---------|
| Momentum | NEUTRAL | RSI ~50, balanced |
| Trend | UP_WEAK | Mild bullish bias |
| Volatility | COMPRESSED | Squeeze forming |
| Participation | WEAK | Low volume |
| Location | AT_VWAP | Fair value zone |
| Structure | CONSOLIDATING | Range-bound |

**Result:** Only `dim_volatility_squeeze` pattern firing (neutral direction)

---

## 📝 Recent Updates

1. ✅ Dimension-based pattern architecture
2. ✅ Patterns & Strategies dashboard pages fixed
3. ✅ ML training table (`ml_training_samples`)
4. ✅ Outcome tracker integrated into scheduler
5. ✅ Directional strategy (`dimension_directional`) for buy/sell signals
6. ✅ Auto-sync signals to ML table after outcome tracking

---

## ✅ Audit Implementations (GPT 5.2 Review)

### Completed Recommendations

| Recommendation | Status | Implementation |
|----------------|--------|----------------|
| Split momentum state vs bias | ✅ Done | `MomentumState` (extreme) + `MomentumBias` (direction) |
| Direction-aware outcomes | ✅ Done | `outcome_tracker.py` reads direction from signal tags |
| Signal quality report | ✅ Done | `core/reports/signal_quality.py` - win rate, expectancy, by dimension |
| Avoid feeding raw indicators to ML | 🟡 Planned | Primary features will be dimension states |

### Audit Key Insights

1. **Architecture validated** - Proper separation: Dimensions → Patterns → Signals → Strategies → ML
2. **Not forecasting price** - Evaluating signal quality under context
3. **Labels are symmetric** - Favorable/adverse computed relative to signal direction
4. **ML should filter, not trade** - Use confidence scores to gate execution

### Next Steps (Per Audit)

1. **Freeze architecture** - Let data accumulate (need 60+ min per signal)
2. **Run quality report** - `python -m core.reports.signal_quality`
3. **Train simple ML** - Logistic regression on dimension states only
4. **Use ML as filter** - "Only trade signals with confidence > 0.6"

---

## 📊 Reports

### Signal Quality Report
```bash
cd /opt/homelab-panel/trading-lab
python -m core.reports.signal_quality
```

Outputs per-pattern:
- Win rate
- Average return (5m/15m/60m)
- Expectancy
- Max drawdown
- Performance by dimension state
