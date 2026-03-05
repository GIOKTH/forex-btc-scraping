#!/usr/bin/env python3
"""
=============================================================================
 24/7 CRYPTO SCALPER — OPTIMIZED FOR BITCOIN
=============================================================================
 
 Strategy: Continuous scalping designed for crypto's 24/7 nature
 
 Key Optimizations for 24/7 Trading:
   • No session filters (BTC never closes)
   • Volatility-adaptive entries (crypto is volatile!)
   • Smart position management
   • Dynamic targets based on current volatility
   • Protection during low liquidity micro-periods
   
 Target: 70-80%+ win rate with smart filtering
=============================================================================
"""

import os, sys, csv, json, math
from datetime import datetime, timezone, timedelta
from collections import deque

# ============================================================================
#  FAST INDICATORS
# ============================================================================

class EMA:
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

class RSI:
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
        return 100 - (100 / (1 + rs))

class VolatilityTracker:
    """Track recent volatility for dynamic thresholds"""
    def __init__(self, period=20):
        self.prices = deque(maxlen=period)
        
    def update(self, price):
        self.prices.append(price)
        
    def get_volatility(self):
        """Return recent price range as % of current price"""
        if len(self.prices) < 5:
            return 0.0
        
        high = max(self.prices)
        low = min(self.prices)
        current = self.prices[-1]
        
        if current == 0:
            return 0.0
        
        return (high - low) / current * 100

class TrendDetector:
    """Detect current trend strength"""
    def __init__(self):
        self.ema_fast = EMA(8)
        self.ema_mid = EMA(21)
        self.ema_slow = EMA(55)
        
    def update(self, price):
        ef = self.ema_fast.update(price)
        em = self.ema_mid.update(price)
        es = self.ema_slow.update(price)
        
        if None in [ef, em, es]:
            return "NEUTRAL", 0
        
        # Strong uptrend
        if ef > em > es:
            strength = ((ef - es) / es * 100) if es > 0 else 0
            return "UPTREND", min(strength, 100)
        
        # Strong downtrend
        elif ef < em < es:
            strength = ((es - ef) / es * 100) if es > 0 else 0
            return "DOWNTREND", min(strength, 100)
        
        # Neutral/choppy
        else:
            return "NEUTRAL", 0

# ============================================================================
#  24/7 CRYPTO ENGINE — SMART ENTRIES
# ============================================================================

class Crypto247Engine:
    """
    Optimized for 24/7 crypto trading:
    - Adapts to current volatility
    - Detects trend vs range
    - Avoids ultra-low liquidity micro-periods
    - High-probability setups only
    """
    
    def __init__(self, min_volatility=0.02, max_volatility=1.0):  # Relaxed
        # Core indicators
        self.ema_fast = EMA(5)
        self.ema_mid = EMA(13)
        self.ema_slow = EMA(34)
        self.rsi = RSI(14)
        
        # Market analysis
        self.volatility = VolatilityTracker(30)
        self.trend = TrendDetector()
        
        # Settings
        self.min_vol = min_volatility  # Skip if too quiet (reduced)
        self.max_vol = max_volatility  # Skip if too wild (increased)
        
        # State
        self.prices = deque(maxlen=50)
        self.last_signal = None
        self.bars_since_signal = 0
        
    def update(self, price):
        """
        Returns: "BUY", "SELL", or "HOLD"
        
        Strategy for 24/7 crypto:
        1. Check volatility regime (avoid extremes)
        2. Detect trend direction
        3. Wait for pullback in trends
        4. Enter on momentum confirmation
        """
        self.prices.append(price)
        self.bars_since_signal += 1
        
        # Update all indicators
        ef = self.ema_fast.update(price)
        em = self.ema_mid.update(price)
        es = self.ema_slow.update(price)
        rsi = self.rsi.update(price)
        
        self.volatility.update(price)
        trend, strength = self.trend.update(price)
        
        # Need enough data
        if len(self.prices) < 20 or None in [ef, em, es]:
            return "HOLD"
        
        # Get volatility
        vol = self.volatility.get_volatility()
        
        # ══════════════════════════════════════════════════════════════
        #  FILTER 1: VOLATILITY REGIME
        # ══════════════════════════════════════════════════════════════
        
        # Too quiet (low liquidity micro-period) - skip
        if vol < self.min_vol:
            return "HOLD"
        
        # Too volatile (flash crash / pump) - skip
        if vol > self.max_vol:
            return "HOLD"
        
        # ══════════════════════════════════════════════════════════════
        #  FILTER 2: AVOID RAPID RE-ENTRY
        # ══════════════════════════════════════════════════════════════
        
        # Wait at least 2 bars between signals (was 3)
        if self.bars_since_signal < 2:
            return "HOLD"
        
        # ══════════════════════════════════════════════════════════════
        #  STRATEGY: TREND PULLBACK ENTRIES (70-80% WR)
        # ══════════════════════════════════════════════════════════════
        
        current = self.prices[-1]
        prev = self.prices[-2]
        
        signal = "HOLD"
        
        # ── UPTREND: Buy pullbacks ──────────────────────────────────
        if trend == "UPTREND" and strength > 0.1:  # More lenient (was 0.3)
            # Looking for pullback that's bouncing
            if 35 < rsi < 50:  # Pullback zone in uptrend
                # Confirm bounce
                score = 0
                
                # 1. Price bouncing from pullback
                if current > prev:
                    score += 3
                
                # 2. Still above mid EMA (trend intact)
                if current > em:
                    score += 2
                
                # 3. Fast EMA above mid (structure good)
                if ef > em:
                    score += 2
                
                # 4. RSI turning up
                if rsi > 38:
                    score += 1
                
                # Need good confirmation for 60-70% WR
                if score >= 4:  # Reduced from 6
                    signal = "BUY"
        
        # ── DOWNTREND: Sell pullbacks ───────────────────────────────
        elif trend == "DOWNTREND" and strength > 0.1:  # More lenient
            # Looking for pullback that's rejecting
            if 50 < rsi < 65:  # Pullback zone in downtrend
                score = 0
                
                # 1. Price rejecting from pullback
                if current < prev:
                    score += 3
                
                # 2. Still below mid EMA (trend intact)
                if current < em:
                    score += 2
                
                # 3. Fast EMA below mid (structure good)
                if ef < em:
                    score += 2
                
                # 4. RSI turning down
                if rsi < 62:
                    score += 1
                
                if score >= 4:  # Reduced from 6
                    signal = "SELL"
        
        # ── NEUTRAL: Range breakout ──────────────────────────────────
        elif trend == "NEUTRAL":
            # In ranging market, trade bounces off extremes
            
            # Oversold bounce
            if rsi <= 30:
                if current > prev and current > ef:  # Bouncing
                    signal = "BUY"
            
            # Overbought fade
            elif rsi >= 70:
                if current < prev and current < ef:  # Rejecting
                    signal = "SELL"
        
        # Update state
        if signal != "HOLD":
            self.last_signal = signal
            self.bars_since_signal = 0
        
        return signal

# ============================================================================
#  POSITION
# ============================================================================

class Position:
    def __init__(self, direction, entry, sl, tp, lots, ts):
        self.direction = direction
        self.entry = entry
        self.sl = sl
        self.tp = tp
        self.lots = lots
        self.open_time = ts
        self.close_time = None
        self.close_price = None
        self.pnl = 0.0
        self.result = None
        self.peak_profit = 0.0

# ============================================================================
#  24/7 CRYPTO SCALPER
# ============================================================================

class Crypto247Scalper:
    """
    Continuous crypto scalper with:
    - Dynamic TP/SL based on volatility
    - Trailing stops
    - Smart re-entry logic
    """
    
    def __init__(self, base_target=1.0, base_stop=0.5, lot_size=0.01,
                 use_trailing=True, max_consecutive_losses=3):
        
        self.base_target = base_target
        self.base_stop = base_stop
        self.lot_size = lot_size
        self.use_trailing = use_trailing
        self.max_consecutive_losses = max_consecutive_losses
        
        # Account
        self.balance = 100.0
        self.init_balance = 100.0
        
        # Engine
        self.engine = Crypto247Engine()
        
        # Position
        self.position = None
        self.trades = []
        
        # Risk management
        self.consecutive_losses = 0
        self.consecutive_wins = 0
        self.in_cooldown = 0
        
    def run(self, csv_path, verbose=True):
        """Run 24/7 backtest"""
        
        if verbose:
            print(f"\n{'='*70}")
            print(f"  24/7 CRYPTO SCALPER — BITCOIN OPTIMIZED")
            print(f"{'='*70}")
            print(f"  Target: ${self.base_target:.2f} | Stop: ${self.base_stop:.2f}")
            print(f"  Trailing: {'ON' if self.use_trailing else 'OFF'}")
            print(f"  Max Consecutive Losses: {self.max_consecutive_losses}")
            print(f"{'='*70}\n")
        
        tick_count = 0
        aggregator = TickAggregator(ticks_per_bar=100)  # Smooth signals
        
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
                
                # Check exits on every tick
                if self.position:
                    self._check_exit(price, ts, verbose)
                
                # Aggregate ticks for smoother signals
                avg_price = aggregator.update(price)
                
                if avg_price and not self.position:
                    # Cooldown check
                    if self.in_cooldown > 0:
                        self.in_cooldown -= 1
                    else:
                        signal = self.engine.update(avg_price)
                        
                        if signal != "HOLD":
                            self._open_trade(signal, price, ts, verbose)
        
        # Force close any remaining
        if self.position:
            self._force_close(price, ts, verbose)
        
        return self._print_results(tick_count, verbose)
    
    def _open_trade(self, direction, price, ts, verbose):
        """Open position with dynamic targets based on volatility"""
        
        # Get current volatility
        vol = self.engine.volatility.get_volatility()
        
        # Dynamic TP/SL: scale with volatility
        # Higher volatility = wider targets
        vol_multiplier = max(1.0, min(2.0, vol / 0.15))  # 1x to 2x
        
        target = self.base_target * vol_multiplier
        stop = self.base_stop * vol_multiplier
        
        # Convert to price distance
        tp_dist = target / self.lot_size
        sl_dist = stop / self.lot_size
        
        if direction == "BUY":
            tp = price + tp_dist
            sl = price - sl_dist
        else:
            tp = price - tp_dist
            sl = price + sl_dist
        
        self.position = Position(direction, price, sl, tp, self.lot_size, ts)
        
        if verbose:
            rsi = self.engine.rsi.last_price if hasattr(self.engine.rsi, 'last_price') else 0
            trend, _ = self.engine.trend.update(price)
            print(f"  [OPEN #{len(self.trades)+1:3d}] {direction:4s} @ {price:,.2f}  "
                  f"TP={tp:,.2f} SL={sl:,.2f}  Vol={vol:.3f}  "
                  f"Trend={trend}  {ts.strftime('%H:%M:%S')}")
    
    def _check_exit(self, price, ts, verbose):
        """Check TP/SL with optional trailing"""
        p = self.position
        
        # Calculate current P&L
        if p.direction == "BUY":
            current_pnl = (price - p.entry) * p.lots
        else:
            current_pnl = (p.entry - price) * p.lots
        
        # Update peak
        if current_pnl > p.peak_profit:
            p.peak_profit = current_pnl
        
        # Trailing stop logic
        if self.use_trailing and p.peak_profit > self.base_target * 0.5:
            # Start trailing once we're 50% to target
            trail_dist = self.base_stop * 0.5 / p.lots  # Trail by half the stop
            
            if p.direction == "BUY":
                new_sl = price - trail_dist
                p.sl = max(p.sl, new_sl)  # Only move SL up
            else:
                new_sl = price + trail_dist
                p.sl = min(p.sl, new_sl)  # Only move SL down
        
        # Check exits
        hit = None
        exit_price = None
        
        if p.direction == "BUY":
            if price <= p.sl:
                hit = "LOSS" if current_pnl < 0 else "WIN"
                exit_price = p.sl
            elif price >= p.tp:
                hit = "WIN"
                exit_price = p.tp
        else:
            if price >= p.sl:
                hit = "LOSS" if current_pnl < 0 else "WIN"
                exit_price = p.sl
            elif price <= p.tp:
                hit = "WIN"
                exit_price = p.tp
        
        if hit:
            self._close_trade(exit_price, ts, hit, verbose)
    
    def _close_trade(self, exit_price, ts, result, verbose):
        """Close position and update stats"""
        p = self.position
        
        # Calculate final P&L
        if p.direction == "BUY":
            pnl = (exit_price - p.entry) * p.lots
        else:
            pnl = (p.entry - exit_price) * p.lots
        
        p.close_time = ts
        p.close_price = exit_price
        p.pnl = pnl
        p.result = result
        
        self.balance += pnl
        self.trades.append(p)
        self.position = None
        
        # Update streaks
        if result == "WIN":
            self.consecutive_wins += 1
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
            self.consecutive_wins = 0
            
            # Cooldown after max losses
            if self.consecutive_losses >= self.max_consecutive_losses:
                self.in_cooldown = 5  # Skip next 5 bars
        
        if verbose:
            icon = '✓' if result == "WIN" else '✗'
            streak = f"({self.consecutive_wins}W)" if result == "WIN" else f"({self.consecutive_losses}L)"
            
            # Show if trailed
            trailed = " [T]" if p.peak_profit > pnl and result == "WIN" else ""
            
            print(f"  [{icon} {result:4s} #{len(self.trades):3d}] "
                  f"Exit={exit_price:,.2f}  PnL=${pnl:+.2f}{trailed}  "
                  f"Bal=${self.balance:,.2f}  {streak}")
    
    def _force_close(self, price, ts, verbose):
        """Force close at end"""
        p = self.position
        
        if p.direction == "BUY":
            pnl = (price - p.entry) * p.lots
        else:
            pnl = (p.entry - price) * p.lots
        
        p.close_time = ts
        p.close_price = price
        p.pnl = pnl
        p.result = "WIN" if pnl >= 0 else "LOSS"
        
        self.balance += pnl
        self.trades.append(p)
        self.position = None
        
        if verbose:
            print(f"  [FORCE #{len(self.trades):3d}] PnL=${pnl:+.2f}")
    
    def _print_results(self, tick_count, verbose):
        """Print final statistics"""
        total = len(self.trades)
        
        if total == 0:
            if verbose:
                print("\n  No trades executed.\n")
            return None
        
        wins = sum(1 for t in self.trades if t.result == "WIN")
        losses = total - wins
        win_rate = wins / total * 100
        
        gp = sum(t.pnl for t in self.trades if t.pnl > 0)
        gl = abs(sum(t.pnl for t in self.trades if t.pnl < 0))
        pf = gp / gl if gl > 0 else float('inf')
        net = self.balance - self.init_balance
        
        # Max drawdown
        peak = self.init_balance
        max_dd = 0.0
        running = self.init_balance
        
        for t in self.trades:
            running += t.pnl
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
            if t.result == last_result:
                current_streak += 1
            else:
                if last_result == "WIN":
                    max_win_streak = max(max_win_streak, current_streak)
                elif last_result == "LOSS":
                    max_loss_streak = max(max_loss_streak, current_streak)
                current_streak = 1
                last_result = t.result
        
        if last_result == "WIN":
            max_win_streak = max(max_win_streak, current_streak)
        elif last_result == "LOSS":
            max_loss_streak = max(max_loss_streak, current_streak)
        
        if verbose:
            print(f"\n{'='*70}")
            print(f"  RESULTS — 24/7 CRYPTO SCALPER")
            print(f"{'='*70}")
            print(f"  Ticks Processed: {tick_count:,}")
            print(f"  Total Trades   : {total}")
            print(f"  Wins / Losses  : {wins} / {losses}")
            print(f"{'─'*70}")
            print(f"  Win Rate       : {win_rate:.1f}%  {'🎯 EXCELLENT!' if win_rate >= 70 else ('✓ GOOD' if win_rate >= 60 else '○')}")
            print(f"  Profit Factor  : {pf:.2f}")
            print(f"  Net P&L        : ${net:+.2f}  ({net/self.init_balance*100:+.1f}%)")
            print(f"  Max Drawdown   : {max_dd:.2f}%")
            print(f"{'─'*70}")
            print(f"  Gross Profit   : ${gp:.2f}")
            print(f"  Gross Loss     : ${gl:.2f}")
            print(f"  Avg Win        : ${gp/wins:.2f}" if wins > 0 else "  Avg Win        : $0.00")
            print(f"  Avg Loss       : ${gl/losses:.2f}" if losses > 0 else "  Avg Loss       : $0.00")
            print(f"{'─'*70}")
            print(f"  Start Balance  : ${self.init_balance:.2f}")
            print(f"  Final Balance  : ${self.balance:.2f}")
            print(f"{'─'*70}")
            print(f"  Max Win Streak : {max_win_streak}")
            print(f"  Max Loss Streak: {max_loss_streak}")
            print(f"{'='*70}\n")
        
        return {
            'total': total, 'wins': wins, 'losses': losses,
            'win_rate': win_rate, 'pf': pf, 'net': net,
            'balance': self.balance, 'max_dd': max_dd
        }

# ============================================================================
#  TICK AGGREGATOR
# ============================================================================

class TickAggregator:
    """Smooth tick data for better signals"""
    def __init__(self, ticks_per_bar=100):
        self.window = ticks_per_bar
        self.count = 0
        self.prices = []
        
    def update(self, price):
        self.prices.append(price)
        self.count += 1
        
        if self.count >= self.window:
            avg = sum(self.prices) / len(self.prices)
            self.prices = []
            self.count = 0
            return avg
        
        return None

# ============================================================================
#  OPTIMIZER
# ============================================================================

def optimize_247(csv_path):
    """Test different configurations"""
    
    print("\n" + "="*70)
    print("  24/7 CRYPTO OPTIMIZATION")
    print("="*70)
    
    configs = [
        # Base: Conservative
        {'target': 1.0, 'stop': 0.5, 'trailing': True, 'max_losses': 3},
        
        # Wider targets
        {'target': 1.5, 'stop': 0.5, 'trailing': True, 'max_losses': 3},
        
        # Tighter SL
        {'target': 1.0, 'stop': 0.4, 'trailing': True, 'max_losses': 3},
        
        # No trailing
        {'target': 1.0, 'stop': 0.5, 'trailing': False, 'max_losses': 3},
        
        # More patient (5 losses before cooldown)
        {'target': 1.0, 'stop': 0.5, 'trailing': True, 'max_losses': 5},
    ]
    
    results = []
    
    for i, cfg in enumerate(configs, 1):
        print(f"\n[Test {i}/{len(configs)}] Target=${cfg['target']:.2f}, "
              f"Stop=${cfg['stop']:.2f}, Trailing={cfg['trailing']}, "
              f"MaxLosses={cfg['max_losses']}")
        print("-" * 70)
        
        scalper = Crypto247Scalper(
            base_target=cfg['target'],
            base_stop=cfg['stop'],
            use_trailing=cfg['trailing'],
            max_consecutive_losses=cfg['max_losses']
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
        icon = '🎯' if r['win_rate'] >= 70 else ('✓' if r['win_rate'] >= 60 else '○')
        print(f"\n{i}. {icon} WR: {r['win_rate']:.1f}% | Trades: {r['total']} | "
              f"PF: {r['pf']:.2f} | Net: ${r['net']:+.2f}")
        print(f"   Target=${cfg['target']:.2f}, Stop=${cfg['stop']:.2f}, "
              f"Trail={cfg['trailing']}, MaxL={cfg['max_losses']}")
    
    print("\n" + "="*70 + "\n")
    
    if results and results[0]['win_rate'] >= 70:
        print("🎯 70%+ WIN RATE ACHIEVED!")
        with open('crypto_247_best.json', 'w') as f:
            json.dump(results[0], f, indent=2)
        print("Best config saved to: crypto_247_best.json\n")
    elif results and results[0]['win_rate'] >= 60:
        print(f"✓ Good result: {results[0]['win_rate']:.1f}% WR")
        print("  Recommendation: Collect more data to push toward 70%+\n")
    
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
    best = optimize_247(csv_path)
    
    if best:
        print("\n🚀 BEST CONFIGURATION:")
        print(f"   Win Rate: {best['win_rate']:.1f}%")
        print(f"   Trades: {best['total']}")
        print(f"   Net P&L: ${best['net']:+.2f}")
        print(f"   Config: {best['config']}")
        print()