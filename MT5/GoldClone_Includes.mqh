//+------------------------------------------------------------------+
//| GoldClone_Includes.mqh                                           |
//| Shared enums, structs, indicator helpers, lot-sizing, fills      |
//| Ported from Python: twister_strategy.py, m1_scalper.py,         |
//|   risk_manager.py, ea_engine.py, execution.py                   |
//+------------------------------------------------------------------+
#ifndef GOLDCLONE_INCLUDES_MQH
#define GOLDCLONE_INCLUDES_MQH

#include <Trade\Trade.mqh>
#include <Trade\SymbolInfo.mqh>
#include <Trade\AccountInfo.mqh>

//===================================================================
// ENUMS
//===================================================================
enum ENUM_TRADE_ENGINE
  {
   ENGINE_TWISTER  = 2001,   // TwisterPro M5/M15 — Magic 2001
   ENGINE_SCALPER  = 1001    // M1 Micro-Scalper  — Magic 1001
  };

enum ENUM_ACCT_TYPE
  {
   ACCT_BRIGHTFUNDED,  // $1 000 prop challenge
   ACCT_PERSONAL       // $20 personal / demo
  };

enum ENUM_TRADE_STATE
  {
   STATE_NORMAL,
   STATE_WARNING,
   STATE_REDUCED_RISK,
   STATE_PROFIT_PROTECT,
   STATE_HIGH_SELECTIVITY,
   STATE_TARGET_REACHED,
   STATE_DAILY_HARD_STOP,
   STATE_CHALLENGE_PASSED
  };

//===================================================================
// STRUCTS
//===================================================================
struct SignalResult
  {
   bool              valid;
   string            direction;   // "BUY" / "SELL"
   double            entry;
   double            sl;
   double            tp;
   int               score;       // 0-100
   string            reason;
   string            candle_id;
  };

struct RiskProfile
  {
   ENUM_ACCT_TYPE    acct_type;
   double            initial_balance;
   double            daily_hard_stop;       // internal stop (leaves buffer)
   double            daily_warning;
   double            daily_reduced_risk;
   double            trailing_hard_stop;
   double            trailing_warning;
   double            trailing_reduced_stop;
   double            max_trade_risk;
   double            hard_reject_risk;
   double            profit_protect_trigger;
   double            profit_selectivity_trigger;
   double            profit_target_stop;
   double            challenge_target;
  };

//===================================================================
// INDICATOR HELPERS
//===================================================================

//--- EMA on any symbol / timeframe
double CalcEMA(const string sym, ENUM_TIMEFRAMES tf, int period, int shift=1)
  {
   int h = iMA(sym, tf, period, 0, MODE_EMA, PRICE_CLOSE);
   if(h == INVALID_HANDLE) return 0;
   double buf[1];
   if(CopyBuffer(h, 0, shift, 1, buf) < 1) return 0;
   IndicatorRelease(h);
   return buf[0];
  }

//--- ATR on any symbol / timeframe
double CalcATR(const string sym, ENUM_TIMEFRAMES tf, int period, int shift=1)
  {
   int h = iATR(sym, tf, period);
   if(h == INVALID_HANDLE) return 0;
   double buf[1];
   if(CopyBuffer(h, 0, shift, 1, buf) < 1) return 0;
   IndicatorRelease(h);
   return buf[0];
  }

//--- RSI on any symbol / timeframe
double CalcRSI(const string sym, ENUM_TIMEFRAMES tf, int period, int shift=1)
  {
   int h = iRSI(sym, tf, period, PRICE_CLOSE);
   if(h == INVALID_HANDLE) return 50;
   double buf[1];
   if(CopyBuffer(h, 0, shift, 1, buf) < 1) return 50;
   IndicatorRelease(h);
   return buf[0];
  }

//--- Swing High over last N closed bars
double SwingHigh(const string sym, ENUM_TIMEFRAMES tf, int bars, int shift=2)
  {
   double highs[];
   if(CopyHigh(sym, tf, shift, bars, highs) < bars) return 0;
   double mx = highs[0];
   for(int i=1; i<bars; i++) if(highs[i] > mx) mx = highs[i];
   return mx;
  }

//--- Swing Low over last N closed bars
double SwingLow(const string sym, ENUM_TIMEFRAMES tf, int bars, int shift=2)
  {
   double lows[];
   if(CopyLow(sym, tf, shift, bars, lows) < bars) return DBL_MAX;
   double mn = lows[0];
   for(int i=1; i<bars; i++) if(lows[i] < mn) mn = lows[i];
   return mn;
  }

//===================================================================
// FILLING MODE HELPER
// Mirrors ea_engine.py:get_symbol_filling_type()
//===================================================================
ENUM_ORDER_TYPE_FILLING GetFillingMode(const string sym)
  {
   long fill = 0;
   SymbolInfoInteger(sym, SYMBOL_FILLING_MODE, fill);
   if((fill & ORDER_FILLING_IOC) != 0) return ORDER_FILLING_IOC;
   if((fill & ORDER_FILLING_FOK) != 0) return ORDER_FILLING_FOK;
   return ORDER_FILLING_RETURN;
  }

//===================================================================
// LOT SIZING
// Mirrors risk_manager.py:calculate_lot_size()
// Uses dollar risk / SL_distance method, snapped to broker step.
//===================================================================
double CalcLots(
   const string sym,
   double entry,
   double sl,
   double targetRiskUSD,    // already scaled by state multiplier
   double hardRejectUSD)
  {
   double slDist = MathAbs(entry - sl);
   if(slDist <= 0) return 0;

   double tickVal  = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE);
   double tickSize = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
   double volMin   = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
   double volMax   = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
   double volStep  = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);

   if(tickSize <= 0 || tickVal <= 0 || volStep <= 0) return 0;

   double valuePerPtPerLot = tickVal / tickSize;
   double rawLots = targetRiskUSD / (slDist * valuePerPtPerLot);

   // snap to broker step
   double lots = MathFloor(rawLots / volStep) * volStep;
   lots = MathMax(volMin, MathMin(volMax, lots));
   lots = NormalizeDouble(lots, 2);

   // Hard-reject guard: simulate loss at this lot size
   double simLoss = slDist * valuePerPtPerLot * lots;
   if(simLoss > hardRejectUSD)
     {
      // step down until within limit
      while(lots > volMin && slDist * valuePerPtPerLot * lots > hardRejectUSD)
         lots = NormalizeDouble(lots - volStep, 2);
      simLoss = slDist * valuePerPtPerLot * lots;
      if(simLoss > hardRejectUSD)
         return 0;  // still too wide — reject
     }

   return lots;
  }

//===================================================================
// RISK PROFILE FACTORY
// Returns pre-filled RiskProfile for BrightFunded ($1k) or Personal ($20)
//===================================================================
RiskProfile MakeRiskProfile(ENUM_ACCT_TYPE t, double balance=0)
  {
   RiskProfile p;
   p.acct_type = t;
   if(t == ACCT_BRIGHTFUNDED)
     {
      p.initial_balance            = (balance > 0) ? balance : 1000.0;
      p.daily_warning              = 15.0;
      p.daily_reduced_risk         = 20.0;
      p.daily_hard_stop            = 25.0;   // firm limit $30 — $5 buffer
      p.trailing_warning           = 30.0;
      p.trailing_reduced_stop      = 40.0;
      p.trailing_hard_stop         = 50.0;   // firm limit $60 — $10 buffer
      p.max_trade_risk             = 3.00;
      p.hard_reject_risk           = 3.50;
      p.profit_protect_trigger     = 30.0;
      p.profit_selectivity_trigger = 40.0;
      p.profit_target_stop         = 50.0;
      p.challenge_target           = 100.0;
     }
   else
     {
      p.initial_balance            = (balance > 0) ? balance : 20.0;
      p.daily_warning              = p.initial_balance * 0.075;  // ~7.5 %
      p.daily_reduced_risk         = p.initial_balance * 0.15;
      p.daily_hard_stop            = p.initial_balance * 0.20;   // 20 % of balance
      p.trailing_warning           = p.initial_balance * 0.125;
      p.trailing_reduced_stop      = p.initial_balance * 0.20;
      p.trailing_hard_stop         = p.initial_balance * 0.25;
      p.max_trade_risk             = 3.50;
      p.hard_reject_risk           = 4.50;
      p.profit_protect_trigger     = 10.0;
      p.profit_selectivity_trigger = 20.0;
      p.profit_target_stop         = 30.0;
      p.challenge_target           = 9999.0; // no target for personal
     }
   return p;
  }

//===================================================================
// DAILY RISK STATE
// Returns state & multiplier. Call once per tick after equity sync.
//===================================================================
ENUM_TRADE_STATE GetDailyState(
   const RiskProfile &prof,
   double equity,
   double dailyStartEq,
   double lifetimeHWM,
   double &multiplierOut)
  {
   multiplierOut = 1.0;
   double netPnl      = equity - dailyStartEq;
   double dailyLoss   = MathMax(0, -netPnl);
   double trailingDD  = MathMax(0, lifetimeHWM - equity);

   // Challenge / Target reached
   if(prof.acct_type == ACCT_BRIGHTFUNDED &&
      (equity - prof.initial_balance) >= prof.challenge_target)
     { multiplierOut = 0; return STATE_CHALLENGE_PASSED; }

   // Daily profit target
   if(netPnl >= prof.profit_target_stop)
     { multiplierOut = 0; return STATE_TARGET_REACHED; }

   // Daily loss ladder
   if(dailyLoss >= prof.daily_hard_stop)
     { multiplierOut = 0; return STATE_DAILY_HARD_STOP; }

   if(dailyLoss >= prof.daily_reduced_risk)
     { multiplierOut = 0.40; return STATE_REDUCED_RISK; }

   if(dailyLoss >= prof.daily_warning)
     { multiplierOut = 0.70; return STATE_WARNING; }

   // Trailing drawdown ladder
   if(trailingDD >= prof.trailing_hard_stop)
     { multiplierOut = 0; return STATE_DAILY_HARD_STOP; }

   if(trailingDD >= prof.trailing_reduced_stop)
     { multiplierOut = 0.40; return STATE_REDUCED_RISK; }

   if(trailingDD >= prof.trailing_warning)
     { multiplierOut = 0.70; return STATE_WARNING; }

   // Profit lifecycle
   if(netPnl >= prof.profit_selectivity_trigger)
     { multiplierOut = 0.50; return STATE_HIGH_SELECTIVITY; }

   if(netPnl >= prof.profit_protect_trigger)
     { multiplierOut = 0.70; return STATE_PROFIT_PROTECT; }

   return STATE_NORMAL;
  }

//===================================================================
// SESSION GATE
// Mirrors twister_strategy.py:validate_layer_4_session()
// Returns true during London + New York: 07:00 – 20:00 UTC
//===================================================================
bool IsLiquidSession(bool btcMode=false)
  {
   if(btcMode) return true;        // crypto runs 24/7
   MqlDateTime tm;
   TimeToStruct(TimeGMT(), tm);
   return (tm.hour >= 7 && tm.hour < 20);
  }

//===================================================================
// SPREAD GATE
// Mirrors twister_strategy.py:validate_layer_5_spread()
//===================================================================
bool IsSpreadOK(const string sym, int maxPts)
  {
   long sp = 0;
   SymbolInfoInteger(sym, SYMBOL_SPREAD, sp);
   return ((int)sp <= maxPts);
  }

//===================================================================
// DUPLICATE POSITION CHECK
// One open position per magic number per symbol — mirrors ea_engine.py
//===================================================================
bool HasOpenPosition(const string sym, int magic)
  {
   int total = PositionsTotal();
   for(int i = 0; i < total; i++)
     {
      ulong ticket = PositionGetTicket(i);
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL) == sym &&
         (int)PositionGetInteger(POSITION_MAGIC) == magic)
         return true;
     }
   return false;
  }

//===================================================================
// SAFE OPEN MARKET ORDER
// Wraps CTrade with fill-mode auto-detection + stops validation
//===================================================================
bool OpenMarketOrder(
   CTrade  &trade,
   const string sym,
   bool   isBuy,
   double lots,
   double sl,
   double tp,
   int    magic,
   const string comment)
  {
   if(lots <= 0) return false;

   int    digits  = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   double point   = SymbolInfoDouble(sym,  SYMBOL_POINT);
   long   stopsLv = SymbolInfoInteger(sym, SYMBOL_TRADE_STOPS_LEVEL);
   double minDist = stopsLv * point;

   double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
   double bid = SymbolInfoDouble(sym, SYMBOL_BID);
   double price = isBuy ? ask : bid;

   // Clamp SL / TP to minimum broker distance
   if(isBuy)
     {
      if(sl > 0 && (price - sl) < minDist) sl = NormalizeDouble(price - minDist, digits);
      if(tp > 0 && (tp - price) < minDist) tp = NormalizeDouble(price + minDist, digits);
     }
   else
     {
      if(sl > 0 && (sl - price) < minDist) sl = NormalizeDouble(price + minDist, digits);
      if(tp > 0 && (price - tp) < minDist) tp = NormalizeDouble(price - minDist, digits);
     }

   trade.SetExpertMagicNumber(magic);
   trade.SetDeviationInPoints(35);
   trade.SetTypeFilling(GetFillingMode(sym));
   trade.SetAsyncMode(false);

   bool ok = isBuy
             ? trade.Buy(lots, sym, price, sl, tp, comment)
             : trade.Sell(lots, sym, price, sl, tp, comment);

   return ok;
  }

//===================================================================
// BREAKEVEN HELPER
// Mirrors ea_engine.py:manage_open_positions()
// Move SL to entry + buffer once profit >= 1.5 × initial_risk
//===================================================================
bool TryApplyBreakeven(CTrade &trade, ulong ticket, double beBufferPts=10)
  {
   if(!PositionSelectByTicket(ticket)) return false;

   double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
   double curPrice  = PositionGetDouble(POSITION_PRICE_CURRENT);
   double curSL     = PositionGetDouble(POSITION_SL);
   double curTP     = PositionGetDouble(POSITION_TP);
   int    posType   = (int)PositionGetInteger(POSITION_TYPE);
   string sym       = PositionGetString(POSITION_SYMBOL);

   double point   = SymbolInfoDouble(sym, SYMBOL_POINT);
   int    digits  = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   double slDist  = (curSL > 0) ? MathAbs(openPrice - curSL) : 10.0 * point;

   if(posType == POSITION_TYPE_BUY)
     {
      double profitDist = curPrice - openPrice;
      if(profitDist >= slDist * 1.5 && curSL < openPrice)
        {
         double newSL = NormalizeDouble(openPrice + beBufferPts * point, digits);
         return trade.PositionModify(ticket, newSL, curTP);
        }
     }
   else // SELL
     {
      double profitDist = openPrice - curPrice;
      if(profitDist >= slDist * 1.5 && (curSL > openPrice || curSL == 0))
        {
         double newSL = NormalizeDouble(openPrice - beBufferPts * point, digits);
         return trade.PositionModify(ticket, newSL, curTP);
        }
     }
   return false;
  }

#endif // GOLDCLONE_INCLUDES_MQH
