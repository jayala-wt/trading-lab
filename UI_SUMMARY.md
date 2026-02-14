# Trading Lab UI Summary

**Generated:** 2026-02-02  
**URL:** `http://localhost:8088/trading-lab/`  
**Framework:** Flask + Jinja2 Templates  
**Styling:** Custom CSS (dark theme, CSS variables)

---

## 🧭 Navigation Tabs

| Tab | Route | Description |
|-----|-------|-------------|
| **Dashboard** | `/trading-lab/` | Main overview with account, charts, bots, signals |
| **Signals** | `/trading-lab/signals` | Pattern detection events with pagination |
| **Trades** | `/trading-lab/trades` | Executed orders from Alpaca |
| **Patterns** | `/trading-lab/patterns` | Registered pattern definitions |
| **Strategies** | `/trading-lab/strategies` | Registered strategy configurations |
| **Content Queue** | `/trading-lab/content-queue` | Social media content artifacts |
| **Devlog** | `/trading-lab/devlog` | System debug/info events |

---

## 📊 Dashboard (`/trading-lab/dashboard`)

### Sections

#### 1. Account Bar (Top Stats)
Live data from Alpaca API:
- **Cash** - Available buying power
- **Portfolio Value** - Total account value
- **Today's P&L** - Daily profit/loss with color coding
- **Buying Power** - Available for trades

#### 2. Price Charts Grid
Real-time charts using Lightweight Charts library:
- **BTC/USD** - Bitcoin price chart
- **ETH/USD** - Ethereum price chart
- **SPY** - S&P 500 ETF (during market hours)
- Each chart shows: current price, % change, candlesticks

#### 3. Positions Table
Current holdings from Alpaca:
- Symbol, Qty, Avg Entry, Current Price, P&L, Market Value
- "Close All" button for emergency liquidation

#### 4. Bot Status Cards
For each registered bot:
- Bot name and mode (paper/live/off)
- Status indicator (running/stopped)
- Last heartbeat timestamp
- Symbols being traded
- Start/Stop buttons

#### 5. Recent Signals Table
Last 10 pattern detections:
- Timestamp, Symbol, Pattern, State, Score
- Color-coded by recency

#### 6. Devlog Events
System activity log:
- Bot starts/stops
- Pattern fires
- Trade executions
- Errors and warnings

---

## 📡 Signals Page (`/trading-lab/signals`)

### Features
- **Pagination** - 50 signals per page
- **Full history** - All pattern detections
- **Details** - Pattern ID, symbol, score, state, timestamp

### Columns
| Column | Description |
|--------|-------------|
| Time | ISO timestamp |
| Symbol | Trading pair (BTC/USD, etc.) |
| Pattern | Pattern ID that fired |
| State | `fired`, `confirmed`, etc. |
| Score | Confidence score (0-1) |
| Tags | JSON metadata |

---

## 💹 Trades Page (`/trading-lab/trades`)

### Features
- **Last 100 trades** from database
- **Alpaca sync** - Real order data

### Columns
| Column | Description |
|--------|-------------|
| Open Time | When trade was opened |
| Symbol | Trading pair |
| Side | BUY or SELL |
| Qty | Position size |
| Entry Price | Fill price |
| Status | open, closed, partial |
| P&L | Realized profit/loss (if closed) |

---

## 🎯 Patterns Page (`/trading-lab/patterns`)

### Features
- **Card layout** - Visual pattern cards
- **15 patterns** registered (7 dimension + 7 YAML + 1 plugin)

### Card Contents
- Pattern name
- Pattern ID (monospace)
- Description
- Implementation type badge (primitives/dimension/plugin)

---

## 📈 Strategies Page (`/trading-lab/strategies`)

### Features
- **Card layout** - Visual strategy cards
- **5 strategies** registered

### Card Contents
- Strategy name
- Strategy ID
- Description
- Mode (BUY only / Signal-based)

---

## 🤖 Bots Page (`/trading-lab/bots`)

### Features
- **Detailed bot management**
- **Status monitoring**
- **Configuration preview**

### Card Contents
- Bot ID and name
- Market (crypto/stocks)
- Timeframe (1m/5m/15m)
- Enabled status
- Execution mode (paper/live)
- Last run timestamp
- Action buttons

---

## 📋 Content Queue (`/trading-lab/content-queue`)

### Features
- **Social media artifacts** - Auto-generated content
- **Chart images** - Signal visualizations
- **Caption templates** - Ready-to-post text

### When Populated
- When patterns fire with `content.enabled: true`
- Stored in `/trading-lab/data/artifacts/queue/`

---

## 📜 Devlog Page (`/trading-lab/devlog`)

### Features
- **System event history**
- **Filterable by level** (INFO, WARN, ERROR)
- **JSON details** expandable

### Event Types
| Type | Description |
|------|-------------|
| `bot_start` | Bot scheduler started |
| `bot_error` | Bot encountered error |
| `signal_fired` | Pattern detected |
| `trade_submitted` | Order sent to Alpaca |
| `outcome_tracked` | ML outcome computed |

---

## 📊 Interactive Chart Page (`/trading-lab/chart/<symbol>`)

### Features
- **Full-screen chart** for any symbol
- **Lightweight Charts** candlestick visualization
- **Real-time price** updates
- **Technical indicators** overlay (planned)

### URL Examples
- `/trading-lab/chart/BTC/USD`
- `/trading-lab/chart/ETH/USD`
- `/trading-lab/chart/SPY`

---

## 🔌 API Endpoints

### Account & Positions
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/account` | GET | Alpaca account info |
| `/api/positions` | GET | Current holdings |
| `/api/positions/close-all` | POST | Liquidate all positions |

### Market Data
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/quote/<symbol>` | GET | Latest quote |
| `/api/bars/<symbol>` | GET | OHLCV candlesticks |

### Signals & Analysis
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/signals/recent` | GET | Last 20 signals |
| `/api/composite/<symbol>` | GET | Live composite signal |
| `/api/live-analysis/<symbol>` | GET | Full dimension analysis |
| `/api/run-analysis` | POST | Trigger manual analysis |

### Bot Control
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/bot/start/<bot_id>` | GET | Start a bot manually |

---

## 🎨 UI Design System

### Colors (CSS Variables)
```css
--bg: #0a0f1a;        /* Dark background */
--card: #111827;      /* Card background */
--border: #1f2937;    /* Subtle borders */
--text: #f3f4f6;      /* Primary text */
--dim: #9ca3af;       /* Secondary text */
--green: #10b981;     /* Positive/success */
--red: #ef4444;       /* Negative/danger */
--accent: #06b6d4;    /* Highlight/links */
```

### Components
- **Stat Cards** - Numeric metrics with labels
- **Chart Cards** - Price charts with headers
- **Bot Cards** - Status with action buttons
- **Table Cards** - Data tables with headers
- **Badges** - Status indicators (paper/live/off)
- **Buttons** - Primary (green) and secondary (gray)

### Layout
- **Max width:** 1600px centered
- **Grid system:** CSS Grid with auto-fit
- **Responsive:** Cards wrap on smaller screens
- **Font:** System fonts (-apple-system, etc.)

---

## 📁 Template Files

```
homelab_portal/trading_lab/templates/trading_lab/
├── dashboard.html      # Main dashboard (35KB)
├── signals.html        # Signal history
├── trades.html         # Trade history
├── patterns.html       # Pattern registry
├── strategies.html     # Strategy registry
├── bots.html           # Bot management
├── content_queue.html  # Content artifacts
├── devlog.html         # System events
└── chart.html          # Full chart page
```

---

## 🔗 External Dependencies

| Library | Version | Purpose |
|---------|---------|---------|
| Lightweight Charts | 4.1.0 | Candlestick charts |
| (No other JS deps) | - | Vanilla JavaScript |

---

## 🚀 Quick Access

- **Dashboard:** http://localhost:8088/trading-lab/
- **Patterns:** http://localhost:8088/trading-lab/patterns
- **Strategies:** http://localhost:8088/trading-lab/strategies
- **Signals:** http://localhost:8088/trading-lab/signals
- **BTC Chart:** http://localhost:8088/trading-lab/chart/BTC/USD
