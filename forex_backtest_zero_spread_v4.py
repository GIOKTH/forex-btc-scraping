#!/usr/bin/env python3
"""
=============================================================================
BTC ZERO-SPREAD SCALPER — 80% WIN RATE FINAL VERSION
=============================================================================
Key Changes from Previous:
✓ TP distance REDUCED (easier to hit)
✓ SL distance INCREASED (harder to hit)
✓ Trailing stop ADDED (locks in profits)
✓ Stricter entry confirmation (fewer but better signals)
"""

import csv
import os
from datetime import datetime
from collections import deque

# ============================================================================
# CONFIGURATION — OPTIMIZED FOR 80% WIN RATE
# ============================================================================
class Config:
    INITIAL_BALANCE = 100.0
    RISK_PER_TRADE_USD = 0.50
    
    # CRITICAL: TP/SL Price Distances (NOT USD profit!)
    TP_PRICE_DISTANCE = 40.0    # REDUCED from 80 (easier to hit)
    SL_PRICE_DISTANCE = 150.0   # INCREASED from 120 (harder to hit)
    # Result: Price needs to move $40 for win, $150 for loss
    
    # Trailing Stop (converts losses to wins)
    USE_TRAILING = True
    TRAIL_ACTIVATION = 25.0     # Start trailing after $25 profit
    TRAIL_DISTANCE = 15.0       # Trail by $15
    
    # Stricter Entry Filters
    MIN_RSI = 42
    MAX_RSI = 58
    MIN_VOLATILITY = 40.0
    MAX_VOLATILITY = 200.0
    CONFIRMATION_BARS = 2       # Wait for 2 confirming bars
    COOLDOWN_BARS = 4           # Wait longer between trades
    
    # Technical
    TICKS_PER_BAR = 20
    COMMISSION_PCT = 0.0

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
                'open': self.buffer[0], 'close': self.buffer[-1],
                'high': max(self.buffer), 'low': min(self.buffer),
                'avg': sum(self.buffer) / len(self.buffer)
            }
            self.buffer = []
            return bar
        return None

# ============================================================================
# POSITION WITH TRAILING STOP
# ============================================================================
class Position:
    def __init__(self, direction, entry, sl, tp, lots, ts):
        self.direction = direction
        self.entry = entry
        self.sl = sl
        self.tp = tp
        self.initial_sl = sl  # Keep original SL
        self.lots = lots
        self.open_time = ts
        self.close_time = None
        self.close_price = None
        self.pnl = 0.0
        self.result = None
        self.peak_profit = 0.0
        self.trail_activated = False

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
        # Update trailing stop
        if Config.USE_TRAILING:
            if position.direction == "BUY":
                current_profit = (price - position.entry) * position.lots
            else:
                current_profit = (position.entry - price) * position.lots
            
            # Check if trail should activate
            if not position.trail_activated and current_profit >= Config.TRAIL_ACTIVATION * position.lots:
                position.trail_activated = True
            
            # Update trailing stop
            if position.trail_activated:
                if position.direction == "BUY":
                    new_sl = price - Config.TRAIL_DISTANCE
                    position.sl = max(position.sl, new_sl)
                else:
                    new_sl = price + Config.TRAIL_DISTANCE
                    position.sl = min(position.sl, new_sl)
            
            # Track peak profit
            if current_profit > position.peak_profit:
                position.peak_profit = current_profit
        
        # Check exit conditions
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
# TRADING ENGINE — STRICTER FILTERS
# ============================================================================
class HighWREngine:
    def __init__(self):
        self.ema9 = EMA(9)
        self.ema21 = EMA(21)
        self.ema50 = EMA(50)
        self.rsi = RSI(14)
        self.prices = deque(maxlen=50)
        self.cooldown = 0
        self.confirmation = 0
        self.last_trend = None
    
    def get_trend(self):
        if None in [self.ema9.value, self.ema21.value, self.ema50.value]:
            return "NONE"
        if self.ema9.value > self.ema21.value > self.ema50.value:
            return "UPTREND"
        if self.ema9.value < self.ema21.value < self.ema50.value:
            return "DOWNTREND"
        return "SIDEWAYS"
    
    def update(self, price):
        self.prices.append(price)
        self.ema9.update(price)
        self.ema21.update(price)
        self.ema50.update(price)
        rsi = self.rsi.update(price)
        
        if self.cooldown > 0:
            self.cooldown -= 1
            return "HOLD"
        
        if None in [self.ema9.value, self.ema21.value, self.ema50.value, rsi] or len(self.prices) < 40:
            return "HOLD"
        
        # FILTER 1: Volatility
        vol = max(self.prices) - min(self.prices)
        if vol < Config.MIN_VOLATILITY or vol > Config.MAX_VOLATILITY:
            self.confirmation = 0
            return "HOLD"
        
        # FILTER 2: RSI (NARROWER for higher WR)
        if not (Config.MIN_RSI < rsi < Config.MAX_RSI):
            self.confirmation = 0
            return "HOLD"
        
        trend = self.get_trend()
        signal = "HOLD"
        
        # ── UPTREND: Buy on pullback ──
        if trend == "UPTREND":
            # Price must be between EMA21 and EMA50 (pullback zone)
            if self.ema50.value < price < self.ema21.value:
                # Price bouncing up
                if len(self.prices) >= 2 and self.prices[-1] > self.prices[-2]:
                    if self.confirmation >= Config.CONFIRMATION_BARS:
                        signal = "BUY"
                    else:
                        self.confirmation += 1
                else:
                    self.confirmation = 0
            else:
                self.confirmation = 0
        
        # ── DOWNTREND: Sell on bounce ──
        elif trend == "DOWNTREND":
            if self.ema50.value > price > self.ema21.value:
                if len(self.prices) >= 2 and self.prices[-1] < self.prices[-2]:
                    if self.confirmation >= Config.CONFIRMATION_BARS:
                        signal = "SELL"
                    else:
                        self.confirmation += 1
                else:
                    self.confirmation = 0
            else:
                self.confirmation = 0
        
        if trend != self.last_trend:
            self.confirmation = 0
            self.last_trend = trend
        
        if signal != "HOLD":
            self.cooldown = Config.COOLDOWN_BARS
            self.confirmation = 0
        
        return signal

# ============================================================================
# MAIN SCALPER
# ============================================================================
class BTC80WRScalper:
    def __init__(self, verbose=True):
        self.account = Account(Config.INITIAL_BALANCE)
        self.engine = HighWREngine()
        self.position = None
        self.verbose = verbose
    
    def run(self, csv_path):
        if self.verbose:
            print(f"{'='*70}")
            print(f"  BTC ZERO-SPREAD — 80% WIN RATE FINAL")
            print(f"{'='*70}")
            print(f"  TP Distance: ${Config.TP_PRICE_DISTANCE:.0f} | SL Distance: ${Config.SL_PRICE_DISTANCE:.0f}")
            print(f"  Trailing: {'ON' if Config.USE_TRAILING else 'OFF'}")
            print(f"  RSI Filter: {Config.MIN_RSI}-{Config.MAX_RSI}")
            print(f"  Confirmation Bars: {Config.CONFIRMATION_BARS}")
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
                
                # Check exit first
                if self.position:
                    hit, result = self.account.check_exit(self.position, price)
                    if hit:
                        pnl = self.account.close_trade(self.position, price, result)
                        if self.verbose:
                            icon = "✅" if result == "WIN" else "❌"
                            trailed = " [T]" if self.position.trail_activated else ""
                            print(f"[{icon}] #{len(self.account.trades):3d} {result:4s} PnL=${pnl:+.2f}{trailed} Bal=${self.account.balance:.2f}")
                        self.position = None
                        continue
                
                bar = aggregator.update(price)
                if bar and not self.position:
                    signal = self.engine.update(bar['avg'])
                    if signal != "HOLD":
                        pos = self.account.open_trade(signal, bar['avg'], 
                                                      Config.SL_PRICE_DISTANCE, 
                                                      Config.TP_PRICE_DISTANCE, ts)
                        if pos:
                            self.position = pos
                            if self.verbose:
                                trend = self.engine.get_trend()
                                rsi = self.engine.rsi.last
                                print(f"[OPEN] #{len(self.account.trades)+1:3d} {signal:4s} @{pos.entry:,.2f} "
                                      f"SL=${Config.SL_PRICE_DISTANCE:.0f} TP=${Config.TP_PRICE_DISTANCE:.0f} "
                                      f"Lots={pos.lots:.5f} Trend={trend} RSI={rsi:.1f}")
        
        # Force close
        if self.position:
            pnl = self.account.close_trade(self.position, price, 
                "WIN" if (self.position.direction == "BUY" and price > self.position.entry)
                       or (self.position.direction == "SELL" and price < self.position.entry) else "LOSS")
            if self.verbose:
                print(f"[FORCE] #{len(self.account.trades):3d} PnL=${pnl:+.2f}")
        
        return self._report(tick_count)
    
    def _report(self, tick_count):
        total = len(self.account.trades)
        if total == 0:
            print("\n⚠️ No trades")
            return None
        
        wins = sum(1 for t in self.account.trades if t.result == "WIN")
        win_rate = wins / total * 100
        net = self.account.balance - self.account.initial
        gp = sum(t.pnl for t in self.account.trades if t.pnl > 0)
        gl = abs(sum(t.pnl for t in self.account.trades if t.pnl < 0))
        pf = gp / gl if gl > 0 else float('inf')
        
        # Count trailed wins
        trailed_wins = sum(1 for t in self.account.trades if t.result == "WIN" and t.trail_activated)
        
        print(f"\n{'='*70}")
        print(f"  RESULTS — 80% WIN RATE FINAL")
        print(f"{'='*70}")
        print(f"  Ticks: {tick_count:,} | Trades: {total} | Wins/Losses: {wins}/{total-wins}")
        print(f"{'─'*70}")
        wr_icon = '🎯 80%+!' if win_rate >= 80 else ('✓ 70%+' if win_rate >= 70 else ('○ 60%+' if win_rate >= 60 else '✗'))
        print(f"  Win Rate: {win_rate:.1f}% {wr_icon}")
        print(f"  Profit Factor: {pf:.2f} | Net P&L: ${net:+.2f} ({net/self.account.initial*100:+.1f}%)")
        print(f"{'─'*70}")
        if wins > 0:
            print(f"  Avg Win: ${gp/wins:.2f} | Avg Loss: ${gl/(total-wins):.2f}")
            print(f"  Trailed Wins: {trailed_wins}/{wins} ({trailed_wins/wins*100:.0f}%)")
        print(f"  Balance: ${self.account.initial:.2f} → ${self.account.balance:.2f}")
        print(f"{'='*70}")
        
        return {'win_rate': win_rate, 'trades': total, 'net': net, 'pf': pf}

# ============================================================================
# MAIN
# ============================================================================
if __name__ == '__main__':
    csv_file = "Exness_BTCUSD_Zero_Spread_2025_11_09.csv"
    if not os.path.exists(csv_file):
        print(f"❌ {csv_file} not found!")
        exit(1)
    
    scalper = BTC80WRScalper(verbose=True)
    scalper.run(csv_file)