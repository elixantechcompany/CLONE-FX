//+------------------------------------------------------------------+
//|  GoldClone_EA.mq5                                                |
//|  GOLD CLONE — Precision Multi-Engine Trading EA                  |
//|                                                                  |
//|  Ported 1-to-1 from Python source:                              |
//|    src/twister_strategy.py   → TwisterPro engine (Magic 2001)   |
//|    src/m1_scalper.py         → M1 Scalper engine  (Magic 1001)  |
//|    src/risk_manager.py       → RiskProfile + circuit breakers   |
//|    src/ea_engine.py          → Execution + breakeven manager    |
//|    config/config.yaml        → All default parameters           |
//|                                                                  |
//|  Symbols  : XAUUSD (Gold) and BTCUSD (Bitcoin)                  |
//|  Engines  :                                                      |
//|    [1] TwisterPro  – 5-layer M5/M15 scalper (Magic 2001)       |
//|    [2] M1 Scalper  – micro-momentum M1/M5    (Magic 1001)       |
//|  Risk     : Dynamic lot-sizing, daily + trailing drawdown guards |
//|  Position : Auto breakeven at 1.5 × initial risk               |
//+------------------------------------------------------------------+
#property copyright "GOLD CLONE"
#property version   "1.00"
#property strict

#include "GoldClone_Includes.mqh"

//===================================================================
// INPUT PARAMETERS — mirror config/config.yaml
//===================================================================

// ── Symbol ──────────────────────────────────────────────────────
input string   Inp_Symbol2      = "BTCUSD";          // 2nd symbol (leave blank to trade only chart symbol)

// ── Account type ────────────────────────────────────────────────
input ENUM_ACCT_TYPE Inp_AcctType = ACCT_PERSONAL;   // Account profile
input double   Inp_AccountBalance = 20.0;            // Starting balance for risk calc

// ── Engine toggles ──────────────────────────────────────────────
input bool     Inp_TwisterEnabled = true;            // Enable TwisterPro engine (Magic 2001)
input bool     Inp_ScalperEnabled = true;            // Enable M1 Scalper engine (Magic 1001)

// ── TwisterPro parameters (twister_strategy.py) ─────────────────
input int      Inp_TW_FastEMA    = 9;                // Fast EMA period
input int      Inp_TW_MidEMA     = 21;               // Mid EMA period
input int      Inp_TW_SlowEMA    = 50;               // Slow EMA period
input int      Inp_TW_RSIPeriod  = 14;               // RSI period
input double   Inp_TW_RSI_BuyMin = 48.0;             // RSI buy minimum
input double   Inp_TW_RSI_BuyMax = 72.0;             // RSI buy maximum
input double   Inp_TW_RSI_SellMin= 28.0;             // RSI sell minimum
input double   Inp_TW_RSI_SellMax= 52.0;             // RSI sell maximum
input int      Inp_TW_ATRPeriod  = 14;               // ATR period
input double   Inp_TW_ATR_SLMult = 1.2;              // ATR × multiplier for SL distance
input double   Inp_TW_ATR_TPMult = 2.0;              // ATR × multiplier for TP distance
input double   Inp_TW_MinSL_XAU  = 1.00;             // Min SL $ XAUUSD
input double   Inp_TW_MaxSL_XAU  = 2.20;             // Max SL $ XAUUSD
input double   Inp_TW_MinTP_XAU  = 2.00;             // Min TP $ XAUUSD
input double   Inp_TW_MaxTP_XAU  = 4.40;             // Max TP $ XAUUSD
input double   Inp_TW_MaxChase   = 0.35;             // Max price drift from signal bar close
input int      Inp_TW_SwingBars  = 8;                // Swing lookback bars (Layer 2)
input double   Inp_TW_WickPct    = 0.15;             // Min rejection wick % (Layer 2)
input int      Inp_TW_MinScore   = 75;               // Minimum quality score to trade
input int      Inp_TW_MaxSpread  = 320;              // Max spread points for XAUUSD
input ENUM_TIMEFRAMES Inp_TW_TF  = PERIOD_M5;        // TwisterPro execution timeframe

// ── M1 Scalper parameters (m1_scalper.py) ───────────────────────
input int      Inp_SC_FastEMA    = 7;                // Fast EMA
input int      Inp_SC_SlowEMA    = 16;               // Slow EMA
input int      Inp_SC_ATRPeriod  = 14;               // ATR period
input double   Inp_SC_ATR_SLMult = 1.5;              // SL = ATR × multiplier
input double   Inp_SC_RR         = 2.0;              // Risk-reward ratio
input int      Inp_SC_SwingBars  = 8;                // Liquidity sweep lookback
input int      Inp_SC_TrendEMA   = 20;               // M15 trend EMA period
input int      Inp_SC_MinScore   = 70;               // Minimum quality score
input int      Inp_SC_MaxSpread  = 280;              // Max spread points

// ── Risk / drawdown limits ───────────────────────────────────────
input double   Inp_RiskPct_BF    = 0.30;             // % equity risk per trade (BrightFunded)
input double   Inp_RiskPct_Pers  = 1.50;             // % equity risk per trade (Personal)
input int      Inp_SessionStart  = 7;                // Session gate start UTC hour
input int      Inp_SessionEnd    = 20;               // Session gate end UTC hour

// ── Position management ─────────────────────────────────────────
input double   Inp_BE_Buffer     = 10.0;             // Breakeven buffer in points

//===================================================================
// GLOBALS
//===================================================================
CTrade         g_trade;
CAccountInfo   g_acct;

RiskProfile    g_profile;
ENUM_TRADE_STATE g_state       = STATE_NORMAL;
double         g_stateMulti    = 1.0;
double         g_dailyStartEq  = 0.0;
double         g_lifetimeHWM   = 0.0;
datetime       g_lastResetDay  = 0;

// Candle-ID dedup store (circular buffer of last 100 IDs)
string         g_tradedIDs[100];
int            g_tradedIDCount = 0;

// Chart symbol + optional 2nd symbol
string         g_sym1;
string         g_sym2;

//===================================================================
// EA LIFECYCLE
//===================================================================
int OnInit()
  {
   g_sym1 = Symbol();
   g_sym2 = (StringLen(Inp_Symbol2) > 2) ? Inp_Symbol2 : "";

   g_profile      = MakeRiskProfile(Inp_AcctType, Inp_AccountBalance);
   g_dailyStartEq = g_acct.Equity();
   g_lifetimeHWM  = g_dailyStartEq;
   g_lastResetDay = 0;

   // Validate symbols exist in Market Watch
   if(!SymbolSelect(g_sym1, true))
     {
      Print("GoldClone EA: Cannot find symbol ", g_sym1, " in Market Watch.");
      return INIT_FAILED;
     }
   if(StringLen(g_sym2) > 0 && !SymbolSelect(g_sym2, true))
     {
      Print("GoldClone EA: Cannot find symbol ", g_sym2, " – running on ", g_sym1, " only.");
      g_sym2 = "";
     }

   Print("GoldClone EA initialised | Sym1=", g_sym1, " Sym2=", g_sym2,
         " | Profile=", EnumToString(Inp_AcctType),
         " | Balance=", Inp_AccountBalance,
         " | TwisterPro=", Inp_TwisterEnabled,
         " | Scalper=", Inp_ScalperEnabled);
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   Print("GoldClone EA stopped. Reason code: ", reason);
  }

//===================================================================
// MAIN TICK
//===================================================================
void OnTick()
  {
   // ── 1. Daily reset ──────────────────────────────────────────
   ResetDailyIfNeeded();

   // ── 2. Update risk state ────────────────────────────────────
   double equity = g_acct.Equity();
   g_state = GetDailyState(g_profile, equity, g_dailyStartEq, g_lifetimeHWM, g_stateMulti);

   // Hard stops — manage existing positions but take no new ones
   if(g_stateMulti <= 0)
     {
      ManageOpenPositions(g_sym1);
      if(StringLen(g_sym2) > 0) ManageOpenPositions(g_sym2);
      return;
     }

   // ── 3. Manage existing positions (breakeven) ────────────────
   ManageOpenPositions(g_sym1);
   if(StringLen(g_sym2) > 0) ManageOpenPositions(g_sym2);

   // ── 4. New signal scan — only on new bar (saves CPU) ────────
   static datetime lastBar1 = 0, lastBar2 = 0;
   datetime curBar1 = iTime(g_sym1, Inp_TW_TF, 0);
   if(curBar1 != lastBar1)
     {
      lastBar1 = curBar1;
      ScanAndTrade(g_sym1);
     }

   if(StringLen(g_sym2) > 0)
     {
      datetime curBar2 = iTime(g_sym2, Inp_TW_TF, 0);
      if(curBar2 != lastBar2)
        {
         lastBar2 = curBar2;
         ScanAndTrade(g_sym2);
        }
     }
  }

//===================================================================
// DAILY RESET
// Mirrors risk_manager.py:reset_daily_metrics_if_needed()
//===================================================================
void ResetDailyIfNeeded()
  {
   MqlDateTime t;
   TimeToStruct(TimeGMT(), t);
   datetime today = StringToTime(StringFormat("%04d.%02d.%02d", t.year, t.mon, t.day));

   if(today != g_lastResetDay)
     {
      g_lastResetDay  = today;
      g_dailyStartEq  = g_acct.Equity();
      g_lifetimeHWM   = MathMax(g_lifetimeHWM, g_dailyStartEq);
      Print("GoldClone: Daily reset | StartEq=", g_dailyStartEq,
            " | LifetimeHWM=", g_lifetimeHWM);
     }

   // Keep lifetime HWM updated every tick
   double eq = g_acct.Equity();
   if(eq > g_lifetimeHWM) g_lifetimeHWM = eq;
  }

//===================================================================
// SCAN AND TRADE — runs for each symbol on new bar
//===================================================================
void ScanAndTrade(const string sym)
  {
   bool isBTC = (StringFind(StringUpper(sym), "BTC") >= 0);

   // Session gate (Layer 4 from TwisterPro)
   if(!IsLiquidSession(isBTC))
     {
      // Outside liquid hours — no new entries (Gold only)
      return;
     }

   // ── Engine 1: TwisterPro ────────────────────────────────────
   if(Inp_TwisterEnabled && !HasOpenPosition(sym, ENGINE_TWISTER))
     {
      SignalResult tw = TwisterProSignal(sym, isBTC);
      if(tw.valid && !IsIDTraded(tw.candle_id))
        {
         double riskUSD   = CalcTargetRisk(tw.score);
         double lots      = CalcLots(sym, tw.entry, tw.sl, riskUSD, g_profile.hard_reject_risk);
         if(lots > 0)
           {
            bool ok = OpenMarketOrder(g_trade, sym, (tw.direction == "BUY"), lots,
                                      tw.sl, tw.tp, ENGINE_TWISTER,
                                      StringFormat("GC_TW_%s", tw.direction));
            if(ok)
              {
               MarkIDTraded(tw.candle_id);
               Print("GoldClone TwisterPro | ", sym, " | ", tw.direction,
                     " | lots=", lots, " | score=", tw.score, " | ", tw.reason);
              }
           }
        }
     }

   // ── Engine 2: M1 Scalper ────────────────────────────────────
   if(Inp_ScalperEnabled && !HasOpenPosition(sym, ENGINE_SCALPER))
     {
      SignalResult sc = ScalperSignal(sym, isBTC);
      if(sc.valid && !IsIDTraded(sc.candle_id))
        {
         double riskUSD   = CalcTargetRisk(sc.score);
         double lots      = CalcLots(sym, sc.entry, sc.sl, riskUSD, g_profile.hard_reject_risk);
         if(lots > 0)
           {
            bool ok = OpenMarketOrder(g_trade, sym, (sc.direction == "BUY"), lots,
                                      sc.sl, sc.tp, ENGINE_SCALPER,
                                      StringFormat("GC_SC_%s", sc.direction));
            if(ok)
              {
               MarkIDTraded(sc.candle_id);
               Print("GoldClone Scalper | ", sym, " | ", sc.direction,
                     " | lots=", lots, " | score=", sc.score, " | ", sc.reason);
              }
           }
        }
     }
  }

//===================================================================
// CALCULATE TARGET RISK $
// Mirrors risk_manager.py:calculate_lot_size() score-based scaling
// then applies current state multiplier
//===================================================================
double CalcTargetRisk(int score)
  {
   double base;
   if(Inp_AcctType == ACCT_BRIGHTFUNDED)
     {
      if(score >= 80)      base = 3.00;
      else if(score >= 65) base = 2.50;
      else if(score >= 50) base = 2.00;
      else                 base = 1.50;
     }
   else
     {
      if(score >= 80)      base = 0.45;
      else if(score >= 65) base = 0.35;
      else if(score >= 50) base = 0.25;
      else                 base = 0.18;
     }
   return base * g_stateMulti;
  }

//===================================================================
// MANAGE OPEN POSITIONS — breakeven for all GoldClone magic numbers
// Mirrors ea_engine.py:manage_open_positions()
//===================================================================
void ManageOpenPositions(const string sym)
  {
   int total = PositionsTotal();
   for(int i = 0; i < total; i++)
     {
      ulong ticket = PositionGetTicket(i);
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL) != sym) continue;

      int magic = (int)PositionGetInteger(POSITION_MAGIC);
      if(magic != ENGINE_TWISTER && magic != ENGINE_SCALPER) continue;

      TryApplyBreakeven(g_trade, ticket, Inp_BE_Buffer);
     }
  }

//===================================================================
// CANDLE-ID DEDUPLICATION
// Mirrors ea_engine.py:traded_setups / bot.py:traded_candle_ids
//===================================================================
bool IsIDTraded(const string id)
  {
   for(int i = 0; i < g_tradedIDCount; i++)
      if(g_tradedIDs[i] == id) return true;
   return false;
  }

void MarkIDTraded(const string id)
  {
   int slot = g_tradedIDCount % 100;
   g_tradedIDs[slot] = id;
   g_tradedIDCount++;
  }

//===================================================================
//  ENGINE 1 — TwisterPro M5/M15 Signal
//  5-Layer Validation Matrix
//  Ported from twister_strategy.py:generate_signal()
//===================================================================
SignalResult TwisterProSignal(const string sym, bool isBTC)
  {
   SignalResult res;
   res.valid = false;

   int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);

   // ── Fetch last CLOSED bar on execution timeframe ─────────────
   // shift=1 means the last fully closed candle
   double closeC  = iClose(sym, Inp_TW_TF, 1);
   double openC   = iOpen (sym, Inp_TW_TF, 1);
   double highC   = iHigh (sym, Inp_TW_TF, 1);
   double lowC    = iLow  (sym, Inp_TW_TF, 1);
   if(closeC <= 0) return res;

   // ── LAYER 1: Momentum & Trend alignment ──────────────────────
   // EMA 9 / 21 / 50 on closed bar; RSI(14)
   double ema9  = CalcEMA(sym, Inp_TW_TF, Inp_TW_FastEMA, 1);
   double ema21 = CalcEMA(sym, Inp_TW_TF, Inp_TW_MidEMA,  1);
   double ema50 = CalcEMA(sym, Inp_TW_TF, Inp_TW_SlowEMA, 1);
   double rsi   = CalcRSI(sym, Inp_TW_TF, Inp_TW_RSIPeriod, 1);
   if(ema9 <= 0 || ema21 <= 0 || ema50 <= 0) return res;

   string direction = "";
   int    l1Score   = 0;

   if(ema9 > ema21 && ema21 > ema50)
     {
      if(rsi >= Inp_TW_RSI_BuyMin && rsi <= Inp_TW_RSI_BuyMax)
        { direction = "BUY";  l1Score = 20; }
      else return res;
     }
   else if(ema9 < ema21 && ema21 < ema50)
     {
      if(rsi >= Inp_TW_RSI_SellMin && rsi <= Inp_TW_RSI_SellMax)
        { direction = "SELL"; l1Score = 20; }
      else return res;
     }
   else return res;  // mixed — no trade

   int totalScore = l1Score;

   // ── LAYER 2: Micro-structure swing breakout / rejection ───────
   double swHigh = SwingHigh(sym, Inp_TW_TF, Inp_TW_SwingBars, 2);  // shift 2 = bars before signal bar
   double swLow  = SwingLow (sym, Inp_TW_TF, Inp_TW_SwingBars, 2);
   double prevClose = iClose(sym, Inp_TW_TF, 2);
   double prevHigh  = iHigh (sym, Inp_TW_TF, 2);
   double prevLow   = iLow  (sym, Inp_TW_TF, 2);
   double range     = highC - lowC;
   if(range <= 0) return res;

   int l2Score = 0;
   if(direction == "BUY")
     {
      double lowerWick    = MathMin(openC, closeC) - lowC;
      double lowerWickPct = lowerWick / range;
      bool closedAbove = closeC > swHigh;
      bool pinBar      = lowerWickPct >= Inp_TW_WickPct && closeC > openC;
      bool emaB        = lowC <= ema9 && closeC > ema9;
      bool barBreak    = closeC > prevHigh;
      bool trendCont   = closeC > openC && closeC >= ema9;

      if(closedAbove)    l2Score = 20;
      else if(pinBar)    l2Score = 15;
      else if(emaB)      l2Score = 15;
      else if(barBreak)  l2Score = 15;
      else if(trendCont) l2Score = 15;
      else return res;
     }
   else
     {
      double upperWick    = highC - MathMax(openC, closeC);
      double upperWickPct = upperWick / range;
      bool closedBelow = closeC < swLow;
      bool pinBar      = upperWickPct >= Inp_TW_WickPct && closeC < openC;
      bool emaR        = highC >= ema9 && closeC < ema9;
      bool barBreak    = closeC < prevLow;
      bool trendCont   = closeC < openC && closeC <= ema9;

      if(closedBelow)    l2Score = 20;
      else if(pinBar)    l2Score = 15;
      else if(emaR)      l2Score = 15;
      else if(barBreak)  l2Score = 15;
      else if(trendCont) l2Score = 15;
      else return res;
     }
   totalScore += l2Score;

   // ── LAYER 3: Volatility & ATR bounds ──────────────────────────
   double atr = CalcATR(sym, Inp_TW_TF, Inp_TW_ATRPeriod, 1);
   if(atr <= 0) return res;

   double atrMinPts = 0.40;
   double maxCandleRatio = 2.5;
   if(atr < atrMinPts) return res;
   if(range > atr * maxCandleRatio) return res;
   totalScore += 20;

   // ── LAYER 4: Session gate ─────────────────────────────────────
   if(!IsLiquidSession(isBTC)) return res;
   totalScore += 20;

   // ── LAYER 5: Spread gate ──────────────────────────────────────
   int maxSpread = isBTC ? 60000 : Inp_TW_MaxSpread;
   if(!IsSpreadOK(sym, maxSpread)) return res;
   totalScore += 20;

   // ── Score threshold ───────────────────────────────────────────
   if(totalScore < Inp_TW_MinScore) return res;

   // ── No-chase guard ────────────────────────────────────────────
   double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
   double bid = SymbolInfoDouble(sym, SYMBOL_BID);
   double livePrice = (direction == "BUY") ? ask : bid;
   double maxChase  = isBTC ? 80.0 : Inp_TW_MaxChase;
   if(MathAbs(livePrice - closeC) > maxChase) return res;

   // ── SL / TP distances ─────────────────────────────────────────
   double minSL, maxSL, minTP, maxTP;
   if(isBTC)
     { minSL = 60.0; maxSL = 90.0;  minTP = 180.0; maxTP = 300.0; }
   else
     { minSL = Inp_TW_MinSL_XAU; maxSL = Inp_TW_MaxSL_XAU;
       minTP = Inp_TW_MinTP_XAU; maxTP = Inp_TW_MaxTP_XAU; }

   double rawSL   = atr * Inp_TW_ATR_SLMult;
   double slDist  = MathMax(minSL, MathMin(rawSL, maxSL));
   double rawTP   = slDist * (Inp_TW_ATR_TPMult / MathMax(0.1, Inp_TW_ATR_SLMult));
   double tpDist  = MathMax(minTP, MathMin(rawTP, maxTP));

   double entry = livePrice;
   double sl    = (direction == "BUY")
                  ? NormalizeDouble(entry - slDist, digits)
                  : NormalizeDouble(entry + slDist, digits);
   double tp    = (direction == "BUY")
                  ? NormalizeDouble(entry + tpDist, digits)
                  : NormalizeDouble(entry - tpDist, digits);

   // ── Build candle ID (unique per symbol + timeframe + bar time) ─
   datetime barTime = iTime(sym, Inp_TW_TF, 1);
   string   barStr  = TimeToString(barTime, TIME_DATE | TIME_MINUTES);
   StringReplace(barStr, " ", "_");
   StringReplace(barStr, ":", "");

   res.valid     = true;
   res.direction = direction;
   res.entry     = entry;
   res.sl        = sl;
   res.tp        = tp;
   res.score     = totalScore;
   res.candle_id = StringFormat("TWISTER_%s_%s_%s", sym,
                                EnumToString(Inp_TW_TF), barStr);
   res.reason    = StringFormat("TwisterPro %s score=%d ATR=%.4f SL=%.2f TP=%.2f",
                                direction, totalScore, atr, sl, tp);
   return res;
  }

//===================================================================
//  ENGINE 2 — M1 Scalper Signal
//  Momentum + micro-pullback scanner on M1 / M5 with M15 trend context
//  Ported from m1_scalper.py:scan_for_scalp_candidates()
//===================================================================
SignalResult ScalperSignal(const string sym, bool isBTC)
  {
   SignalResult res;
   res.valid = false;

   // ── M15 trend context ─────────────────────────────────────────
   double trendEMA = CalcEMA(sym, PERIOD_M15, Inp_SC_TrendEMA, 1);
   double m15Close = iClose(sym, PERIOD_M15, 1);
   string trendCtx = "NEUTRAL";
   if(m15Close > trendEMA) trendCtx = "UPTREND";
   else if(m15Close < trendEMA) trendCtx = "DOWNTREND";

   // ── Try M1 first, then M5 ─────────────────────────────────────
   ENUM_TIMEFRAMES tfs[2] = {PERIOD_M1, PERIOD_M5};
   for(int t = 0; t < 2; t++)
     {
      SignalResult candidate = EvaluateScalperTF(sym, tfs[t], trendCtx, isBTC);
      if(candidate.valid)
        { return candidate; }
     }
   return res;
  }

//--- Single timeframe evaluation for M1 Scalper
SignalResult EvaluateScalperTF(const string sym,
                                ENUM_TIMEFRAMES tf,
                                const string    trendCtx,
                                bool            isBTC)
  {
   SignalResult res;
   res.valid = false;

   int    digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   double minSL  = isBTC ? 60.0 : 1.00;
   double maxSL  = isBTC ? 90.0 : 1.80;

   // ── Closed bar data ───────────────────────────────────────────
   double closeP = iClose(sym, tf, 1);   // signal bar
   double openP  = iOpen (sym, tf, 1);
   double highP  = iHigh (sym, tf, 1);
   double lowP   = iLow  (sym, tf, 1);
   double closeP2= iClose(sym, tf, 2);   // prior bar
   double openP2 = iOpen (sym, tf, 2);
   double highP2 = iHigh (sym, tf, 2);
   double lowP2  = iLow  (sym, tf, 2);
   if(closeP <= 0 || closeP2 <= 0) return res;

   // ── EMAs on signal bar ────────────────────────────────────────
   double emaFast = CalcEMA(sym, tf, Inp_SC_FastEMA, 1);
   double emaSlow = CalcEMA(sym, tf, Inp_SC_SlowEMA, 1);
   double atr     = CalcATR(sym, tf, Inp_SC_ATRPeriod, 1);
   double rsi     = CalcRSI(sym, tf, 14, 1);
   if(emaFast <= 0 || emaSlow <= 0 || atr <= 0) return res;

   // ── Swing bounds (over last sweep_lookback bars before signal) ─
   double swHigh = SwingHigh(sym, tf, Inp_SC_SwingBars, 2);
   double swLow  = SwingLow (sym, tf, Inp_SC_SwingBars, 2);

   double range    = highP - lowP;
   if(range <= 0) return res;
   double upperWick = highP - MathMax(openP, closeP);
   double lowerWick = MathMin(openP, closeP) - lowP;

   double rawSL = atr * Inp_SC_ATR_SLMult;
   double slDist = NormalizeDouble(MathMax(MathMin(rawSL, maxSL), minSL), digits);
   double tpDist = NormalizeDouble(slDist * Inp_SC_RR, digits);

   // ── Spread gate ───────────────────────────────────────────────
   int maxSpread = isBTC ? 2200 : Inp_SC_MaxSpread;
   if(!IsSpreadOK(sym, maxSpread)) return res;
   long sp = 0;
   SymbolInfoInteger(sym, SYMBOL_SPREAD, sp);

   // ── Chop filter — reject if last 6 bars alternate 4+ times ───
   int altCount = 0;
   for(int k = 1; k <= 5; k++)
     {
      double c1 = iClose(sym, tf, k);
      double o1 = iOpen (sym, tf, k);
      double c2 = iClose(sym, tf, k+1);
      double o2 = iOpen (sym, tf, k+1);
      if((c1 >= o1) != (c2 >= o2)) altCount++;
     }
   if(altCount >= 4) return res;

   // ── Bullish patterns ──────────────────────────────────────────
   bool isBullBreakout  = (closeP > swHigh && closeP > openP && closeP2 <= swHigh);
   bool isBullPinBar    = (lowerWick / range >= 0.30) && (upperWick / range <= 0.35) && (closeP >= openP);
   bool isBullEngulfing = (closeP > openP) && (closeP >= highP2) && (closeP2 < openP2);
   bool isBullPullback  = (closeP2 <= openP2) &&
                          (lowP2 <= emaFast || lowP2 <= emaSlow) &&
                          (closeP > emaFast) && (closeP > openP);
   bool isBullSweep     = (lowP < swLow) && (closeP > swLow) && (closeP > openP);

   bool buyTrend = (emaFast >= emaSlow);

   // ── Bearish patterns ──────────────────────────────────────────
   bool isBearBreakout  = (closeP < swLow && closeP < openP && closeP2 >= swLow);
   bool isBearPinBar    = (upperWick / range >= 0.30) && (lowerWick / range <= 0.35) && (closeP <= openP);
   bool isBearEngulfing = (closeP < openP) && (closeP <= lowP2) && (closeP2 > openP2);
   bool isBearPullback  = (closeP2 >= openP2) &&
                          (highP2 >= emaFast || highP2 >= emaSlow) &&
                          (closeP < emaFast) && (closeP < openP);
   bool isBearSweep     = (highP > swHigh) && (closeP < swHigh) && (closeP < openP);

   bool sellTrend = (emaFast <= emaSlow);

   // ── Evaluate SELL first (mirrors py order) ────────────────────
   bool validBear = sellTrend &&
                    (isBearBreakout || isBearPinBar || isBearEngulfing ||
                     isBearPullback || isBearSweep);
   bool rsiOKSell = (rsi >= 30.0 && rsi <= 68.0) || isBearPinBar || isBearSweep;

   if(validBear && rsiOKSell)
     {
      int score = ScalperQualityScore("SELL", trendCtx, rsi, atr,
                                      isBearBreakout||isBearSweep, (int)sp, isBTC);
      if(score >= Inp_SC_MinScore)
        {
         double bid = SymbolInfoDouble(sym, SYMBOL_BID);
         // Chase guard: price should not have drifted more than atr*0.5
         double maxChase = MathMin(atr * 0.50, isBTC ? 30.0 : 0.40);
         double chaseDist = closeP - bid;
         if(chaseDist >= -0.25 && chaseDist <= maxChase && bid <= highP)
           {
            double entry = bid;
            datetime barTime = iTime(sym, tf, 1);
            string   barStr  = TimeToString(barTime, TIME_DATE|TIME_MINUTES);
            StringReplace(barStr, " ", "_");
            StringReplace(barStr, ":", "");

            res.valid     = true;
            res.direction = "SELL";
            res.entry     = entry;
            res.sl        = NormalizeDouble(entry + slDist, digits);
            res.tp        = NormalizeDouble(entry - tpDist, digits);
            res.score     = score;
            res.candle_id = StringFormat("SCALP_SELL_%s_%s_%s", sym,
                                         EnumToString(tf), barStr);
            res.reason    = StringFormat("Scalper SELL %s score=%d ATR=%.4f RSI=%.1f",
                                         EnumToString(tf), score, atr, rsi);
            return res;
           }
        }
     }

   // ── Evaluate BUY ──────────────────────────────────────────────
   bool validBull = buyTrend &&
                    (isBullBreakout || isBullPinBar || isBullEngulfing ||
                     isBullPullback || isBullSweep);
   bool rsiOKBuy = (rsi >= 32.0 && rsi <= 70.0) || isBullPinBar || isBullSweep;

   if(validBull && rsiOKBuy)
     {
      int score = ScalperQualityScore("BUY", trendCtx, rsi, atr,
                                      isBullBreakout||isBullSweep, (int)sp, isBTC);
      if(score >= Inp_SC_MinScore)
        {
         double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
         double maxChase = MathMin(atr * 0.50, isBTC ? 30.0 : 0.40);
         double chaseDist = ask - closeP;
         if(chaseDist >= -0.25 && chaseDist <= maxChase && ask >= lowP)
           {
            double entry = ask;
            datetime barTime = iTime(sym, tf, 1);
            string   barStr  = TimeToString(barTime, TIME_DATE|TIME_MINUTES);
            StringReplace(barStr, " ", "_");
            StringReplace(barStr, ":", "");

            res.valid     = true;
            res.direction = "BUY";
            res.entry     = entry;
            res.sl        = NormalizeDouble(entry - slDist, digits);
            res.tp        = NormalizeDouble(entry + tpDist, digits);
            res.score     = score;
            res.candle_id = StringFormat("SCALP_BUY_%s_%s_%s", sym,
                                         EnumToString(tf), barStr);
            res.reason    = StringFormat("Scalper BUY %s score=%d ATR=%.4f RSI=%.1f",
                                         EnumToString(tf), score, atr, rsi);
            return res;
           }
        }
     }

   return res;
  }

//--- Graded quality score (0-100) for M1 Scalper
//    Mirrors m1_scalper.py:calculate_quality_score()
int ScalperQualityScore(const string dir,
                        const string trendCtx,
                        double rsi,
                        double atr,
                        bool   isBreakoutOrSweep,
                        int    spread,
                        bool   isBTC)
  {
   // 1. Trend alignment (0-30)
   int sTrend = 0;
   if(dir == "BUY"  && trendCtx == "UPTREND")   sTrend = 30;
   else if(dir == "SELL" && trendCtx == "DOWNTREND") sTrend = 30;
   else if(trendCtx == "NEUTRAL") sTrend = 5;

   // 2. Momentum / RSI + volatility (0-25)
   int sMom = 0;
   if(dir == "BUY"  && rsi >= 40.0 && rsi <= 68.0) sMom += 15;
   else if(dir == "SELL" && rsi >= 32.0 && rsi <= 60.0) sMom += 15;
   else sMom += 8;
   sMom += (atr > 0) ? 10 : 5;

   // 3. Candle structure (0-25)
   int sCandle = isBreakoutOrSweep ? 25 : 20;

   // 4. Spread (0-10)
   int maxNormal = isBTC ? 2200 : 280;
   int sSpread   = (spread <= maxNormal) ? 10 : 5;

   // 5. ATR stability (0-10)
   int sATR = (atr > 0) ? 10 : 5;

   return sTrend + sMom + sCandle + sSpread + sATR;
  }
//+------------------------------------------------------------------+
