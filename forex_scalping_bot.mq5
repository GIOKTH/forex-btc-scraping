//+------------------------------------------------------------------+
//|                     ForexScalpingBot.mq5                        |
//|         FOREX SCALPING EA — Ported from BTC Bot Analysis        |
//|                                                                  |
//|  Strategy:  EMA(9/21) Cross + RSI(14) + ATR(14) +               |
//|             MACD(12,26,9) + Bollinger Bands(20,2)               |
//|                                                                  |
//|  Derived from:                                                   |
//|   v5  (btcusd_scalping_bot.txt)   — RSI + EMA core              |
//|   v14 (improved_scalping_bot.txt) — Smart analysis + ATR        |
//|                                                                  |
//|  Risk model: ATR-based SL/TP (2:1 RR), 1% risk per trade       |
//+------------------------------------------------------------------+
#property copyright  "Forex Scalping Bot — v1.0"
#property version    "1.00"
#property description "Multi-indicator Forex scalper targeting ≥80% win rate"

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

//==========================================================================
//  INPUT PARAMETERS
//==========================================================================

input group "=== SYMBOL & TIMEFRAME ==="
input string   InpSymbol        = "";           // Symbol (blank = chart symbol)
input ENUM_TIMEFRAMES InpTF     = PERIOD_M5;   // Timeframe

input group "=== INDICATORS ==="
input int      InpEmaFast       = 9;            // EMA Fast period
input int      InpEmaSlow       = 21;           // EMA Slow period
input int      InpRsiPeriod     = 14;           // RSI period
input int      InpAtrPeriod     = 14;           // ATR period
input int      InpMacdFast      = 12;           // MACD fast EMA
input int      InpMacdSlow      = 26;           // MACD slow EMA
input int      InpMacdSignal    = 9;            // MACD signal period
input int      InpBbPeriod      = 20;           // Bollinger Bands period
input double   InpBbMult        = 2.0;          // Bollinger Bands deviation

input group "=== ENTRY THRESHOLDS ==="
input double   InpRsiBuy        = 40.0;         // RSI buy level (oversold ≤)
input double   InpRsiSell       = 60.0;         // RSI sell level (overbought ≥)
input double   InpRsiNeutralLo  = 45.0;         // RSI neutral zone low
input double   InpRsiNeutralHi  = 55.0;         // RSI neutral zone high
input double   InpAtrMinPips    = 5.0;          // Min ATR in normalised pips
input double   InpBbMinWidth    = 0.0005;       // Min BB width (squeeze filter)

input group "=== RISK MANAGEMENT ==="
input double   InpRiskPct       = 1.0;          // Risk % per trade
input double   InpTpAtrMult     = 2.0;          // TP = TpAtrMult × ATR
input double   InpSlAtrMult     = 1.0;          // SL = SlAtrMult × ATR  (RR = 2:1)
input int      InpMaxDailyTrades = 15;          // Max trades per day
input double   InpMaxDailyLossPct = 5.0;        // Max daily loss % of balance

input group "=== GENERAL ==="
input int      InpMagic         = 777999;       // Magic number
input bool     InpEnableLog     = true;         // Detailed logging
input int      InpSlippage      = 20;           // Allowed slippage (points)

input group "=== SCALP MODE ==="
input bool     InpScalpMode     = true;         // Enable scalp mode (fixed $$ target)
input double   InpScalpLots     = 0.01;         // Fixed lot size
input double   InpScalpTarget   = 1.00;         // Profit target ($)
input double   InpScalpStop     = 0.50;         // Stop loss ($)
input bool     InpScalpTrendFilter = true;      // Only trade with EMA-50 major trend
input int      InpScalpCooldown = 3;            // Bars to skip after a loss
input int      InpEmaTrend      = 50;           // Trend filter EMA period

//==========================================================================
//  GLOBALS
//==========================================================================

CTrade        trade;
CPositionInfo pos;
string        sym;

// Indicator handles
int  hEmaFast, hEmaSlow, hRsi, hAtr, hMacd, hBb, hEmaTrend;

// State
bool   inPosition      = false;
int    dailyTrades     = 0;
double dailyLoss       = 0.0;
bool   dailyLimitHit   = false;
datetime currentDay    = 0;
int    totalTrades     = 0;
double totalPnl        = 0.0;

// Previous bar values for dual-mode signal tracking
double prevEmaFast = 0, prevEmaSlow = 0, prevMacdHist = 0, prevRsi = 0;
bool   prevReady = false;

// Scalp mode state
int    scalpCooldownBars = 0;    // remaining cooldown bars after a loss
string lastTradeResult   = "";   // "WIN" or "LOSS"

//==========================================================================
//  INIT / DEINIT
//==========================================================================

int OnInit()
{
    sym = (InpSymbol == "") ? _Symbol : InpSymbol;

    Print("╔════════════════════════════════════════════╗");
    Print("║  FOREX SCALPING BOT  v1.0  —  STARTED      ║");
    Print("╚════════════════════════════════════════════╝");
    Print("Symbol    : ", sym);
    Print("Timeframe : ", EnumToString(InpTF));
    Print("Risk/Trade: ", InpRiskPct, "%   TP:", InpTpAtrMult, "×ATR  SL:", InpSlAtrMult, "×ATR");
    Print("Max daily trades: ", InpMaxDailyTrades);

    if(!SymbolSelect(sym, true))
    {
        Print("ERROR: Cannot select symbol ", sym);
        return INIT_FAILED;
    }

    // Create indicator handles
    hEmaFast = iMA(sym, InpTF, InpEmaFast, 0, MODE_EMA, PRICE_CLOSE);
    hEmaSlow = iMA(sym, InpTF, InpEmaSlow, 0, MODE_EMA, PRICE_CLOSE);
    hEmaTrend= iMA(sym, InpTF, InpEmaTrend,0, MODE_EMA, PRICE_CLOSE);
    hRsi     = iRSI(sym, InpTF, InpRsiPeriod, PRICE_CLOSE);
    hAtr     = iATR(sym, InpTF, InpAtrPeriod);
    hMacd    = iMACD(sym, InpTF, InpMacdFast, InpMacdSlow, InpMacdSignal, PRICE_CLOSE);
    hBb      = iBands(sym, InpTF, InpBbPeriod, 0, InpBbMult, PRICE_CLOSE);

    if(hEmaFast == INVALID_HANDLE || hEmaSlow == INVALID_HANDLE ||
       hEmaTrend== INVALID_HANDLE || hRsi == INVALID_HANDLE     ||
       hAtr == INVALID_HANDLE    || hMacd == INVALID_HANDLE     ||
       hBb == INVALID_HANDLE)
    {
        Print("ERROR: Failed to create indicator handles");
        return INIT_FAILED;
    }

    // Trade setup
    trade.SetExpertMagicNumber(InpMagic);
    trade.SetMarginMode();
    trade.SetTypeFillingBySymbol(sym);
    trade.SetDeviationInPoints(InpSlippage);

    // Init day tracking
    currentDay = TimeCurrent();
    dailyTrades = 0;
    dailyLoss   = 0.0;

    Print("Bot initialised successfully. Waiting for signals...");
    return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
    Print("╔════════════════════════════════════════════╗");
    Print("║  FOREX SCALPING BOT — STOPPED               ║");
    Print("╚════════════════════════════════════════════╝");
    Print("Total Trades : ", totalTrades);
    Print("Total P&L    : $", NormalizeDouble(totalPnl, 2));

    if(hEmaFast != INVALID_HANDLE) IndicatorRelease(hEmaFast);
    if(hEmaSlow != INVALID_HANDLE) IndicatorRelease(hEmaSlow);
    if(hRsi     != INVALID_HANDLE) IndicatorRelease(hRsi);
    if(hAtr     != INVALID_HANDLE) IndicatorRelease(hAtr);
    if(hMacd    != INVALID_HANDLE) IndicatorRelease(hMacd);
    if(hBb      != INVALID_HANDLE) IndicatorRelease(hBb);
}

//==========================================================================
//  MAIN TICK
//==========================================================================

void OnTick()
{
    // 1. Day reset
    CheckNewDay();

    // 2. Safety limits
    if(dailyLimitHit) return;
    if(!CheckDailyLimits()) return;

    // 3. Update position status
    UpdatePosition();

    // 4. Manage open position
    if(inPosition)
    {
        ManagePosition();
        return;
    }

    // 5. Only trade on new bar
    if(!IsNewBar()) return;

    // 6. Analyse market and trade
    AnalyseAndTrade();
}

//==========================================================================
//  NEW BAR DETECTION
//==========================================================================

bool IsNewBar()
{
    static datetime lastBar = 0;
    datetime current = iTime(sym, InpTF, 0);
    if(current != lastBar)
    {
        lastBar = current;
        return true;
    }
    return false;
}

//==========================================================================
//  DAY TRACKING
//==========================================================================

void CheckNewDay()
{
    MqlDateTime now, cur;
    TimeToStruct(TimeCurrent(), now);
    TimeToStruct(currentDay, cur);

    if(now.day != cur.day || now.mon != cur.mon || now.year != cur.year)
    {
        Print("══ NEW DAY ══  Previous: ", dailyTrades, " trades  Loss: $",
              NormalizeDouble(dailyLoss, 2));
        dailyTrades   = 0;
        dailyLoss     = 0.0;
        dailyLimitHit = false;
        currentDay    = TimeCurrent();
        prevReady    = false;
    }
}

bool CheckDailyLimits()
{
    if(dailyTrades >= InpMaxDailyTrades)
    {
        if(InpEnableLog) Print("Daily trade limit reached (", dailyTrades, ")");
        dailyLimitHit = true;
        return false;
    }
    double maxLoss = AccountInfoDouble(ACCOUNT_BALANCE) * InpMaxDailyLossPct / 100.0;
    if(dailyLoss >= maxLoss)
    {
        Print("DAILY LOSS LIMIT HIT: $", NormalizeDouble(dailyLoss, 2),
              " / $", NormalizeDouble(maxLoss, 2));
        dailyLimitHit = true;
        return false;
    }
    return true;
}

//==========================================================================
//  POSITION TRACKING
//==========================================================================

void UpdatePosition()
{
    inPosition = false;
    for(int i = 0; i < PositionsTotal(); i++)
    {
        if(pos.SelectByIndex(i))
        {
            if(pos.Symbol() == sym && pos.Magic() == InpMagic)
            {
                inPosition = true;
                break;
            }
        }
    }
}

//==========================================================================
//  POSITION MANAGEMENT  (manual SL/TP monitoring)
//==========================================================================

void ManagePosition()
{
    if(!pos.Select(sym)) return;

    double profit = pos.Profit() + pos.Swap() + pos.Commission();
    string type   = (pos.PositionType() == POSITION_TYPE_BUY) ? "BUY" : "SELL";

    // Let MT5 handle the built-in SL/TP — just log
    if(InpEnableLog)
    {
        static datetime lastLog = 0;
        if(TimeCurrent() - lastLog > 60)
        {
            Print("Position (", type, ") P&L: $", NormalizeDouble(profit, 2));
            lastLog = TimeCurrent();
        }
    }
}

//==========================================================================
//  READ INDICATOR VALUES
//==========================================================================

double GetBuffer(int handle, int bufIdx, int shift = 1)
{
    double buf[1];
    if(CopyBuffer(handle, bufIdx, shift, 1, buf) <= 0)
        return 0.0;
    return buf[0];
}

bool ReadIndicators(double &emaFast, double &emaSlow, double &emaTrend, double &rsi,
                    double &atr,     double &macdHist,
                    double &bbUpper, double &bbMid, double &bbLower)
{
    emaFast  = GetBuffer(hEmaFast, 0);
    emaSlow  = GetBuffer(hEmaSlow, 0);
    emaTrend = GetBuffer(hEmaTrend, 0);
    rsi      = GetBuffer(hRsi,     0);
    atr      = GetBuffer(hAtr,     0);
    macdHist = GetBuffer(hMacd,    2);  // Histogram buffer = index 2
    bbUpper  = GetBuffer(hBb,      1);
    bbMid    = GetBuffer(hBb,      0);
    bbLower  = GetBuffer(hBb,      2);

    return (emaFast > 0 && emaSlow > 0 && emaTrend > 0 && rsi > 0 && atr > 0 &&
            bbUpper > 0 && bbMid > 0);
}

//==========================================================================
//  MAIN SIGNAL LOGIC
//==========================================================================

void AnalyseAndTrade()
{
    double emaFast, emaSlow, emaTrend, rsi, atr, macdHist;
    double bbUpper, bbMid, bbLower;

    if(!ReadIndicators(emaFast, emaSlow, emaTrend, rsi, atr, macdHist,
                       bbUpper, bbMid, bbLower))
    {
        if(InpEnableLog) Print("Waiting for indicators to warm up...");
        return;
    }

    // ────── FILTER 1: ATR volatility gate ──────────────────────────────
    double price = SymbolInfoDouble(sym, SYMBOL_BID);
    double atrPips = (price > 0) ? (atr / price * 10000.0) : 0;
    if(atrPips < InpAtrMinPips)
    {
        if(InpEnableLog) Print("ATR too low (", NormalizeDouble(atrPips,2), " pips) — skip");
        prevReady    = true;
        prevEmaFast  = emaFast;
        prevEmaSlow  = emaSlow;
        prevMacdHist = macdHist;
        prevRsi      = rsi;
    }

    // ────── FILTER 2: RSI neutral zone removed for RSI Bounce mode ────
    // (RSI Bounce mode allows any RSI extreme; no neutral filter needed)

    // ────── FILTER 3: Bollinger Band squeeze ───────────────────────────
    double bbWidth = (bbMid > 0) ? (bbUpper - bbLower) / bbMid : 0;
    bool bbOk = (bbWidth >= InpBbMinWidth);
    if(!bbOk && InpEnableLog)
        Print("BB squeeze (width=", NormalizeDouble(bbWidth,5), ") — Mode B suppressed");

    // ────── EMA crossover detection ────────────────────────────────────
    bool emaCrossBull = (prevValuesReady &&
                         prevEmaFast <= prevEmaSlow &&
                         emaFast >  emaSlow);
    bool emaCrossBear = (prevValuesReady &&
                         prevEmaFast >= prevEmaSlow &&
                         emaFast <  emaSlow);

    bool emaBullish  = (emaFast > emaSlow);
    bool emaBearish  = (emaFast < emaSlow);

    // ────── SCALP MODE GUARDS ──────────────────────────────────────────
    if(InpScalpMode)
    {
        if(scalpCooldownBars > 0)
        {
            scalpCooldownBars--;
            if(InpEnableLog) Print("Scalp cooldown active: ", scalpCooldownBars, " bars left");
            return;
        }
    }

    // ────── MACD momentum ──────────────────────────────────────────────
    bool macdBull = (macdHist > 0 && (!prevReady || macdHist > prevMacdHist));
    bool macdBear = (macdHist < 0 && (!prevReady || macdHist < prevMacdHist));

    // ────── SIGNAL LOGIC ───────────────────────────────────────────────
    bool buySignal  = false;
    bool sellSignal = false;
    string reason   = "";

    // ── MACD momentum ──────────────────────────────────────────────
    bool macdRising  = prevReady && (macdHist > prevMacdHist);
    bool macdFalling = prevReady && (macdHist < prevMacdHist);
    bool rsiRising   = prevReady && (rsi > prevRsi);
    bool rsiFalling  = prevReady && (rsi < prevRsi);

    // ── MODE A: RSI Bounce (high-probability reversal) ───────────────
    if(rsi <= InpRsiBuy && rsiRising && macdRising)
    {
        buySignal = true;
        reason    = StringFormat("RSI_Bounce_Buy=%.1f", rsi);
    }
    else if(rsi >= InpRsiSell && rsiFalling && macdFalling)
    {
        sellSignal = true;
        reason     = StringFormat("RSI_Bounce_Sell=%.1f", rsi);
    }
    // ── MODE B: EMA Crossover (trend-following, requires BB expansion) ─
    else if(bbOk)
    {
        bool emaCrossBull = prevReady && (prevEmaFast <= prevEmaSlow) && (emaFast > emaSlow);
        bool emaCrossBear = prevReady && (prevEmaFast >= prevEmaSlow) && (emaFast < emaSlow);
        if(emaCrossBull && macdHist > 0)
        {
            buySignal = true;
            reason    = StringFormat("EMA_Cross_Bull RSI=%.1f", rsi);
        }
        else if(emaCrossBear && macdHist < 0)
        {
            sellSignal = true;
            reason     = StringFormat("EMA_Cross_Bear RSI=%.1f", rsi);
        }
    }

    // ── SCALP MODE TREND FILTER ───────────────────────────────────────
    if(InpScalpMode && InpScalpTrendFilter)
    {
        double close = iClose(sym, InpTF, 0);
        if(buySignal  && close < emaTrend) { buySignal  = false; if(InpEnableLog) Print("Scalp BUY blocked by EMA-50 trend"); }
        if(sellSignal && close > emaTrend) { sellSignal = false; if(InpEnableLog) Print("Scalp SELL blocked by EMA-50 trend"); }
    }

    // Store prev values
    prevEmaFast  = emaFast;
    prevEmaSlow  = emaSlow;
    prevMacdHist = macdHist;
    prevRsi      = rsi;
    prevReady    = true;

    // ────── EXECUTE ────────────────────────────────────────────────────
    if(buySignal)
    {
        PrintQualitySetup("BUY", reason, rsi, atr, emaFast, emaSlow);
        OpenTrade(ORDER_TYPE_BUY, atr, reason);
    }
    else if(sellSignal)
    {
        PrintQualitySetup("SELL", reason, rsi, atr, emaFast, emaSlow);
        OpenTrade(ORDER_TYPE_SELL, atr, reason);
    }
}

//==========================================================================
//  TRADE EXECUTION
//==========================================================================

void OpenTrade(ENUM_ORDER_TYPE orderType, double atr, string reason)
{
    double balance  = AccountInfoDouble(ACCOUNT_BALANCE);
    double pipSize  = SymbolInfoDouble(sym, SYMBOL_POINT) * 10; // 1 pip
    if(pipSize == 0) pipSize = 0.0001;

    double slDist, tpDist, lots;

    if(InpScalpMode)
    {
        lots = InpScalpLots;
        // Calculate price distance for fixed dollar profit/stop
        // Profit = (PriceDiff / TickSize) * TickValue * Lots
        double tickSize  = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
        double tickValue = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE);
        
        if(tickValue > 0 && lots > 0)
        {
            tpDist = (InpScalpTarget * tickSize) / (tickValue * lots);
            slDist = (InpScalpStop   * tickSize) / (tickValue * lots);
        }
        else
        {
            slDist = atr * InpSlAtrMult;
            tpDist = atr * InpTpAtrMult;
        }
    }
    else
    {
        slDist = atr * InpSlAtrMult;
        tpDist = atr * InpTpAtrMult;

        // Risk-based lot sizing
        double riskAmt  = balance * InpRiskPct / 100.0;
        double slPips   = slDist / pipSize;
        double pipVal   = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE) /
                          SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE) * pipSize;
        lots = (pipVal > 0 && slPips > 0) ? (riskAmt / (slPips * pipVal)) : 0.01;
    }

    // Clamp to symbol limits
    double minLot  = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
    double maxLot  = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
    double lotStep = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
    lots = MathMax(lots, minLot);
    lots = MathMin(lots, maxLot);
    lots = MathFloor(lots / lotStep) * lotStep;
    lots = NormalizeDouble(lots, 2);

    // Prices
    bool   isBuy = (orderType == ORDER_TYPE_BUY);
    double entry = isBuy ? SymbolInfoDouble(sym, SYMBOL_ASK)
                         : SymbolInfoDouble(sym, SYMBOL_BID);

    // Minimum stop distance
    int    minStop = (int)SymbolInfoInteger(sym, SYMBOL_TRADE_STOPS_LEVEL);
    double minDist = minStop * SymbolInfoDouble(sym, SYMBOL_POINT);
    if(slDist < minDist) slDist = minDist * 1.2;
    if(tpDist < minDist) tpDist = minDist * 2.5;

    double sl = isBuy ? entry - slDist : entry + slDist;
    double tp = isBuy ? entry + tpDist : entry - tpDist;

    int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
    sl = NormalizeDouble(sl, digits);
    tp = NormalizeDouble(tp, digits);

    string comment = "FSB_" + reason;
    bool   success = false;

    if(isBuy)
        success = trade.Buy(lots, sym, entry, sl, tp, comment);
    else
        success = trade.Sell(lots, sym, entry, sl, tp, comment);

    if(success)
    {
        dailyTrades++;
        totalTrades++;
        inPosition = true;

        Print("══ TRADE #", totalTrades, " (Today:", dailyTrades, ") ══");
        Print("  Type   : ", isBuy ? "BUY" : "SELL");
        Print("  Entry  : ", NormalizeDouble(entry, digits));
        Print("  SL     : ", NormalizeDouble(sl, digits), " (", NormalizeDouble(slDist/pipSize, 1), " pips)");
        Print("  TP     : ", NormalizeDouble(tp, digits), " (", NormalizeDouble(tpDist/pipSize, 1), " pips)");
        Print("  Lots   : ", lots);
        Print("  Risk   : $", NormalizeDouble(riskAmt, 2));
        Print("  Reason : ", reason);
        Print("  Mode   : ", InpScalpMode ? "SCALP" : "NORMAL");
        if(!InpScalpMode) Print("  RR     : 1:", NormalizeDouble(InpTpAtrMult/InpSlAtrMult, 2));
    }
    else
    {
        Print("Trade FAILED — Error: ", trade.ResultRetcode(),
              " | ", trade.ResultRetcodeDescription());
    }
}

void PrintQualitySetup(string dir, string reason, double rsi, double atr,
                        double ef, double es)
{
    if(!InpEnableLog) return;
    Print("══ QUALITY ", dir, " SETUP DETECTED ══");
    Print("  Reason     : ", reason);
    Print("  RSI        : ", NormalizeDouble(rsi, 1));
    Print("  ATR        : ", NormalizeDouble(atr, 5));
    Print("  EMA Fast   : ", NormalizeDouble(ef, 5));
    Print("  EMA Slow   : ", NormalizeDouble(es, 5));
    Print("  Daily trades so far: ", dailyTrades, "/", InpMaxDailyTrades);
}

//==========================================================================
//  ON TRADE  (track closed positions)
//==========================================================================

void OnTradeTransaction(const MqlTradeTransaction& trans,
                        const MqlTradeRequest& req,
                        const MqlTradeResult& res)
{
    if(trans.type != TRADE_TRANSACTION_DEAL_ADD) return;
    if(trans.symbol != sym) return;

    CDealInfo deal;
    if(!deal.Ticket(trans.deal)) return;
    if(deal.Magic() != InpMagic) return;

    double pnl = deal.Profit() + deal.Swap() + deal.Commission();
    if(deal.Entry() == DEAL_ENTRY_OUT || deal.Entry() == DEAL_ENTRY_OUT_BY)
    {
        totalPnl += pnl;
        if(pnl < 0) 
        {
            dailyLoss += MathAbs(pnl);
            lastTradeResult = "LOSS";
            if(InpScalpMode) scalpCooldownBars = InpScalpCooldown;
        }
        else
        {
            lastTradeResult = "WIN";
        }

        Print("── POSITION CLOSED ──  P&L: $", NormalizeDouble(pnl, 2),
              "  | Result: ", lastTradeResult, 
              "  | Total P&L: $", NormalizeDouble(totalPnl, 2));
    }
}
