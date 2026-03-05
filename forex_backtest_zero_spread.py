#!/usr/bin/env python3
"""
=============================================================================
BTC ZERO-SPREAD SCALPER — TREND FOLLOWING STRATEGY
=============================================================================
Optimized for Exness BTCUSD Zero Spread Account
• $100 Initial Balance
• Small Quick Profits ($0.50 - $2.00 per trade)
• Trend-Following Entry (EMA + RSI + Price Action)
• 80% Win Rate Target
• 1 Trade at a Time
• 24/7 Trading
"""

import csv
import json
from datetime import datetime
from collections import deque

# ============================================================================
# CONFIGURATION
# ============================================================================
class Config:
    INITIAL_BALANCE = 100.0
    RISK_PER_TRADE_PCT = 1.0          # Risk 1% = $1 per trade
    TARGET_PROFIT_PCT = 0.5           # Target 0.5% = $0.50 per trade
    STOP_LOSS_PCT = 0.25              # Stop 0.25% = $0.25 per trade
    MIN_PRICE_MOVE_TP = 30.0          # Minimum $30 price move for TP
    MAX_PRICE_MOVE_TP = 150.0         # Maximum $150 price move for TP
    COMMISSION_PCT = 0.0              # Zero spread account
    TICKS_PER_BAR = 20                # Aggregate 20 ticks per bar
    COOLDOWN_BARS = 2                 # Wait 2 bars after trade
    MIN_VOLATILITY = 20.0             # Minimum volatility to trade
    MAX_VOLATILITY = 300.0            # Maximum volatility to trade

# ============================================================================
# INDICATORS
# ============================================================================
class EMA:
    def __init__(self, period):
        self.period = period
        self.value = None
        self.alpha = 2 / (period + 1)
    
    def update(self, price):
        if self.value is None:
            self.value = price
        else:
            self.value = self.alpha * price + (1 - self.alpha) * self.value
        return self.value

class RSI:
    def __init__(self, period=14):
        self.period = period
        self.gains = deque(maxlen=period)
        self.losses = deque(maxlen=period)
        self.last = None
    
    def update(self, price):
        if self.last is not None:
            diff = price - self.last
            self.gains.append(max(0, diff))
            self.losses.append(max(0, -diff))
        self.last = price
        
        if len(self.gains) < self.period:
            return None
        
        avg_g = sum(self.gains) / len(self.gains)
        avg_l = sum(self.losses) / len(self.losses)
        
        if avg_l == 0:
            return 100
        
        rs = avg_g / avg_l
        return 100 - (100 / (1 + rs))

class Volatility:
    def __init__(self, period=20):
        self.period = period
        self.prices = deque(maxlen=period)
    
    def update(self, price):
        self.prices.append(price)
        if len(self.prices) < self.period:
            return 0
        return max(self.prices) - min(self.prices)

# ============================================================================
# TICK AGGREGATOR
# ============================================================================
class TickAggregator:
    def __init__(self, ticks_per_bar=20):
        self.window = ticks_per_bar
        self.buffer = []
    
    def update(self, price):
        self.buffer.append(price)
        if len(self.buffer) >= self.window:
            bar = {
                'open': self.buffer[0],
                'close': self.buffer[-1],
                'high': max(self.buffer),
                'low': min(self.buffer),
                'avg': sum(self.buffer) / len(self.buffer)
            }
            self.buffer = []
            return bar
        return None

# ============================================================================
# POSITION
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

# ============================================================================
# TRADING ENGINE
# ============================================================================
class TrendScalper:
    def __init__(self):
        self.ema_fast = EMA(9)
        self.ema_mid = EMA(21)
        self.ema_slow = EMA(50)
        self.rsi = RSI(14)
        self.volatility = Volatility(20)
        self.prices = deque(maxlen=50)
        self.cooldown = 0
        self.last_signal = None
    
    def get_trend(self):
        if None in [self.ema_fast.value, self.ema_mid.value, self.ema_slow.value]:
            return "NONE", 0
        
        if self.ema_fast.value > self.ema_mid.value > self.ema_slow.value:
            strength = (self.ema_fast.value - self.ema_slow.value) / self.ema_slow.value * 100
            return "UPTREND", strength
        elif self.ema_fast.value < self.ema_mid.value < self.ema_slow.value:
            strength = (self.ema_slow.value - self.ema_fast.value) / self.ema_slow.value * 100
            return "DOWNTREND", strength
        return "SIDEWAYS", 0
    
    def update(self, price):
        self.prices.append(price)
        
        ef = self.ema_fast.update(price)
        em = self.ema_mid.update(price)
        es = self.ema_slow.update(price)
        rsi = self.rsi.update(price)
        vol = self.volatility.update(price)
        
        if self.cooldown > 0:
            self.cooldown -= 1
            return "HOLD"
        
        if None in [ef, em, es, rsi] or len(self.prices) < 30:
            return "HOLD"
        
        # Check volatility filter
        if vol < Config.MIN_VOLATILITY or vol > Config.MAX_VOLATILITY:
            return "HOLD"
        
        trend, strength = self.get_trend()
        signal = "HOLD"
        
        # ── UPTREND ENTRY ──
        if trend == "UPTREND" and strength > 0.03:
            # Buy on pullback in uptrend
            if 35 < rsi < 60:
                # Price bouncing up
                if len(self.prices) >= 3 and self.prices[-1] > self.prices[-2]:
                    # Above mid EMA
                    if price > em:
                        signal = "BUY"
        
        # ── DOWNTREND ENTRY ──
        elif trend == "DOWNTREND" and strength > 0.03:
            # Sell on bounce in downtrend
            if 40 < rsi < 65:
                # Price bouncing down
                if len(self.prices) >= 3 and self.prices[-1] < self.prices[-2]:
                    # Below mid EMA
                    if price < em:
                        signal = "SELL"
        
        if signal != "HOLD":
            self.last_signal = signal
            self.cooldown = Config.COOLDOWN_BARS
        
        return signal

# ============================================================================
# ACCOUNT & EXECUTION
# ============================================================================
class Account:
    def __init__(self, balance=100.0):
        self.balance = balance
        self.initial = balance
        self.trades = []
    
    def calculate_lots(self, risk_pct, sl_distance, price):
        """Calculate lot size to risk exact percentage"""
        if sl_distance <= 0:
            return 0
        risk_amount = self.balance * (risk_pct / 100)
        lots = risk_amount / sl_distance
        # Cap leverage at 10x
        max_lots = (self.balance * 10) / price
        return min(lots, max_lots)
    
    def open_trade(self, direction, price, sl_dist, tp_dist, ts):
        entry = price
        sl = entry - sl_dist if direction == "BUY" else entry + sl_dist
        tp = entry + tp_dist if direction == "BUY" else entry - tp_dist
        
        lots = self.calculate_lots(Config.RISK_PER_TRADE_PCT, sl_dist, price)
        if lots <= 0:
            return None
        
        return Position(direction, entry, sl, tp, lots, ts)
    
    def check_exit(self, position, price):
        if position.direction == "BUY":
            if price <= position.sl:
                return True, "LOSS"
            if price >= position.tp:
                return True, "WIN"
        else:
            if price >= position.sl:
                return True, "LOSS"
            if price <= position.tp:
                return True, "WIN"
        return False, None
    
    def close_trade(self, position, exit_price, result):
        if position.direction == "BUY":
            pnl = (exit_price - position.entry) * position.lots
        else:
            pnl = (position.entry - exit_price) * position.lots
        
        pnl *= (1 - Config.COMMISSION_PCT / 100)
        
        position.close_price = exit_price
        position.pnl = pnl
        position.result = result
        self.balance += pnl
        self.trades.append(position)
        return pnl

# ============================================================================
# MAIN SCALPER
# ============================================================================
class BTCZeroSpreadScalper:
    def __init__(self, verbose=True):
        self.account = Account(Config.INITIAL_BALANCE)
        self.engine = TrendScalper()
        self.position = None
        self.verbose = verbose
    
    def run(self, csv_path):
        if self.verbose:
            print(f"{'='*70}")
            print(f"  BTC ZERO-SPREAD SCALPER — TREND FOLLOWING")
            print(f"{'='*70}")
            print(f"  Balance: ${Config.INITIAL_BALANCE:.2f}")
            print(f"  Risk: {Config.RISK_PER_TRADE_PCT}% | Target: {Config.TARGET_PROFIT_PCT}%")
            print(f"  TP Range: ${Config.MIN_PRICE_MOVE_TP}-${Config.MAX_PRICE_MOVE_TP}")
            print(f"{'='*70}\n")
        
        aggregator = TickAggregator(Config.TICKS_PER_BAR)
        tick_count = 0
        
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            
            for row in reader:
                if len(row) < 5:
                    continue
                
                try:
                    ts_str = row[2].strip('"')
                    price = float(row[3].strip('"'))
                    ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                except:
                    continue
                
                tick_count += 1
                
                # Check exit first (on every tick)
                if self.position:
                    hit, result = self.account.check_exit(self.position, price)
                    if hit:
                        pnl = self.account.close_trade(self.position, price, result)
                        if self.verbose:
                            icon = "✅" if result == "WIN" else "❌"
                            print(f"[{icon}] #{len(self.account.trades):3d} {result:4s} "
                                  f"PnL=${pnl:+.2f} Bal=${self.account.balance:.2f}")
                        self.position = None
                        continue
                
                # Aggregate ticks → bar
                bar = aggregator.update(price)
                if bar and not self.position:
                    signal = self.engine.update(bar['avg'])
                    
                    if signal != "HOLD":
                        # Calculate TP/SL based on volatility
                        vol = self.engine.volatility.update(bar['avg'])
                        sl_dist = max(30.0, min(100.0, vol * 0.5))
                        tp_dist = sl_dist * 2  # 1:2 Risk/Reward
                        tp_dist = max(Config.MIN_PRICE_MOVE_TP, 
                                     min(Config.MAX_PRICE_MOVE_TP, tp_dist))
                        
                        pos = self.account.open_trade(signal, bar['avg'], sl_dist, tp_dist, ts)
                        if pos:
                            self.position = pos
                            if self.verbose:
                                trend, strength = self.engine.get_trend()
                                rsi = self.engine.rsi.last
                                print(f"[OPEN] #{len(self.account.trades)+1:3d} {signal:4s} "
                                      f"@{pos.entry:,.2f} SL=${sl_dist:.0f} TP=${tp_dist:.0f} "
                                      f"Lots={pos.lots:.5f} Trend={trend} RSI={rsi:.1f}")
        
        # Force close remaining
        if self.position:
            pnl = self.account.close_trade(
                self.position, price,
                "WIN" if (self.position.direction == "BUY" and price > self.position.entry)
                       or (self.position.direction == "SELL" and price < self.position.entry)
                else "LOSS"
            )
            if self.verbose:
                print(f"[FORCE] #{len(self.account.trades):3d} PnL=${pnl:+.2f}")
        
        return self._report(tick_count)
    
    def _report(self, tick_count):
        total = len(self.account.trades)
        if total == 0:
            print("\n⚠️ No trades executed")
            return None
        
        wins = sum(1 for t in self.account.trades if t.result == "WIN")
        win_rate = wins / total * 100
        net = self.account.balance - self.account.initial
        gp = sum(t.pnl for t in self.account.trades if t.pnl > 0)
        gl = abs(sum(t.pnl for t in self.account.trades if t.pnl < 0))
        pf = gp / gl if gl > 0 else float('inf')
        
        # Max drawdown
        peak = self.account.initial
        max_dd = 0
        running = self.account.initial
        for t in self.account.trades:
            running += t.pnl
            if running > peak:
                peak = running
            dd = (peak - running) / peak * 100
            if dd > max_dd:
                max_dd = dd
        
        print(f"\n{'='*70}")
        print(f"  RESULTS — BTC ZERO-SPREAD SCALPER")
        print(f"{'='*70}")
        print(f"  Ticks Processed : {tick_count:,}")
        print(f"  Total Trades    : {total}")
        print(f"  Wins / Losses   : {wins} / {total-wins}")
        print(f"{'─'*70}")
        wr_icon = '🎯 80%+!' if win_rate >= 80 else ('✓ 70%+' if win_rate >= 70 else ('○ 60%+' if win_rate >= 60 else '✗'))
        print(f"  Win Rate        : {win_rate:.1f}% {wr_icon}")
        print(f"  Profit Factor   : {pf:.2f}")
        print(f"  Net P&L         : ${net:+.2f} ({net/self.account.initial*100:+.1f}%)")
        print(f"  Max Drawdown    : {max_dd:.2f}%")
        print(f"{'─'*70}")
        print(f"  Gross Profit    : ${gp:.2f}")
        print(f"  Gross Loss      : ${gl:.2f}")
        if wins > 0:
            print(f"  Avg Win         : ${gp/wins:.2f}")
        if total - wins > 0:
            print(f"  Avg Loss        : ${gl/(total-wins):.2f}")
        print(f"{'─'*70}")
        print(f"  Start Balance   : ${self.account.initial:.2f}")
        print(f"  Final Balance   : ${self.account.balance:.2f}")
        print(f"{'='*70}")
        
        return {
            'total': total, 'wins': wins, 'win_rate': win_rate,
            'pf': pf, 'net': net, 'balance': self.account.balance,
            'max_dd': max_dd
        }

# ============================================================================
# OPTIMIZER
# ============================================================================
def optimize_strategy(csv_path):
    print(f"\n{'='*70}")
    print("  STRATEGY OPTIMIZATION — FINDING BEST CONFIG")
    print(f"{'='*70}\n")
    
    configs = [
        {'risk': 1.0, 'tp_mult': 2.0, 'ticks': 20, 'name': 'Base 1% Risk, 1:2 RR'},
        {'risk': 0.5, 'tp_mult': 3.0, 'ticks': 15, 'name': 'Conservative 0.5% Risk, 1:3 RR'},
        {'risk': 1.5, 'tp_mult': 1.5, 'ticks': 25, 'name': 'Aggressive 1.5% Risk, 1:1.5 RR'},
        {'risk': 1.0, 'tp_mult': 1.0, 'ticks': 20, 'name': 'High WR 1:1 RR'},
        {'risk': 0.75, 'tp_mult': 2.5, 'ticks': 18, 'name': 'Balanced 0.75% Risk, 1:2.5 RR'},
    ]
    
    results = []
    for cfg in configs:
        print(f"Testing: {cfg['name']}")
        print("-" * 70)
        
        Config.RISK_PER_TRADE_PCT = cfg['risk']
        Config.TARGET_PROFIT_PCT = cfg['risk'] * cfg['tp_mult']
        Config.TICKS_PER_BAR = cfg['ticks']
        
        scalper = BTCZeroSpreadScalper(verbose=False)
        metrics = scalper.run(csv_path)
        
        if metrics:
            metrics['config'] = cfg
            results.append(metrics)
            print(f"→ Win Rate: {metrics['win_rate']:.1f}% | Net: ${metrics['net']:+.2f}\n")
    
    if results:
        results.sort(key=lambda x: x['win_rate'], reverse=True)
        
        print(f"{'='*70}")
        print("  RANKING BY WIN RATE")
        print(f"{'='*70}")
        for i, r in enumerate(results, 1):
            cfg = r['config']
            icon = '🎯' if r['win_rate'] >= 80 else '✓' if r['win_rate'] >= 70 else '○'
            print(f"{i}. {icon} {cfg['name']:<35} WR: {r['win_rate']:5.1f}% | Net: ${r['net']:+7.2f}")
        
        best = results[0]
        with open('best_scalper_config.json', 'w') as f:
            json.dump(best, f, indent=2)
        print(f"\n✅ Best config saved to: best_scalper_config.json")
        return best
    
    return None

# ============================================================================
# MAIN
# ============================================================================
if __name__ == '__main__':
    csv_file = "Exness_BTCUSD_Zero_Spread_2025_11_09.csv"
    
    import os
    if not os.path.exists(csv_file):
        print(f"❌ Error: {csv_file} not found!")
        exit(1)
    
    # Run optimization first
    best = optimize_strategy(csv_file)
    
    if best:
        print(f"\n{'='*70}")
        print("  🚀 RUNNING BEST CONFIG WITH FULL DETAILS")
        print(f"{'='*70}\n")
        
        Config.RISK_PER_TRADE_PCT = best['config']['risk']
        Config.TICKS_PER_BAR = best['config']['ticks']
        
        scalper = BTCZeroSpreadScalper(verbose=True)
        scalper.run(csv_file)