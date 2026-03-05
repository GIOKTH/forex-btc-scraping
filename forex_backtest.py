#!/usr/bin/env python3
"""
=============================================================================
 FOREX SCALPING BOT — TICK-DATA BACKTESTER  v2.0
=============================================================================
 Strategy derived from BTC bot analysis:
   v5  (btcusd_scalping_bot.txt)   — RSI + EMA core logic
   v14 (improved_scalping_bot.txt) — Smart analysis: EMA cross + RSI + ATR

 Enhanced for Forex / crypto with:
   • EMA(9) / EMA(21) crossover
   • RSI(14) extremes  (≤ 40 buy / ≥ 60 sell)
   • ATR(14) volatility gate  (adaptive — 0.05% of price)
   • MACD(12,26,9) histogram confirmation
   • Bollinger Band squeeze breakout filter
   • 2:1 Risk-Reward ratio   →  targets ≥ 80% win rate

 Usage:
   python3 forex_backtest.py [--csv PATH] [--tf 5] [--tp 2.0] [--sl 1.0]
=============================================================================
"""

import argparse, os, sys, math, csv, json, base64
from datetime import datetime, timezone
from collections import deque

HAS_MATPLOTLIB = False
try:
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt, matplotlib.dates as mdates
    HAS_MATPLOTLIB = True
except ImportError:
    pass

# ============================================================================
#  CONFIG / DEFAULTS
# ============================================================================
DEFAULT_CSV      = "Exness_BTCUSD_Zero_Spread_2025_11_09.csv"
DEFAULT_TF_MIN   = 5
INIT_BALANCE     = 10_000.0
RISK_PCT         = 1.0
MAX_DAILY_TRADES = 15
MAX_DAILY_LOSS_PCT = 5.0

# Indicator periods
EMA_FAST_P, EMA_SLOW_P = 9, 21
RSI_P = 14;  ATR_P = 14
MACD_FAST, MACD_SLOW, MACD_SIG = 12, 26, 9
BB_P = 20;   BB_MULT = 2.0

# Signal thresholds
RSI_BUY           = 42.0    # oversold
RSI_SELL          = 58.0    # overbought
RSI_NEUTRAL_LO    = 45.0
RSI_NEUTRAL_HI    = 55.0
ATR_MIN_PCT       = 0.05    # ATR must be ≥ 0.05% of price (adaptive)
TP_ATR_MULT       = 2.0     # TP = 2× ATR
SL_ATR_MULT       = 1.0     # SL = 1× ATR  →  RR = 2:1
MIN_BB_SQUEEZE    = 0.002   # BB width / mid must exceed this

# Lot sizing (treat as 0.01-lot contracts, $1 per pip, 1 pip = 1 USD on BTC)
LOT_FIXED         = 0.01    # Fixed micro-lot
PIP_VALUE_PER_LOT = 10.0    # $ per pip per lot (standard Forex)

# ============================================================================
#  INDICATORS  (all online, no libraries required)
# ============================================================================

class EMA:
    def __init__(self, period):
        self.p = period; self.k = 2/(period+1); self.v = None; self.n = 0
    def update(self, x):
        self.n += 1
        self.v = x if self.v is None else x*self.k + self.v*(1-self.k)
        return self.v if self.n >= self.p else None

class RSI:
    def __init__(self, period):
        self.p = period; self._prev = None; self._ag = None; self._al = None
        self._n = 0; self._bg = []; self._bl = []
    def update(self, x):
        if self._prev is None: self._prev = x; return None
        d = x - self._prev; self._prev = x
        g = max(d, 0.0); l = max(-d, 0.0); self._n += 1
        if self._n <= self.p:
            self._bg.append(g); self._bl.append(l)
            if self._n == self.p:
                self._ag = sum(self._bg)/self.p; self._al = sum(self._bl)/self.p
                rs = self._ag/(self._al if self._al > 0 else 1e-9)
                return 100 - 100/(1+rs)
            return None
        self._ag = (self._ag*(self.p-1)+g)/self.p
        self._al = (self._al*(self.p-1)+l)/self.p
        rs = self._ag/(self._al if self._al > 0 else 1e-9)
        return 100 - 100/(1+rs)

class ATR:
    def __init__(self, period):
        self.p = period; self._pc = None; self._a = None; self._n = 0; self._buf = []
    def update(self, h, l, c):
        if self._pc is None: self._pc = c; return None
        tr = max(h-l, abs(h-self._pc), abs(l-self._pc)); self._pc = c; self._n += 1
        if self._n <= self.p:
            self._buf.append(tr)
            if self._n == self.p: self._a = sum(self._buf)/self.p; return self._a
            return None
        self._a = (self._a*(self.p-1)+tr)/self.p; return self._a

class MACD:
    def __init__(self, fast=12, slow=26, sig=9):
        self._ef = EMA(fast); self._es = EMA(slow); self._eg = EMA(sig)
    def update(self, x):
        ef = self._ef.update(x); es = self._es.update(x)
        if ef is None or es is None: return None, None, None
        line = ef - es; sig = self._eg.update(line)
        if sig is None: return line, None, None
        return line, sig, line - sig

class BB:
    def __init__(self, period=20, mult=2.0):
        self.p = period; self.m = mult; self._buf = deque(maxlen=period)
    def update(self, x):
        self._buf.append(x)
        if len(self._buf) < self.p: return None, None, None
        mn = sum(self._buf)/self.p
        std = math.sqrt(sum((v-mn)**2 for v in self._buf)/self.p)
        return mn+self.m*std, mn, mn-self.m*std

# ============================================================================
#  CANDLE BUILDER
# ============================================================================

class CandleBuilder:
    def __init__(self, tf_minutes):
        self._tf = tf_minutes * 60; self._bar = None; self._cs = None; self.done = []
    def feed(self, ts_unix, price):
        bs = int(ts_unix // self._tf) * self._tf
        if self._cs is None:
            self._cs = bs; self._bar = [price, price, price, price, 1]; return None
        if bs != self._cs:
            c = {'o':self._bar[0], 'h':self._bar[1], 'l':self._bar[2],
                 'c':self._bar[3], 'v':self._bar[4],
                 'ts': datetime.fromtimestamp(self._cs, tz=timezone.utc)}
            self.done.append(c)
            self._cs = bs; self._bar = [price, price, price, price, 1]; return c
        if price > self._bar[1]: self._bar[1] = price
        if price < self._bar[2]: self._bar[2] = price
        self._bar[3] = price; self._bar[4] += 1; return None
    def flush(self):
        if self._bar:
            c = {'o':self._bar[0],'h':self._bar[1],'l':self._bar[2],
                 'c':self._bar[3],'v':self._bar[4],
                 'ts': datetime.fromtimestamp(self._cs, tz=timezone.utc)}
            self.done.append(c); self._bar = None; return c
        return None

# ============================================================================
#  SIGNAL ENGINE
# ============================================================================

class SignalEngine:
    def __init__(self):
        self.ema_fast = EMA(EMA_FAST_P); self.ema_slow = EMA(EMA_SLOW_P)
        self.rsi = RSI(RSI_P); self.atr = ATR(ATR_P)
        self.macd = MACD(MACD_FAST, MACD_SLOW, MACD_SIG); self.bb = BB(BB_P, BB_MULT)
        self._pef = None; self._pes = None; self._pmh = None; self._prsi = None
        self.state = {}

    def update(self, candle):
        c, h, lo = candle['c'], candle['h'], candle['l']
        ef = self.ema_fast.update(c); es = self.ema_slow.update(c)
        rv = self.rsi.update(c); av = self.atr.update(h, lo, c)
        ml, ms, mh = self.macd.update(c)
        bu, bm, bl = self.bb.update(c)

        self.state = dict(ema_fast=ef, ema_slow=es, rsi=rv, atr=av,
                          macd_hist=mh, bb_upper=bu, bb_mid=bm, bb_lower=bl, close=c)

        pef, pes, pmh, prsi = self._pef, self._pes, self._pmh, self._prsi

        if None in (ef, es, rv, av, mh, bm):
            self._update_prev(ef, es, mh, rv); return "HOLD"

        # ── ATR gate: adaptive volatility (% of price) ──────────────────
        if av / c * 100 < ATR_MIN_PCT:
            self._update_prev(ef, es, mh, rv); return "HOLD"

        # ── BB squeeze filter (only for Mode B) ─────────────────────────
        bb_ok = not (bm and (bu - bl)/bm < MIN_BB_SQUEEZE)

        # ── Crossover detection ─────────────────────────────────────────
        cross_bull = pef is not None and pes is not None and pef <= pes and ef > es
        cross_bear = pef is not None and pes is not None and pef >= pes and ef < es

        # ── MACD momentum ───────────────────────────────────────────────
        macd_rising  = pmh is not None and mh > pmh
        macd_falling = pmh is not None and mh < pmh
        macd_bull    = mh > 0
        macd_bear    = mh < 0

        # ── RSI momentum ────────────────────────────────────────────────
        rsi_rising  = prsi is not None and rv > prsi
        rsi_falling = prsi is not None and rv < prsi

        sig = "HOLD"

        # ── RSI Bounce strict: RSI ≤ 40 oversold, ≥ 60 overbought ─────────
        # Tight thresholds ensure only high-probability reversal signals
        if rv <= 40 and rsi_rising and macd_rising:
            sig = "BUY"
        # Sell when RSI overbought AND turning back down + MACD histogram falling
        elif rv >= 60 and rsi_falling and macd_falling:
            sig = "SELL"

        # ── MODE B: EMA Crossover (trend-following) ──────────────────────
        elif cross_bull and macd_bull and bb_ok:
            sig = "BUY"
        elif cross_bear and macd_bear and bb_ok:
            sig = "SELL"

        self._update_prev(ef, es, mh, rv); return sig

    def _update_prev(self, ef, es, mh, rv=None):
        self._pef = ef; self._pes = es; self._pmh = mh; self._prsi = rv

# ============================================================================
#  POSITION
# ============================================================================

class Position:
    def __init__(self, direction, entry, sl, tp, lots, ts, bar_idx):
        self.direction = direction; self.entry = entry
        self.sl = sl; self.tp = tp; self.lots = lots
        self.open_ts = ts; self.open_bar = bar_idx
        self.close_ts = None; self.close_price = None
        self.pnl = 0.0; self.result = None

# ============================================================================
#  BACKTESTER
# ============================================================================

class Backtester:
    def __init__(self, tf_minutes=DEFAULT_TF_MIN, init_balance=INIT_BALANCE,
                 tp_mult=TP_ATR_MULT, sl_mult=SL_ATR_MULT,
                 risk_pct=RISK_PCT, max_daily=MAX_DAILY_TRADES,
                 max_loss_pct=MAX_DAILY_LOSS_PCT):
        self.tf_min = tf_minutes; self.balance = init_balance
        self.init_balance = init_balance; self.tp_mult = tp_mult; self.sl_mult = sl_mult
        self.risk_pct = risk_pct; self.max_daily = max_daily; self.max_loss_pct = max_loss_pct

        self.engine   = SignalEngine()
        self.builder  = CandleBuilder(tf_minutes)
        self.position = None
        self.trades   = []
        self.equity   = []  # (datetime, balance)

        self._d_trades = 0; self._d_loss = 0.0
        self._cur_day  = None; self._bar_idx = 0

    # ── Main loop ─────────────────────────────────────────────────────────

    def run(self, csv_path):
        print(f"\n{'='*65}")
        print(f"  FOREX SCALPING BOT — TICK BACKTESTER  v2.0")
        print(f"{'='*65}")
        print(f"  File      : {os.path.basename(csv_path)}")
        print(f"  TF        : {self.tf_min}m  |  Balance: ${self.init_balance:,.0f}")
        print(f"  Strategy  : EMA({EMA_FAST_P}/{EMA_SLOW_P}) + RSI({RSI_P}) "
              f"+ ATR({ATR_P}) + MACD + BB")
        print(f"  TP/SL     : {self.tp_mult}×ATR / {self.sl_mult}×ATR  →  RR "
              f"= 1:{self.tp_mult/self.sl_mult:.1f}")
        print(f"{'='*65}\n")

        tick_count = 0
        last_bid   = 0.0
        last_ts    = None

        with open(csv_path, newline='', encoding='utf-8') as f:
            for row in csv.reader(f):
                if len(row) < 4: continue
                ts_raw = row[2].strip('"')
                if not ts_raw or not ts_raw[0].isdigit(): continue
                try:
                    ts  = datetime.fromisoformat(ts_raw.replace('Z', '+00:00'))
                    bid = float(row[3].strip('"'))
                except (ValueError, IndexError):
                    continue

                tick_count += 1
                last_bid = bid; last_ts = ts
                ts_unix  = ts.timestamp()

                # Always check SL/TP on every tick
                if self.position:
                    self._check_exit(bid, ts)

                # Always build candle
                candle = self.builder.feed(ts_unix, bid)
                if candle:
                    self._on_candle(candle)

        # Flush last candle
        last = self.builder.flush()
        if last: self._on_candle(last)

        # Force close any open position
        if self.position and last_bid and last_ts:
            self._force_close(last_bid, last_ts)

        return self._print_and_summary(tick_count)

    # ── Candle handler ────────────────────────────────────────────────────

    def _on_candle(self, candle):
        self._bar_idx += 1
        day = candle['ts'].date()
        if self._cur_day != day:
            if self._cur_day:
                print(f"\n── {self._cur_day} ──  Trades: {self._d_trades}  "
                      f"Daily loss: ${self._d_loss:.2f}\n")
            self._cur_day = day; self._d_trades = 0; self._d_loss = 0.0

        signal = self.engine.update(candle)

        if signal == "HOLD" or self.position: return
        if self._d_trades >= self.max_daily: return
        if self._d_loss >= self.init_balance * self.max_loss_pct / 100: return

        atr = self.engine.state.get('atr')
        if not atr: return

        self._open_trade(signal, candle['c'], atr, candle['ts'])

    # ── Trade management ──────────────────────────────────────────────────

    def _open_trade(self, direction, price, atr, ts):
        sl_d = atr * self.sl_mult; tp_d = atr * self.tp_mult
        sl   = price - sl_d if direction == 'BUY' else price + sl_d
        tp   = price + tp_d if direction == 'BUY' else price - tp_d

        # Risk-based lots: risk_amount / (sl_distance × pip_value)
        risk_amt = self.balance * self.risk_pct / 100
        lots     = max(0.01, round(risk_amt / (sl_d * PIP_VALUE_PER_LOT), 2))

        self.position = Position(direction, price, sl, tp, lots, ts, self._bar_idx)
        self._d_trades += 1

        rsi = self.engine.state.get('rsi', 0)
        print(f"  [OPEN  #{len(self.trades)+1:3d}] {direction} @ {price:.2f}  "
              f"SL={sl:.2f}  TP={tp:.2f}  Lots={lots:.2f}  "
              f"RSI={rsi:.1f}  {ts.strftime('%H:%M')}")

    def _check_exit(self, bid, ts):
        p  = self.position
        hit = None; ep = None
        if p.direction == 'BUY':
            if bid <= p.sl: hit='LOSS'; ep=p.sl
            elif bid >= p.tp: hit='WIN';  ep=p.tp
        else:
            if bid >= p.sl: hit='LOSS'; ep=p.sl
            elif bid <= p.tp: hit='WIN';  ep=p.tp
        if hit:
            self._close_trade(ep, ts, hit)

    def _close_trade(self, exit_price, ts, result):
        p = self.position
        diff = (exit_price - p.entry) if p.direction == 'BUY' else (p.entry - exit_price)
        pnl  = diff * p.lots * PIP_VALUE_PER_LOT

        p.close_ts = ts; p.close_price = exit_price; p.pnl = pnl; p.result = result
        self.balance += pnl
        if pnl < 0: self._d_loss += abs(pnl)

        self.trades.append(p)
        self.equity.append((ts, self.balance))
        self.position = None

        icon = '✓' if result == 'WIN' else '✗'
        print(f"  [{icon}{result:4s} #{len(self.trades):3d}] {p.direction}  "
              f"Exit={exit_price:.2f}  PnL=${pnl:+.2f}  "
              f"Bal=${self.balance:,.2f}  {ts.strftime('%H:%M')}")

    def _force_close(self, price, ts):
        p = self.position
        diff = (price - p.entry) if p.direction == 'BUY' else (p.entry - price)
        pnl  = diff * p.lots * PIP_VALUE_PER_LOT
        p.close_ts = ts; p.close_price = price; p.pnl = pnl
        p.result = 'WIN' if pnl >= 0 else 'LOSS'
        self.balance += pnl
        self.trades.append(p)
        self.equity.append((ts, self.balance))
        self.position = None
        print(f"  [FORCE #{len(self.trades):3d}] PnL=${pnl:+.2f}")

    # ── Results ───────────────────────────────────────────────────────────

    def _print_and_summary(self, tick_count):
        trades = self.trades; total = len(trades)
        wins   = sum(1 for t in trades if t.result == 'WIN')
        losses = total - wins
        wr     = wins/total*100 if total else 0
        gp     = sum(t.pnl for t in trades if t.pnl > 0)
        gl     = abs(sum(t.pnl for t in trades if t.pnl < 0))
        pf     = gp/gl if gl else float('inf')
        net    = self.balance - self.init_balance

        # Max drawdown
        peak = self.init_balance; mdd = 0.0; run = self.init_balance
        for t in trades:
            run += t.pnl
            if run > peak: peak = run
            dd = (peak-run)/peak*100
            if dd > mdd: mdd = dd

        aw = gp/wins   if wins   else 0
        al = gl/losses if losses else 0
        rr = aw/al     if al     else float('inf')

        TARGET = wr >= 80
        print(f"\n{'='*65}")
        print(f"  BACKTEST RESULTS — {self.tf_min}m  |  Tick data (40K ticks)")
        print(f"{'='*65}")
        print(f"  Ticks     : {tick_count:,}   Candles: {self._bar_idx:,}")
        print(f"  Total     : {total} trades  (Wins: {wins}  Losses: {losses})")
        print(f"{'─'*65}")
        print(f"  Win Rate  : {wr:.1f}%   {'✓ TARGET MET (≥80%)' if TARGET else '✗ Below 80%'}")
        print(f"  Profit Fac: {pf:.2f}")
        print(f"  Net P&L   : ${net:+,.2f}  ({net/self.init_balance*100:+.2f}%)")
        print(f"  Max DD    : {mdd:.2f}%")
        print(f"  Avg Win   : ${aw:.2f}   Avg Loss: ${al:.2f}   R:R 1:{rr:.2f}")
        print(f"  Balance   : ${self.balance:,.2f}")
        print(f"{'='*65}\n")

        return dict(total_trades=total, wins=wins, losses=losses, win_rate=wr,
                    profit_factor=pf, net_pnl=net, final_balance=self.balance,
                    max_drawdown=mdd, gross_profit=gp, gross_loss=gl,
                    avg_win=aw, avg_loss=al, rr=rr)

# ============================================================================
#  EXPORTS
# ============================================================================

def export_csv(trades, path):
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['#','Direction','OpenTime','CloseTime','Entry','Exit',
                    'Lots','PnL','Result'])
        for i, t in enumerate(trades, 1):
            w.writerow([i, t.direction,
                        t.open_ts.strftime('%Y-%m-%d %H:%M:%S'),
                        t.close_ts.strftime('%Y-%m-%d %H:%M:%S') if t.close_ts else '',
                        f'{t.entry:.5f}', f'{t.close_price:.5f}' if t.close_price else '',
                        f'{t.lots:.2f}', f'{t.pnl:.2f}', t.result])
    print(f"  Trade log   → {path}")

def plot_equity(equity, trades, path, init_bal):
    if not equity or not HAS_MATPLOTLIB:
        if not HAS_MATPLOTLIB:
            print("  (matplotlib not installed — skipping chart, pip3 install matplotlib)")
        return
    dates = [e[0] for e in equity]; vals = [e[1] for e in equity]
    fig, (ax1, ax2) = plt.subplots(2,1,figsize=(14,8),
                                   gridspec_kw={'height_ratios':[3,1]})
    fig.patch.set_facecolor('#0d1117')
    for ax in (ax1, ax2):
        ax.set_facecolor('#161b22'); ax.tick_params(colors='#c9d1d9')
        for sp in ax.spines.values(): sp.set_color('#30363d')
        ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    ax1.plot(dates, vals, color='#58a6ff', lw=1.5, label='Equity')
    ax1.axhline(init_bal, color='#6e7681', ls='--', lw=0.8,
                label=f'Start ${init_bal:,.0f}')
    ax1.fill_between(dates, init_bal, vals,
                     where=[v>=init_bal for v in vals], alpha=0.2, color='#3fb950')
    ax1.fill_between(dates, init_bal, vals,
                     where=[v<init_bal  for v in vals], alpha=0.2, color='#f85149')
    wr = sum(1 for t in trades if t.result=='WIN')/len(trades)*100 if trades else 0
    ax1.set_title(f"Forex Scalping Bot — Equity  |  Win Rate: {wr:.1f}%  |  "
                  f"Trades: {len(trades)}",
                  color='#e6edf3', fontsize=13, pad=12)
    ax1.set_ylabel('Balance ($)', color='#c9d1d9')
    ax1.legend(facecolor='#21262d', labelcolor='#c9d1d9', framealpha=0.7)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M')); fig.autofmt_xdate()
    pdates = [t.close_ts for t in trades if t.close_ts]
    pvals  = [t.pnl for t in trades if t.close_ts]
    cols   = ['#3fb950' if v>=0 else '#f85149' for v in pvals]
    ax2.bar(pdates, pvals, color=cols, width=0.003, alpha=0.8)
    ax2.axhline(0, color='#6e7681', lw=0.6)
    ax2.set_ylabel('Trade P&L ($)', color='#c9d1d9')
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close(); print(f"  Equity chart → {path}")

def generate_html(summary, trades, chart_path, out_path, tf):
    chart_b64 = ""
    if os.path.exists(chart_path):
        with open(chart_path, 'rb') as f:
            chart_b64 = base64.b64encode(f.read()).decode()
    img_tag = (f'<img src="data:image/png;base64,{chart_b64}" '
               f'style="width:100%;border-radius:8px;margin-top:16px;">'
               if chart_b64 else '')

    wr = summary['win_rate']; met = wr >= 80
    bc = '#3fb950' if met else '#f85149'; bt = '✓ TARGET MET' if met else '✗ Below Target'
    np_ = summary['net_pnl']; nc = '#3fb950' if np_ >= 0 else '#f85149'

    rows = ""
    for i,t in enumerate(trades, 1):
        c = '#3fb950' if t.result=='WIN' else '#f85149'
        rows += (f"<tr><td>{i}</td><td>{t.direction}</td>"
                 f"<td>{t.open_ts.strftime('%H:%M:%S')}</td>"
                 f"<td>{t.close_ts.strftime('%H:%M:%S') if t.close_ts else '-'}</td>"
                 f"<td>{t.entry:.2f}</td>"
                 f"<td>{'%.2f' % t.close_price if t.close_price else '-'}</td>"
                 f"<td style='color:{c};font-weight:600'>${t.pnl:+.2f}</td>"
                 f"<td style='color:{c}'>{t.result}</td></tr>")

    pf = summary.get('profit_factor', 0)
    pf_str = f"{pf:.2f}" if pf != float('inf') else "∞"
    dd  = summary.get('max_drawdown', 0)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Forex Scalping Bot — Backtest Report</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Inter',sans-serif;background:#0d1117;color:#e6edf3;padding:32px}}
h1{{font-size:26px;color:#58a6ff;margin-bottom:4px}}
.sub{{color:#8b949e;font-size:14px;margin-bottom:28px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:14px;margin-bottom:28px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:18px}}
.label{{font-size:11px;color:#8b949e;text-transform:uppercase;letter-spacing:.8px}}
.val{{font-size:26px;font-weight:700;margin-top:6px}}
.badge{{display:inline-block;margin-top:8px;padding:2px 10px;border-radius:12px;
        font-size:12px;font-weight:600;background:{bc}28;color:{bc}}}
.stitle{{font-size:16px;font-weight:600;margin:28px 0 12px;color:#c9d1d9}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{background:#161b22;padding:10px 12px;text-align:left;color:#8b949e;
    border-bottom:1px solid #30363d;font-weight:600;text-transform:uppercase;
    font-size:11px;letter-spacing:.6px}}
td{{padding:9px 12px;border-bottom:1px solid #21262d}}
tr:hover td{{background:#161b22}}
</style></head>
<body>
<h1>Forex Scalping Bot — Backtest Report</h1>
<p class="sub">Strategy: EMA(9/21) + RSI(14) + ATR(14) + MACD(12,26,9) + BB(20)
&nbsp;|&nbsp; TF: {tf}m candles &nbsp;|&nbsp; Source: tick CSV</p>
<div class="grid">
  <div class="card"><div class="label">Win Rate</div>
    <div class="val" style="color:{bc}">{wr:.1f}%</div>
    <span class="badge">{bt}</span></div>
  <div class="card"><div class="label">Total Trades</div>
    <div class="val">{summary['total_trades']}</div></div>
  <div class="card"><div class="label">Net P&amp;L</div>
    <div class="val" style="color:{nc}">${np_:+,.2f}</div></div>
  <div class="card"><div class="label">Profit Factor</div>
    <div class="val">{pf_str}</div></div>
  <div class="card"><div class="label">Max Drawdown</div>
    <div class="val" style="color:#f0883e">{dd:.2f}%</div></div>
  <div class="card"><div class="label">Final Balance</div>
    <div class="val">${summary['final_balance']:,.2f}</div></div>
</div>
{img_tag}
<div class="stitle">Trade Log</div>
<div style="overflow-x:auto">
<table><thead><tr>
  <th>#</th><th>Dir</th><th>Open</th><th>Close</th>
  <th>Entry</th><th>Exit</th><th>P&amp;L</th><th>Result</th>
</tr></thead><tbody>{rows}</tbody></table></div>
</body></html>"""

    with open(out_path, 'w', encoding='utf-8') as f: f.write(html)
    print(f"  HTML report → {out_path}")

# ============================================================================
#  MAIN
# ============================================================================

def main():
    ap = argparse.ArgumentParser(description="Forex Scalping Bot — Tick Backtester v2")
    ap.add_argument('--csv',    default=DEFAULT_CSV)
    ap.add_argument('--tf',     type=int,   default=DEFAULT_TF_MIN)
    ap.add_argument('--tp',     type=float, default=TP_ATR_MULT)
    ap.add_argument('--sl',     type=float, default=SL_ATR_MULT)
    ap.add_argument('--risk',   type=float, default=RISK_PCT)
    ap.add_argument('--balance',type=float, default=INIT_BALANCE)
    a = ap.parse_args()

    csv_path = a.csv if os.path.isabs(a.csv) else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), a.csv)
    if not os.path.exists(csv_path):
        print(f"ERROR: CSV not found: {csv_path}"); sys.exit(1)

    bt = Backtester(tf_minutes=a.tf, init_balance=a.balance,
                    tp_mult=a.tp, sl_mult=a.sl, risk_pct=a.risk)
    summary = bt.run(csv_path)

    base = os.path.dirname(csv_path)
    log   = os.path.join(base, 'backtest_trade_log.csv')
    chart = os.path.join(base, 'backtest_equity_curve.png')
    html  = os.path.join(base, 'forex_backtest_report.html')
    jpath = os.path.join(base, 'backtest_summary.json')

    export_csv(bt.trades, log)
    plot_equity(bt.equity, bt.trades, chart, bt.init_balance)
    generate_html(summary, bt.trades, chart, html, a.tf)
    with open(jpath, 'w') as f: json.dump(summary, f, indent=2)
    print(f"  Summary JSON → {jpath}\n")

    wr = summary['win_rate']
    if wr >= 80:
        print(f"  🎯 Win rate {wr:.1f}% — 80% TARGET ACHIEVED!")
    else:
        print(f"  ℹ️  Win rate {wr:.1f}% "
              f"({'Boost with: --tf 15 --tp 4 --sl 1.2' if wr < 70 else 'Just below target — try --tf 15'})")
    print()

if __name__ == '__main__':
    main()
