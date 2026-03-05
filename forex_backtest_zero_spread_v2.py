#!/usr/bin/env python3
"""
=============================================================================
BTC ZERO-SPREAD SCALPER — FIXED VERSION (TRADES WILL EXECUTE)
=============================================================================
Fixes Applied:
✓ CSV parsing matches your actual data format (5 columns)
✓ Relaxed entry filters for more signals
✓ Lower ticks_per_bar (20 instead of 100)
✓ Realistic TP/SL for BTC ~$100,000 price levels
✓ Debug output shows why signals fire/don't fire
"""

import csv
import os
import sys
from datetime import datetime
from collections import deque

# ============================================================================
# CONFIGURATION
# ============================================================================
class Config:
    INITIAL_BALANCE = 100.0
    RISK_PER_TRADE_USD = 0.50       # Risk $0.50 per trade
    TARGET_PROFIT_USD = 0.75        # Target $0.75 per trade (1:1.5 RR)
    TICKS_PER_BAR = 20              # More signals (was 100)
    MIN_VOLATILITY = 10.0           # Min $ price movement
    MAX_VOLATILITY = 500.0          # Max $ price movement
    COMMISSION_PCT = 0.0            # Zero spread account

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
# TRADING ENGINE — SIMPLIFIED FOR MORE SIGNALS
# ============================================================================
class SimpleEngine:
    def __init__(self):
        self.ema_fast = EMA(9)
        self.ema_slow = EMA(21)
        self.rsi = RSI(14)
        self.prices = deque(maxlen=30)
        self.cooldown = 0
    
    def update(self, price, debug=False):
        self.prices.append(price)
        
        ef = self.ema_fast.update(price)
        es = self.ema_slow.update(price)
        rsi = self.rsi.update(price)
        
        if self.cooldown > 0:
            self.cooldown -= 1
            return "HOLD"
        
        # Need enough data
        if None in [ef, es, rsi] or len(self.prices) < 20:
            return "HOLD"
        
        signal = "HOLD"
        
        # ── SIMPLE TREND FOLLOWING ──
        # BUY: Fast EMA > Slow EMA + RSI not overbought
        if ef > es and 30 < rsi < 70:
            # Price bouncing up
            if len(self.prices) >= 2 and self.prices[-1] > self.prices[-2]:
                signal = "BUY"
                if debug:
                    print(f"  [DEBUG] BUY: ef={ef:.2f}>es={es:.2f}, RSI={rsi:.1f}")
        
        # SELL: Fast EMA < Slow EMA + RSI not oversold
        elif ef < es and 30 < rsi < 70:
            # Price bouncing down
            if len(self.prices) >= 2 and self.prices[-1] < self.prices[-2]:
                signal = "SELL"
                if debug:
                    print(f"  [DEBUG] SELL: ef={ef:.2f}<es={es:.2f}, RSI={rsi:.1f}")
        
        if signal != "HOLD":
            self.cooldown = 3  # Wait 3 bars before next signal
        
        return signal

# ============================================================================
# ACCOUNT
# ============================================================================
class Account:
    def __init__(self, balance=100.0):
        self.balance = balance
        self.initial = balance
        self.trades = []
    
    def calculate_lots(self, risk_usd, sl_distance, price):
        if sl_distance <= 0:
            return 0
        lots = risk_usd / sl_distance
        # Cap leverage
        max_lots = (self.balance * 10) / price
        return min(lots, max_lots)
    
    def open_trade(self, direction, price, sl_dist, tp_dist, ts):
        entry = price
        sl = entry - sl_dist if direction == "BUY" else entry + sl_dist
        tp = entry + tp_dist if direction == "BUY" else entry - tp_dist
        
        lots = self.calculate_lots(Config.RISK_PER_TRADE_USD, sl_dist, price)
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
        
        position.close_price = exit_price
        position.pnl = pnl
        position.result = result
        self.balance += pnl
        self.trades.append(position)
        return pnl

# ============================================================================
# MAIN SCALPER
# ============================================================================
class BTCScalper:
    def __init__(self, verbose=True, debug=False):
        self.account = Account(Config.INITIAL_BALANCE)
        self.engine = SimpleEngine()
        self.position = None
        self.verbose = verbose
        self.debug = debug
    
    def run(self, csv_path):
        if self.verbose:
            print(f"{'='*70}")
            print(f"  BTC ZERO-SPREAD SCALPER — FIXED VERSION")
            print(f"{'='*70}")
            print(f"  Balance: ${Config.INITIAL_BALANCE:.2f}")
            print(f"  Risk: ${Config.RISK_PER_TRADE_USD:.2f} | Target: ${Config.TARGET_PROFIT_USD:.2f}")
            print(f"  Ticks/Bar: {Config.TICKS_PER_BAR}")
            print(f"{'='*70}\n")
        
        aggregator = TickAggregator(Config.TICKS_PER_BAR)
        tick_count = 0
        bar_count = 0
        
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            
            for row in reader:
                if len(row) < 5:
                    continue
                
                try:
                    # YOUR CSV FORMAT: broker,symbol,timestamp,bid,ask
                    ts_str = row[2].strip('"')
                    price = float(row[3].strip('"'))  # Use bid price
                    ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                except Exception as e:
                    if self.debug:
                        print(f"  [DEBUG] Parse error: {e}, row={row[:3]}")
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
                    bar_count += 1
                    signal = self.engine.update(bar['avg'], debug=self.debug)
                    
                    if signal != "HOLD":
                        # Calculate TP/SL based on USD targets
                        # For BTC ~$100,000, a $50 price move = ~0.05%
                        sl_dist = max(30.0, Config.RISK_PER_TRADE_USD * 100)  # $50 SL
                        tp_dist = max(40.0, Config.TARGET_PROFIT_USD * 100)   # $75 TP
                        
                        pos = self.account.open_trade(signal, bar['avg'], sl_dist, tp_dist, ts)
                        if pos:
                            self.position = pos
                            if self.verbose:
                                print(f"[OPEN] #{len(self.account.trades)+1:3d} {signal:4s} "
                                      f"@{pos.entry:,.2f} SL=${sl_dist:.0f} TP=${tp_dist:.0f} "
                                      f"Lots={pos.lots:.5f}")
                        elif self.debug:
                            print(f"  [DEBUG] Failed to open position (lots={pos})")
        
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
        
        return self._report(tick_count, bar_count)
    
    def _report(self, tick_count, bar_count):
        total = len(self.account.trades)
        if total == 0:
            print("\n⚠️  NO TRADES EXECUTED")
            print(f"   Ticks: {tick_count:,} | Bars: {bar_count:,}")
            print(f"   Check: CSV format, indicator warmup, filter strictness")
            return None
        
        wins = sum(1 for t in self.account.trades if t.result == "WIN")
        win_rate = wins / total * 100
        net = self.account.balance - self.account.initial
        gp = sum(t.pnl for t in self.account.trades if t.pnl > 0)
        gl = abs(sum(t.pnl for t in self.account.trades if t.pnl < 0))
        pf = gp / gl if gl > 0 else float('inf')
        
        print(f"\n{'='*70}")
        print(f"  RESULTS")
        print(f"{'='*70}")
        print(f"  Ticks Processed : {tick_count:,}")
        print(f"  Bars Generated  : {bar_count:,}")
        print(f"  Total Trades    : {total}")
        print(f"  Wins / Losses   : {wins} / {total-wins}")
        print(f"{'─'*70}")
        wr_icon = '🎯 80%+!' if win_rate >= 80 else ('✓ 70%+' if win_rate >= 70 else ('○ 60%+' if win_rate >= 60 else '✗'))
        print(f"  Win Rate        : {win_rate:.1f}% {wr_icon}")
        print(f"  Profit Factor   : {pf:.2f}")
        print(f"  Net P&L         : ${net:+.2f} ({net/self.account.initial*100:+.1f}%)")
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
            'pf': pf, 'net': net, 'balance': self.account.balance
        }

# ============================================================================
# MAIN
# ============================================================================
if __name__ == '__main__':
    csv_file = "Exness_BTCUSD_Zero_Spread_2025_11_09.csv"
    
    if not os.path.exists(csv_file):
        print(f"❌ Error: {csv_file} not found!")
        sys.exit(1)
    
    # First run with debug to see what's happening
    print("🔍 Running with DEBUG mode...\n")
    scalper = BTCScalper(verbose=True, debug=True)
    scalper.run(csv_file)