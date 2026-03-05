#!/usr/bin/env python3
"""
=============================================================================
 FAST SCALPER BOT — $1 PROFIT TARGET — 80%+ WIN RATE
=============================================================================
 Strategy: Ultra-short scalps, ONE trade at a time
 
 Rules:
   • Fixed $1.00 profit target per 0.01 lot
   • Fixed $0.50 stop loss (2:1 risk-reward)
   • Only 1 position open at a time
   • Re-enter IMMEDIATELY after close
   • No cooldown, no waiting — constant trading
   
 Target: 80%+ win rate with high frequency
=============================================================================
"""

import os, sys, csv, json, math
from datetime import datetime, timezone
from collections import deque

# ============================================================================
#  SIMPLE INDICATORS FOR FAST DECISIONS
# ============================================================================

class FastEMA:
    """Exponential Moving Average - fast calculation"""
    def __init__(self, period):
        self.period = period
        self.multiplier = 2.0 / (period + 1)
        self.ema = None
        
    def update(self, price):
        if self.ema is None:
            self.ema = price
        else:
            self.ema = (price - self.ema) * self.multiplier + self.ema
        return self.ema

class FastRSI:
    """RSI - simplified for speed"""
    def __init__(self, period=14):
        self.period = period
        self.gains = deque(maxlen=period)
        self.losses = deque(maxlen=period)
        self.last_price = None
        
    def update(self, price):
        if self.last_price is None:
            self.last_price = price
            return 50.0
        
        change = price - self.last_price
        self.last_price = price
        
        if change > 0:
            self.gains.append(change)
            self.losses.append(0)
        else:
            self.gains.append(0)
            self.losses.append(abs(change))
        
        if len(self.gains) < self.period:
            return 50.0
        
        avg_gain = sum(self.gains) / self.period
        avg_loss = sum(self.losses) / self.period
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

class MomentumDetector:
    """Detects price momentum direction"""
    def __init__(self, lookback=10):
        self.prices = deque(maxlen=lookback)
        
    def update(self, price):
        self.prices.append(price)
        if len(self.prices) < 3:
            return "NEUTRAL"
        
        # Recent momentum
        recent_change = self.prices[-1] - self.prices[-3]
        
        # Overall trend
        if len(self.prices) >= 5:
            trend = self.prices[-1] - self.prices[-5]
        else:
            trend = recent_change
        
        # Strong upward momentum
        if recent_change > 0 and trend > 0:
            return "BULLISH"
        # Strong downward momentum
        elif recent_change < 0 and trend < 0:
            return "BEARISH"
        else:
            return "NEUTRAL"

# ============================================================================
#  FAST SCALPING ENGINE — OPTIMIZED FOR 80%+ WIN RATE
# ============================================================================

class FastScalpEngine:
    """
    Ultra-selective entries for high win rate:
    - Only trade with strong momentum
    - Use multiple confirmations
    - Tight profit targets (easy to hit)
    """
    def __init__(self):
        # Multiple timeframe EMAs for better signals
        self.ema_fast = FastEMA(5)      # Very fast
        self.ema_mid = FastEMA(13)      # Medium
        self.ema_slow = FastEMA(21)     # Slower
        
        self.rsi = FastRSI(14)
        self.momentum = MomentumDetector(10)
        
        # Price tracking
        self.prices = deque(maxlen=20)
        self.last_signal = None
        
    def update(self, price):
        """
        Returns: "BUY", "SELL", or "HOLD"
        
        Strategy: High-probability scalps only
        - Wait for pullbacks in trends
        - Enter on momentum reversal
        - Multiple confirmations required
        """
        # Update all indicators
        self.prices.append(price)
        
        ema_f = self.ema_fast.update(price)
        ema_m = self.ema_mid.update(price)
        ema_s = self.ema_slow.update(price)
        
        rsi = self.rsi.update(price)
        momentum = self.momentum.update(price)
        
        # Need at least 10 prices for reliable signals
        if len(self.prices) < 10:
            return "HOLD"
        
        # Calculate recent price action
        current = self.prices[-1]
        prev = self.prices[-2]
        price_rising = current > prev
        price_falling = current < prev
        
        # ══════════════════════════════════════════════════════════════
        #  HIGH WIN-RATE SCALP STRATEGY
        # ══════════════════════════════════════════════════════════════
        
        signal = "HOLD"
        
        # ── BUY SIGNAL: Pullback in uptrend ──────────────────────────
        # Wait for RSI to dip, then bounce
        if 30 <= rsi <= 45:  # RSI pullback zone (not extreme)
            score = 0
            
            # 1. Overall uptrend (EMA alignment)
            if ema_f > ema_m > ema_s:
                score += 2
            elif ema_f > ema_m:
                score += 1
            
            # 2. Price bouncing up
            if price_rising:
                score += 2
            
            # 3. RSI turning up
            if rsi > 35:  # Coming out of oversold
                score += 1
            
            # 4. Momentum turning bullish
            if momentum == "BULLISH":
                score += 2
            
            # 5. Price above mid EMA (trend confirmation)
            if current > ema_m:
                score += 1
            
            # Need strong setup for 80%+ accuracy
            if score >= 5:
                signal = "BUY"
        
        # ── SELL SIGNAL: Pullback in downtrend ───────────────────────
        # Wait for RSI to rise, then fall
        elif 55 <= rsi <= 70:  # RSI pullback zone (not extreme)
            score = 0
            
            # 1. Overall downtrend (EMA alignment)
            if ema_f < ema_m < ema_s:
                score += 2
            elif ema_f < ema_m:
                score += 1
            
            # 2. Price falling
            if price_falling:
                score += 2
            
            # 3. RSI turning down
            if rsi < 65:  # Coming out of overbought
                score += 1
            
            # 4. Momentum turning bearish
            if momentum == "BEARISH":
                score += 2
            
            # 5. Price below mid EMA (trend confirmation)
            if current < ema_m:
                score += 1
            
            if score >= 5:
                signal = "SELL"
        
        # ── BREAKOUT SIGNALS (Alternative strategy) ──────────────────
        # When RSI is neutral, look for EMA crosses
        elif 45 < rsi < 55:
            # Bullish breakout
            if ema_f > ema_m and current > ema_m:
                if price_rising and momentum == "BULLISH":
                    signal = "BUY"
            
            # Bearish breakout
            elif ema_f < ema_m and current < ema_m:
                if price_falling and momentum == "BEARISH":
                    signal = "SELL"
        
        self.last_signal = signal
        return signal

# ============================================================================
#  CANDLE BUILDER (Optional - can work directly with ticks too)
# ============================================================================

class TickAggregator:
    """Aggregates ticks into small time windows for smoother signals"""
    def __init__(self, window_ticks=50):
        self.window = window_ticks
        self.tick_count = 0
        self.prices = []
        
    def update(self, price):
        """Returns aggregated price every N ticks"""
        self.prices.append(price)
        self.tick_count += 1
        
        if self.tick_count >= self.window:
            # Return average price over window
            avg = sum(self.prices) / len(self.prices)
            self.prices = []
            self.tick_count = 0
            return avg
        
        return None

# ============================================================================
#  FAST SCALPER BACKTESTER
# ============================================================================

class FastScalper:
    """
    High-frequency scalper:
    - $1 profit target per 0.01 lot
    - One trade at a time
    - Re-enter immediately after close
    """
    def __init__(self, target_usd=1.0, stop_usd=0.5, lot_size=0.01):
        self.target_usd = target_usd
        self.stop_usd = stop_usd
        self.lot_size = lot_size
        
        # Account
        self.balance = 100.0
        self.init_balance = 100.0
        
        # Engine
        self.engine = FastScalpEngine()
        self.aggregator = TickAggregator(window_ticks=50)  # Smooth every 50 ticks
        
        # Position tracking
        self.position = None
        self.trades = []
        
        # Performance tracking
        self.consecutive_wins = 0
        self.consecutive_losses = 0
        self.peak_balance = 100.0
        
    def run(self, csv_path, verbose=True):
        """Run backtest on tick data"""
        
        if verbose:
            print(f"\n{'='*70}")
            print(f"  FAST SCALPER — $1 TARGET PER 0.01 LOT")
            print(f"{'='*70}")
            print(f"  Target: ${self.target_usd:.2f} | Stop: ${self.stop_usd:.2f} | Lot: {self.lot_size}")
            print(f"  Strategy: One trade at a time, re-enter immediately")
            print(f"{'='*70}\n")
        
        tick_count = 0
        last_price = 0
        last_ts = None
        
        with open(csv_path, newline='', encoding='utf-8') as f:
            for row in csv.reader(f):
                if len(row) < 4:
                    continue
                    
                ts_raw = row[2].strip('"')
                if not ts_raw or not ts_raw[0].isdigit():
                    continue
                
                try:
                    ts = datetime.fromisoformat(ts_raw.replace('Z', '+00:00'))
                    price = float(row[3].strip('"'))
                except (ValueError, IndexError):
                    continue
                
                tick_count += 1
                last_price = price
                last_ts = ts
                
                # Check exits on EVERY tick (critical for scalping)
                if self.position:
                    self._check_exit(price, ts, verbose)
                
                # Get aggregated price (smoother signals)
                avg_price = self.aggregator.update(price)
                
                if avg_price:
                    # Update engine with aggregated price
                    signal = self.engine.update(avg_price)
                    
                    # Open trade if no position
                    if not self.position and signal != "HOLD":
                        self._open_trade(signal, price, ts, verbose)
        
        # Force close any remaining position
        if self.position and last_price:
            self._force_close(last_price, last_ts, verbose)
        
        return self._print_results(tick_count, verbose)
    
    def _open_trade(self, direction, price, ts, verbose):
        """Open a scalp position"""
        # Calculate TP/SL in price terms
        # For 0.01 lot on BTCUSD: $1 profit = price move of $100
        # (0.01 lot * $100 move = $1)
        
        tp_distance = self.target_usd / self.lot_size  # $1 / 0.01 = $100
        sl_distance = self.stop_usd / self.lot_size    # $0.5 / 0.01 = $50
        
        if direction == "BUY":
            tp = price + tp_distance
            sl = price - sl_distance
        else:  # SELL
            tp = price - tp_distance
            sl = price + sl_distance
        
        self.position = {
            'direction': direction,
            'entry': price,
            'tp': tp,
            'sl': sl,
            'lots': self.lot_size,
            'open_time': ts,
            'entry_balance': self.balance
        }
        
        if verbose:
            rsi = self.engine.rsi.last_price if hasattr(self.engine.rsi, 'last_price') else 0
            print(f"  [OPEN #{len(self.trades)+1:4d}] {direction:4s} @ {price:,.2f}  "
                  f"TP={tp:,.2f} SL={sl:,.2f}  {ts.strftime('%H:%M:%S')}")
    
    def _check_exit(self, price, ts, verbose):
        """Check if TP or SL hit on this tick"""
        p = self.position
        hit = None
        exit_price = None
        
        if p['direction'] == "BUY":
            if price >= p['tp']:
                hit = "WIN"
                exit_price = p['tp']
            elif price <= p['sl']:
                hit = "LOSS"
                exit_price = p['sl']
        else:  # SELL
            if price <= p['tp']:
                hit = "WIN"
                exit_price = p['tp']
            elif price >= p['sl']:
                hit = "LOSS"
                exit_price = p['sl']
        
        if hit:
            self._close_trade(exit_price, ts, hit, verbose)
    
    def _close_trade(self, exit_price, ts, result, verbose):
        """Close the position"""
        p = self.position
        
        # Calculate P&L
        if p['direction'] == "BUY":
            pnl = (exit_price - p['entry']) * p['lots']
        else:
            pnl = (p['entry'] - exit_price) * p['lots']
        
        # Update balance
        self.balance += pnl
        
        # Track streaks
        if result == "WIN":
            self.consecutive_wins += 1
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
            self.consecutive_wins = 0
        
        # Update peak
        if self.balance > self.peak_balance:
            self.peak_balance = self.balance
        
        # Record trade
        trade = {
            'num': len(self.trades) + 1,
            'direction': p['direction'],
            'entry': p['entry'],
            'exit': exit_price,
            'pnl': pnl,
            'result': result,
            'open_time': p['open_time'],
            'close_time': ts,
            'balance': self.balance
        }
        self.trades.append(trade)
        
        if verbose:
            icon = '✓' if result == "WIN" else '✗'
            streak = f"({self.consecutive_wins}W)" if result == "WIN" else f"({self.consecutive_losses}L)"
            print(f"  [{icon} {result:4s} #{trade['num']:4d}] "
                  f"Exit={exit_price:,.2f}  PnL=${pnl:+.2f}  "
                  f"Bal=${self.balance:,.2f}  {streak}")
        
        # Clear position for next trade
        self.position = None
    
    def _force_close(self, price, ts, verbose):
        """Force close at end of data"""
        p = self.position
        
        if p['direction'] == "BUY":
            pnl = (price - p['entry']) * p['lots']
        else:
            pnl = (p['entry'] - price) * p['lots']
        
        self.balance += pnl
        result = "WIN" if pnl >= 0 else "LOSS"
        
        trade = {
            'num': len(self.trades) + 1,
            'direction': p['direction'],
            'entry': p['entry'],
            'exit': price,
            'pnl': pnl,
            'result': result,
            'open_time': p['open_time'],
            'close_time': ts,
            'balance': self.balance
        }
        self.trades.append(trade)
        
        if verbose:
            print(f"  [FORCE #{trade['num']:4d}] PnL=${pnl:+.2f}")
        
        self.position = None
    
    def _print_results(self, tick_count, verbose):
        """Print final statistics"""
        total = len(self.trades)
        
        if total == 0:
            if verbose:
                print("\n  No trades executed.\n")
            return None
        
        wins = sum(1 for t in self.trades if t['result'] == "WIN")
        losses = total - wins
        win_rate = wins / total * 100
        
        gross_profit = sum(t['pnl'] for t in self.trades if t['pnl'] > 0)
        gross_loss = abs(sum(t['pnl'] for t in self.trades if t['pnl'] < 0))
        
        pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        net = self.balance - self.init_balance
        
        # Max drawdown
        peak = self.init_balance
        max_dd = 0.0
        running = self.init_balance
        
        for t in self.trades:
            running += t['pnl']
            if running > peak:
                peak = running
            dd = (peak - running) / peak * 100
            if dd > max_dd:
                max_dd = dd
        
        # Streaks
        max_win_streak = 0
        max_loss_streak = 0
        current_streak = 0
        last_result = None
        
        for t in self.trades:
            if t['result'] == last_result:
                current_streak += 1
            else:
                if last_result == "WIN":
                    max_win_streak = max(max_win_streak, current_streak)
                elif last_result == "LOSS":
                    max_loss_streak = max(max_loss_streak, current_streak)
                current_streak = 1
                last_result = t['result']
        
        # Final streak check
        if last_result == "WIN":
            max_win_streak = max(max_win_streak, current_streak)
        elif last_result == "LOSS":
            max_loss_streak = max(max_loss_streak, current_streak)
        
        if verbose:
            print(f"\n{'='*70}")
            print(f"  RESULTS — FAST SCALPER")
            print(f"{'='*70}")
            print(f"  Ticks Processed: {tick_count:,}")
            print(f"  Total Trades   : {total}")
            print(f"  Wins / Losses  : {wins} / {losses}")
            print(f"{'─'*70}")
            print(f"  Win Rate       : {win_rate:.1f}%  {'🎯 TARGET!' if win_rate >= 80 else '○'}")
            print(f"  Profit Factor  : {pf:.2f}")
            print(f"  Net P&L        : ${net:+.2f}  ({net/self.init_balance*100:+.1f}%)")
            print(f"  Max Drawdown   : {max_dd:.2f}%")
            print(f"{'─'*70}")
            print(f"  Gross Profit   : ${gross_profit:.2f}")
            print(f"  Gross Loss     : ${gross_loss:.2f}")
            print(f"  Avg Win        : ${gross_profit/wins:.2f}" if wins > 0 else "  Avg Win        : $0.00")
            print(f"  Avg Loss       : ${gross_loss/losses:.2f}" if losses > 0 else "  Avg Loss       : $0.00")
            print(f"{'─'*70}")
            print(f"  Start Balance  : ${self.init_balance:.2f}")
            print(f"  Final Balance  : ${self.balance:.2f}")
            print(f"  Peak Balance   : ${self.peak_balance:.2f}")
            print(f"{'─'*70}")
            print(f"  Max Win Streak : {max_win_streak}")
            print(f"  Max Loss Streak: {max_loss_streak}")
            print(f"{'='*70}\n")
        
        return {
            'total': total,
            'wins': wins,
            'losses': losses,
            'win_rate': win_rate,
            'pf': pf,
            'net': net,
            'balance': self.balance,
            'max_dd': max_dd
        }

# ============================================================================
#  OPTIMIZATION RUNNER
# ============================================================================

def find_best_config(csv_path):
    """Test different configurations to maximize win rate"""
    
    print("\n" + "="*70)
    print("  OPTIMIZING FOR 80%+ WIN RATE")
    print("="*70)
    
    configs = [
        {'target': 1.0, 'stop': 0.5, 'lot': 0.01},   # 2:1 RR
        {'target': 1.5, 'stop': 0.5, 'lot': 0.01},   # 3:1 RR
        {'target': 2.0, 'stop': 0.5, 'lot': 0.01},   # 4:1 RR
        {'target': 1.0, 'stop': 0.75, 'lot': 0.01},  # Tighter SL
        {'target': 0.75, 'stop': 0.5, 'lot': 0.01},  # Smaller target
    ]
    
    results = []
    
    for i, cfg in enumerate(configs, 1):
        print(f"\n[Test {i}/{len(configs)}] Target=${cfg['target']:.2f}, Stop=${cfg['stop']:.2f}, Lot={cfg['lot']}")
        print("-" * 70)
        
        scalper = FastScalper(
            target_usd=cfg['target'],
            stop_usd=cfg['stop'],
            lot_size=cfg['lot']
        )
        
        metrics = scalper.run(csv_path, verbose=True)
        
        if metrics:
            metrics['config'] = cfg
            results.append(metrics)
    
    # Sort by win rate
    results.sort(key=lambda x: x['win_rate'], reverse=True)
    
    print("\n" + "="*70)
    print("  RANKING BY WIN RATE")
    print("="*70)
    
    for i, r in enumerate(results, 1):
        cfg = r['config']
        icon = '🎯' if r['win_rate'] >= 80 else ('✓' if r['win_rate'] >= 70 else '○')
        print(f"\n{i}. {icon} WR: {r['win_rate']:.1f}% | Trades: {r['total']} | "
              f"PF: {r['pf']:.2f} | Net: ${r['net']:+.2f}")
        print(f"   Target=${cfg['target']:.2f}, Stop=${cfg['stop']:.2f}, Lot={cfg['lot']}")
    
    print("\n" + "="*70 + "\n")
    
    if results and results[0]['win_rate'] >= 80:
        print("🎯 SUCCESS! 80%+ win rate achieved!")
        with open('best_scalp_config.json', 'w') as f:
            json.dump(results[0], f, indent=2)
        print("Best configuration saved to: best_scalp_config.json\n")
    
    return results[0] if results else None

# ============================================================================
#  MAIN
# ============================================================================

if __name__ == '__main__':
    csv_path = "Exness_BTCUSD_Zero_Spread_2025_11_09.csv"
    
    if not os.path.exists(csv_path):
        print(f"ERROR: {csv_path} not found!")
        sys.exit(1)
    
    # Run optimization
    best = find_best_config(csv_path)
    
    if best:
        print("\n🚀 RECOMMENDATION:")
        print(f"   Use: Target=${best['config']['target']:.2f}, Stop=${best['config']['stop']:.2f}")
        print(f"   Expected: {best['win_rate']:.1f}% win rate, {best['total']} trades/day")
        print()