# trading-lab

A YAML-driven paper-trading and signal research framework for stocks + crypto. Designed to run locally with SQLite, Flask UI, safe expression engine, and strict execution safety gates.

## 🎯 What This Framework Does (Plain English)

### The Big Picture
This is an **automated trading assistant** that:
1. **Watches** cryptocurrency/stock prices every 5 minutes
2. **Analyzes** them using 27+ technical indicators (RSI, MACD, etc.)
3. **Detects patterns** like "price is oversold" or "trend reversal forming"
4. **Decides** whether to buy/sell based on your strategies
5. **Executes** paper trades on Alpaca (fake money for learning)
6. **Logs** everything for you to review

### Key Concepts Explained

| Term | What It Means | Example |
|------|--------------|---------|
| **Indicator** | A math formula that measures one thing | RSI measures if price is "too high" or "too low" |
| **Pattern** | Multiple indicators combined into a setup | "Bart Simpson" = spike up → flat top → spike down |
| **Signal** | When a pattern fires with live data | "RSI_OVERSOLD detected for BTC at $77,500" |
| **Strategy** | Rules for what to do when signal fires | "Buy $15 of BTC, sell if +2.5% or -1%" |
| **Bot** | A configuration that runs patterns + strategies | "crypto_24_7" watches BTC, ETH, SOL all day |

### How Signals Combine (Composite Engine)

Our **Multi-Indicator Composite** combines 9 categories:

| Category | Weight | What It Tells You |
|----------|--------|-------------------|
| RSI | 15% | Is price oversold (buy) or overbought (sell)? |
| MACD | 15% | Is momentum shifting up or down? |
| Trend EMAs | 15% | Which direction is the trend going? |
| Bollinger Bands | 10% | Is price at extreme levels? |
| Stochastic | 10% | Another oversold/overbought measure |
| ADX | 10% | How strong is the current trend? |
| Volume | 10% | Are people actually trading? |
| Support/Resistance | 10% | Is price near key levels? |
| Candlestick | 5% | What does the price action look like? |

**Output:** Score from -100 (strong sell) to +100 (strong buy)

### Are These Professional-Grade?

**Partially.** The indicators are industry-standard (used everywhere). But:

| What We Have | What Wall Street Has |
|--------------|---------------------|
| Same indicators ✅ | Same indicators |
| Simple rules | AI trained on millions of trades |
| Static weights | Adaptive weights |
| 5-min data | Microsecond data |
| No order flow | Dark pool, order book data |

This is a **learning platform**, not a money-making machine.

---

## Requirements

- Python 3.11+
- SQLite (bundled with Python)

## Quick start

```bash
cd trading-lab
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 scripts/migrate_db.py
python3 scripts/run_bot.py --config configs/bots/stocks_intraday.yaml --once
python3 -m app.web.app
```

Open: `http://localhost:5050/trading-lab/overview`

## What runs where

- Scheduler: `python3 scripts/run_all.py --configs configs/bots/*.yaml`
- Single bot: `python3 scripts/run_bot.py --config configs/bots/stocks_intraday.yaml`
- Web UI: `python3 -m app.web.app`
- Artifacts:
  - Charts: `data/artifacts/charts/{date}/{bot_id}/{symbol}_{ts}.png`
  - Content queue: `data/artifacts/queue/{date}/{bot_id}/{symbol}_{ts}.json`
  - JSONL logs: `data/artifacts/reports/trading-lab.jsonl`

## 📊 Current Configuration

### Registered Patterns (8)
| Pattern | Description |
|---------|-------------|
| `ema_crossover` | Fast EMA crosses above slow EMA |
| `rsi_oversold` | RSI drops below 30 then recovers |
| `vwap_bounce` | Price bounces off VWAP support |
| `support_bounce` | Price bounces off calculated support |
| `volatility_squeeze` | Bollinger bands tighten before breakout |
| `mean_reversion_extreme` | Price at statistical extremes |
| `bart_simpson` | Spike up → flat top → spike down pattern |
| `composite_momentum` | Multi-indicator combined score > threshold |

### Registered Strategies (4)
| Strategy | Position Size | Stop Loss | Take Profit |
|----------|--------------|-----------|-------------|
| `rsi_reversal` | $15 | 0.8% | 1.5% |
| `composite_momentum_long` | $15 | 1.0% | 2.5% |
| `squeeze_breakout` | $15 | 1.0% | 2.0% |
| `mr_fade` | $15 | 0.5% | 1.0% |

### Risk Limits
- Max trades per day: 20
- Max daily loss: $50
- Max position size: $300
- Shorting: Disabled

### Active Bot
- **crypto_24_7**: Runs 24/7 on BTC/USD, ETH/USD, SOL/USD
- Interval: Every 5 minutes
- Mode: Paper trading (fake money)

## Safety gates

- Execution modes: `off`, `paper`, `live`.
- Live is gated by `configs/risk/defaults.yaml` and `TRADING_LAB_ARMED=1` when `arm_required: true`.
- Daily limits are enforced: max trades, max loss, max position size, allow_short.
- Kill switch triggers after repeated API errors.

## YAML-driven config

- Bots: `configs/bots/*.yaml`
- Patterns: `configs/patterns/*.yaml`
- Strategies: `configs/strategies/*.yaml`
- Risk defaults: `configs/risk/defaults.yaml`

Patterns support:
- `implementation: primitives` (safe expression engine)
- `implementation: plugin` (e.g., `bart_simpson` detector)

## Systemd services (no Docker)

```bash
chmod +x services/install_services.sh
./services/install_services.sh
```

Edit these unit files before enabling if needed:
- `services/trading-lab-web.service`
- `services/trading-lab-scheduler.service`

## Alpaca MCP server (optional, separate service)

Trading-lab does **not** depend on MCP. If you want Alpaca MCP for IDE workflows:

```bash
chmod +x services/setup_alpaca_mcp.sh
./services/setup_alpaca_mcp.sh
```

This uses the official Alpaca MCP server install flow (`uvx alpaca-mcp-server init`). Update `~/services/alpaca-mcp-server/.env` with your keys, then edit and enable:

- `services/alpaca-mcp.service`

### VS Code / Cursor MCP client config

Add a server entry (based on the official config):

```json
{
  "mcpServers": {
    "alpaca-mcp-server": {
      "command": "uvx",
      "args": ["alpaca-mcp-server", "serve"],
      "env": {
        "ALPACA_API_KEY": "YOUR_KEY",
        "ALPACA_SECRET_KEY": "YOUR_SECRET"
      }
    }
  }
}
```

If you use the systemd service instead, keep the same keys in `~/services/alpaca-mcp-server/.env` and ensure the service is running.

## Smoke test (paper only)

```bash
TRADING_LAB_SMOKE_TEST=1 python3 scripts/smoke_test_paper.py --config configs/bots/stocks_intraday.yaml
```

Places **exactly one** paper trade only when `TRADING_LAB_SMOKE_TEST=1` and bot execution mode is `paper`.
