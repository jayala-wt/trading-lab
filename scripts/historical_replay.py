#!/usr/bin/env python3
"""
Historical Replay Engine - Parallel Training Data Generation

Download historical bars, replay dimension classifier + pattern detection,
generate synthetic training samples in parallel with live bot.

Usage:
    # Replay last 7 days for BTC/USD
    python3 scripts/historical_replay.py --symbol BTC/USD --days 7
    
    # Replay multiple symbols
    python3 scripts/historical_replay.py --symbols BTC/USD,ETH/USD --days 7
    
    # Replay specific date range
    python3 scripts/historical_replay.py --symbol BTC/USD --start 2026-02-03 --end 2026-02-06
    
    # Dry run (don't insert to DB)
    python3 scripts/historical_replay.py --symbol BTC/USD --days 7 --dry-run
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
from datetime import datetime, timedelta
import time
from typing import List, Dict, Optional, Any
import json

# Use actual trading-lab infrastructure
from core.data.providers import AlpacaConfig, AlpacaMarketDataProvider
from core.data.db import Database, log_dev_event
from core.patterns.dimensions import compute_dimensions, DimensionSnapshot
from core.patterns.dimension_patterns import evaluate_all_patterns


class HistoricalReplay:
    """Replay bot logic on historical data to generate training samples."""
    
    def __init__(self, dry_run: bool = False):
        # Get Alpaca config from environment
        api_key = os.getenv("ALPACA_API_KEY", "")
        api_secret = os.getenv("ALPACA_API_SECRET", "") or os.getenv("ALPACA_SECRET_KEY", "")
        data_url = os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets")
        
        if not api_key or not api_secret:
            raise ValueError("ALPACA_API_KEY and ALPACA_API_SECRET environment variables required!")
        
        config = AlpacaConfig(
            api_key=api_key,
            api_secret=api_secret,
            trading_base_url="https://paper-api.alpaca.markets",
            data_base_url=data_url,
            market="crypto",  # BTC/USD, ETH/USD
        )
        
        self.alpaca = AlpacaMarketDataProvider(config)
        self.db = Database()
        self.dry_run = dry_run
        
        self.stats = {
            'bars_processed': 0,
            'signals_detected': 0,
            'samples_created': 0,
            'start_time': time.time(),
        }
    
    def download_historical_bars(self, symbol: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """Download historical 1-minute bars from Alpaca."""
        print(f"📥 Downloading {symbol} bars from {start_date} to {end_date}...")
        
        bars = self.alpaca.get_bars(
            symbol=symbol,
            timeframe='1Min',
            start=start_date,
            end=end_date,
            limit=50000  # Max per request
        )
        
        if bars.empty:
            print(f"⚠️  No data returned for {symbol}")
            return pd.DataFrame()
        
        print(f"✅ Downloaded {len(bars)} bars")
        return bars
    
    def calculate_indicators(self, bars: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators on bars."""
        df = bars.copy()
        
        # Ensure we have OHLCV columns
        if 'close' not in df.columns:
            print("⚠️  No 'close' column in bars!")
            return df
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # MACD
        ema_12 = df['close'].ewm(span=12, adjust=False).mean()
        ema_26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = ema_12 - ema_26
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_histogram'] = df['macd'] - df['macd_signal']
        
        # EMAs
        df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
        df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
        
        # Bollinger Bands
        df['bb_middle'] = df['close'].rolling(window=20).mean()
        bb_std = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_middle'] + (2 * bb_std)
        df['bb_lower'] = df['bb_middle'] - (2 * bb_std)
        df['bb_bandwidth'] = ((df['bb_upper'] - df['bb_lower']) / df['bb_middle']) * 100
        df['bb_pct'] = ((df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])) * 100
        
        # ATR
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = true_range.rolling(window=14).mean()
        df['atr_pct'] = (df['atr'] / df['close']) * 100
        
        # Stochastic
        low_14 = df['low'].rolling(window=14).min()
        high_14 = df['high'].rolling(window=14).max()
        df['stoch_k'] = ((df['close'] - low_14) / (high_14 - low_14)) * 100
        df['stoch_d'] = df['stoch_k'].rolling(window=3).mean()
        
        # Slope (20-period)
        df['slope_20'] = df['close'].pct_change(periods=20) * 100
        
        # Volume metrics
        df['volume_ma_20'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma_20']
        
        # VWAP
        df['vwap'] = (df['close'] * df['volume']).cumsum() / df['volume'].cumsum()
        df['vwap_distance_pct'] = ((df['close'] - df['vwap']) / df['vwap']) * 100
        
        return df
    
    def classify_dimension_snapshot(self, bar_data: Dict) -> Dict:
        """Create dimension snapshot from bar data."""
        snapshot = {
            'timestamp': bar_data['timestamp'],
            'symbol': bar_data['symbol'],
            'close': bar_data['close'],
            'volume': bar_data['volume'],
            
            # Dimensions
            'dim_momentum': self.dimension_classifier.classify_momentum(bar_data['rsi'], bar_data['stoch_k']),
            'dim_trend': self.dimension_classifier.classify_trend(bar_data['ema_9'], bar_data['ema_21'], bar_data['ema_50'], bar_data['slope_20']),
            'dim_volatility': self.dimension_classifier.classify_volatility(bar_data['bb_bandwidth'], bar_data['atr_pct']),
            
            # Raw indicators
            'raw_rsi': bar_data['rsi'],
            'raw_stoch_k': bar_data['stoch_k'],
            'raw_macd_histogram': bar_data['macd_histogram'],
            'raw_ema_9': bar_data['ema_9'],
            'raw_ema_21': bar_data['ema_21'],
            'raw_ema_50': bar_data['ema_50'],
            'raw_slope_20': bar_data['slope_20'],
            'raw_atr_pct': bar_data['atr_pct'],
            'raw_bb_bandwidth': bar_data['bb_bandwidth'],
            'raw_bb_pct': bar_data['bb_pct'],
            'raw_volume_ratio': bar_data['volume_ratio'],
            'raw_vwap_distance_pct': bar_data['vwap_distance_pct'],
        }
        
        return snapshot
    
    def detect_patterns(self, snapshot: Dict) -> List[Dict]:
        """Run pattern detection on dimension snapshot."""
        # Convert snapshot to format pattern detector expects
        signals = self.pattern_detector.detect_all(snapshot)
        return signals
    
    def label_outcomes(self, df: pd.DataFrame, signal_idx: int, signal_time: datetime) -> Dict:
        """Label outcomes 5m, 15m, 60m after signal."""
        signal_price = df.iloc[signal_idx]['close']
        
        outcomes = {
            'entry_price': signal_price,
            'outcome_5m': None,
            'outcome_15m': None,
            'outcome_60m': None,
            'max_drawdown': None,
            'max_favorable': None,
        }
        
        # Calculate outcomes
        future_window = df.iloc[signal_idx:signal_idx+61]  # Next 60 bars
        
        if len(future_window) < 6:
            return outcomes  # Not enough future data
        
        # 5-minute outcome
        if len(future_window) >= 6:
            price_5m = future_window.iloc[5]['close']
            outcomes['outcome_5m'] = ((price_5m - signal_price) / signal_price) * 100
        
        # 15-minute outcome
        if len(future_window) >= 16:
            price_15m = future_window.iloc[15]['close']
            outcomes['outcome_15m'] = ((price_15m - signal_price) / signal_price) * 100
        
        # 60-minute outcome
        if len(future_window) >= 61:
            price_60m = future_window.iloc[60]['close']
            outcomes['outcome_60m'] = ((price_60m - signal_price) / signal_price) * 100
        
        # Max drawdown & favorable
        min_price = future_window['low'].min()
        max_price = future_window['high'].max()
        outcomes['max_drawdown'] = ((min_price - signal_price) / signal_price) * 100
        outcomes['max_favorable'] = ((max_price - signal_price) / signal_price) * 100
        
        return outcomes
    
    def create_training_sample(self, snapshot: Dict, pattern: Dict, outcomes: Dict) -> Dict:
        """Create ML training sample from snapshot, pattern, and outcomes."""
        sample = {
            'symbol': snapshot['symbol'],
            'created_at': snapshot['timestamp'],
            'pattern_id': pattern['pattern_id'],
            'direction': pattern['direction'],
            'confidence': pattern.get('confidence', 0.8),
            
            # Dimension snapshot
            'dimension_snapshot': json.dumps({
                'dim_momentum': snapshot['dim_momentum'],
                'dim_trend': snapshot['dim_trend'],
                'dim_volatility': snapshot['dim_volatility'],
            }),
            
            # Dimension states
            'dim_momentum': snapshot['dim_momentum'],
            'dim_trend': snapshot['dim_trend'],
            'dim_volatility': snapshot['dim_volatility'],
            
            # Raw indicators
            'raw_rsi': snapshot['raw_rsi'],
            'raw_stoch_k': snapshot['raw_stoch_k'],
            'raw_macd_histogram': snapshot['raw_macd_histogram'],
            'raw_ema_9': snapshot['raw_ema_9'],
            'raw_ema_21': snapshot['raw_ema_21'],
            'raw_ema_50': snapshot['raw_ema_50'],
            'raw_slope_20': snapshot['raw_slope_20'],
            'raw_atr_pct': snapshot['raw_atr_pct'],
            'raw_bb_bandwidth': snapshot['raw_bb_bandwidth'],
            'raw_bb_pct': snapshot['raw_bb_pct'],
            'raw_volume_ratio': snapshot['raw_volume_ratio'],
            'raw_vwap_distance_pct': snapshot['raw_vwap_distance_pct'],
            
            # Outcomes
            'entry_price': outcomes['entry_price'],
            'outcome_5m': outcomes['outcome_5m'],
            'outcome_15m': outcomes['outcome_15m'],
            'outcome_60m': outcomes['outcome_60m'],
            'max_drawdown': outcomes['max_drawdown'],
            'max_favorable': outcomes['max_favorable'],
            
            # Labels (basic)
            'label_profitable_5m': 1 if (outcomes['outcome_5m'] and outcomes['outcome_5m'] > 0) else 0,
            'label_profitable_15m': 1 if (outcomes['outcome_15m'] and outcomes['outcome_15m'] > 0) else 0,
            
            # Quality label
            'label_quality': self.classify_quality(outcomes),
            
            # Metadata
            'data_source': 'historical_replay',
        }
        
        return sample
    
    def classify_quality(self, outcomes: Dict) -> str:
        """Classify trade quality based on outcomes."""
        if outcomes['outcome_5m'] is None:
            return 'unknown'
        
        # Crash: fast loss or big drawdown
        if outcomes['outcome_5m'] <= -3.0 or (outcomes['max_drawdown'] and outcomes['max_drawdown'] <= -5.0):
            return 'crash'
        
        # Great: good profit, small drawdown
        if outcomes['outcome_5m'] >= 2.0 and (outcomes['max_drawdown'] and outcomes['max_drawdown'] >= -1.0):
            return 'profitable'
        
        # Bad: loss or big drawdown
        if outcomes['outcome_5m'] <= -1.0 or (outcomes['max_drawdown'] and outcomes['max_drawdown'] <= -3.0):
            return 'losing'
        
        return 'normal'
    
    def save_training_sample(self, sample: Dict):
        """Save training sample to database."""
        if self.dry_run:
            print(f"  [DRY RUN] Would save sample: {sample['symbol']} {sample['pattern_id']} @ {sample['created_at']} → {sample['outcome_5m']:.2f}% (quality: {sample['label_quality']})")
            return
        
        # Insert to ml_training_samples table
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO ml_training_samples (
                symbol, created_at, pattern_id, direction, confidence,
                dimension_snapshot,
                dim_momentum, dim_trend, dim_volatility,
                raw_rsi, raw_stoch_k, raw_macd_histogram,
                raw_ema_9, raw_ema_21, raw_ema_50, raw_slope_20,
                raw_atr_pct, raw_bb_bandwidth, raw_bb_pct,
                raw_volume_ratio, raw_vwap_distance_pct,
                entry_price, outcome_5m, outcome_15m, outcome_60m,
                max_drawdown, max_favorable,
                label_profitable_5m, label_profitable_15m, label_quality,
                data_source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            sample['symbol'], sample['created_at'], sample['pattern_id'],
            sample['direction'], sample['confidence'], sample['dimension_snapshot'],
            sample['dim_momentum'], sample['dim_trend'], sample['dim_volatility'],
            sample['raw_rsi'], sample['raw_stoch_k'], sample['raw_macd_histogram'],
            sample['raw_ema_9'], sample['raw_ema_21'], sample['raw_ema_50'],
            sample['raw_slope_20'], sample['raw_atr_pct'], sample['raw_bb_bandwidth'],
            sample['raw_bb_pct'], sample['raw_volume_ratio'], sample['raw_vwap_distance_pct'],
            sample['entry_price'], sample['outcome_5m'], sample['outcome_15m'],
            sample['outcome_60m'], sample['max_drawdown'], sample['max_favorable'],
            sample['label_profitable_5m'], sample['label_profitable_15m'],
            sample['label_quality'], sample['data_source']
        ))
        
        conn.commit()
        self.stats['samples_created'] += 1
    
    def replay_symbol(self, symbol: str, start_date: str, end_date: str):
        """Replay entire symbol history."""
        print(f"\n🔄 REPLAYING {symbol}")
        print(f"   Period: {start_date} to {end_date}")
        
        # Download bars
        bars = self.download_historical_bars(symbol, start_date, end_date)
        if bars.empty:
            return
        
        # Calculate indicators
        print(f"📊 Calculating indicators...")
        df = self.calculate_indicators(bars)
        
        # Drop NaN rows (warm-up period for indicators)
        df = df.dropna()
        print(f"✅ {len(df)} bars ready for analysis (after indicator warm-up)")
        
        # Iterate through bars
        print(f"🔍 Detecting patterns and labeling outcomes...")
        
        for idx in range(len(df) - 61):  # Need 60 bars ahead for outcome labeling
            bar = df.iloc[idx]
            self.stats['bars_processed'] += 1
            
            # Create dimension snapshot
            bar_data = {
                'timestamp': bar.name,  # Index is timestamp
                'symbol': symbol,
                'close': bar['close'],
                'volume': bar['volume'],
                'rsi': bar['rsi'],
                'stoch_k': bar['stoch_k'],
                'macd_histogram': bar['macd_histogram'],
                'ema_9': bar['ema_9'],
                'ema_21': bar['ema_21'],
                'ema_50': bar['ema_50'],
                'slope_20': bar['slope_20'],
                'atr_pct': bar['atr_pct'],
                'bb_bandwidth': bar['bb_bandwidth'],
                'bb_pct': bar['bb_pct'],
                'volume_ratio': bar['volume_ratio'],
                'vwap_distance_pct': bar['vwap_distance_pct'],
            }
            
            snapshot = self.classify_dimension_snapshot(bar_data)
            
            # Detect patterns
            patterns = self.detect_patterns(snapshot)
            
            if not patterns:
                continue
            
            self.stats['signals_detected'] += len(patterns)
            
            # Label outcomes for each pattern
            for pattern in patterns:
                outcomes = self.label_outcomes(df, idx, bar.name)
                
                if outcomes['outcome_5m'] is None:
                    continue
                
                # Create training sample
                sample = self.create_training_sample(snapshot, pattern, outcomes)
                
                # Save to database
                self.save_training_sample(sample)
            
            # Progress update every 1000 bars
            if self.stats['bars_processed'] % 1000 == 0:
                elapsed = time.time() - self.stats['start_time']
                rate = self.stats['bars_processed'] / elapsed
                print(f"  Progress: {self.stats['bars_processed']:,} bars | {self.stats['signals_detected']} signals | {self.stats['samples_created']} samples | {rate:.1f} bars/sec")
    
    def print_summary(self):
        """Print replay summary."""
        elapsed = time.time() - self.stats['start_time']
        
        print(f"\n{'='*60}")
        print(f"📊 HISTORICAL REPLAY SUMMARY")
        print(f"{'='*60}")
        print(f"Bars processed:    {self.stats['bars_processed']:,}")
        print(f"Signals detected:  {self.stats['signals_detected']:,}")
        print(f"Samples created:   {self.stats['samples_created']:,}")
        print(f"Elapsed time:      {elapsed:.1f}s ({elapsed/60:.1f} min)")
        print(f"Processing rate:   {self.stats['bars_processed']/elapsed:.1f} bars/sec")
        
        if self.stats['signals_detected'] > 0:
            conversion = (self.stats['samples_created'] / self.stats['signals_detected']) * 100
            print(f"Signal→Sample:     {conversion:.1f}%")
        
        print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description='Historical Replay Engine - Generate Training Data from Historical Bars')
    
    parser.add_argument('--symbol', type=str, help='Single symbol to replay (e.g., BTC/USD)')
    parser.add_argument('--symbols', type=str, help='Comma-separated symbols (e.g., BTC/USD,ETH/USD)')
    parser.add_argument('--days', type=int, help='Number of days to replay (from today backwards)')
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--dry-run', action='store_true', help='Dry run - don\'t save to database')
    
    args = parser.parse_args()
    
    # Determine symbols
    symbols = []
    if args.symbol:
        symbols.append(args.symbol)
    if args.symbols:
        symbols.extend(args.symbols.split(','))
    
    if not symbols:
        symbols = ['BTC/USD']  # Default
    
    # Determine date range
    if args.start and args.end:
        start_date = args.start
        end_date = args.end
    elif args.days:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=args.days)).strftime('%Y-%m-%d')
    else:
        # Default: last 7 days
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    
    # Create replay engine
    replay = HistoricalReplay(dry_run=args.dry_run)
    
    print(f"\n{'='*60}")
    print(f"🔄 HISTORICAL REPLAY ENGINE")
    print(f"{'='*60}")
    print(f"Symbols:     {', '.join(symbols)}")
    print(f"Date range:  {start_date} to {end_date}")
    print(f"Dry run:     {args.dry_run}")
    print(f"{'='*60}\n")
    
    if args.dry_run:
        print("⚠️  DRY RUN MODE - No data will be saved to database\n")
    
    # Replay each symbol
    for symbol in symbols:
        try:
            replay.replay_symbol(symbol, start_date, end_date)
        except Exception as e:
            print(f"❌ Error replaying {symbol}: {e}")
            import traceback
            traceback.print_exc()
    
    # Print summary
    replay.print_summary()
    
    if not args.dry_run and replay.stats['samples_created'] > 0:
        print(f"✅ Created {replay.stats['samples_created']} new training samples!")
        print(f"📊 Run this to see updated dataset size:")
        print(f"   sqlite3 data/market.db 'SELECT COUNT(*) FROM ml_training_samples;'")
        print(f"\n🤖 Retrain model to incorporate new samples:")
        print(f"   python -m core.ml.crash_predictor_trainer --train\n")


if __name__ == '__main__':
    main()
