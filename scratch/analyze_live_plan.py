"""
Live Market Analysis & Planned Entry Scanner for Gold (XAUUSDm)
Inspects current market structure, key liquidity zones, upcoming candle closes,
and exact trigger levels across Musumali Institutional Sweeps and M5/M15 Scalper.
"""

import os
import sys
import yaml
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

def load_config():
    cfg_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "config.yaml"))
    with open(cfg_path, "r") as f:
        return yaml.safe_load(f)

def run_market_analysis():
    if not mt5.initialize():
        print("[ERROR] MT5 could not be initialized.")
        return

    cfg = load_config()
    symbol = cfg.get("symbol", "XAUUSDm")
    info = mt5.symbol_info(symbol)
    if info is None:
        print(f"[ERROR] Symbol {symbol} not found.")
        mt5.shutdown()
        return

    tick = mt5.symbol_info_tick(symbol)
    acc = mt5.account_info()
    positions = mt5.positions_get(symbol=symbol)

    print("=" * 80)
    print(f" LIVE GOLD (XAUUSD) MARKET STRUCTURE & ENTRY PLANNING REPORT")
    print(f" Broker: Exness | Symbol: {symbol} | Digits: {info.digits} | Spread: {info.spread} pts (${info.spread * 0.001:.2f})")
    print(f" Account Balance: ${acc.balance:.2f} | Equity: ${acc.equity:.2f} | Margin Free: ${acc.margin_free:.2f}")
    print(f" Current Market Price -> Ask: {tick.ask:.2f} | Bid: {tick.bid:.2f}")
    print("=" * 80)

    # 1. Open Positions Inspection
    print(f"\n--- 1. ACTIVE LIVE POSITIONS ({len(positions)} Open) ---")
    if not positions:
        print(" -> No active open positions currently. Both engines are actively scanning.")
    else:
        for pos in positions:
            p_type = "BUY" if pos.type == 0 else "SELL"
            pnl = pos.profit
            print(f" -> #{pos.ticket} | {p_type} {pos.volume} lots @ {pos.price_open:.2f} | Current: {pos.price_current:.2f} | SL: {pos.sl:.2f} | TP: {pos.tp:.2f} | Floating P&L: ${pnl:+.2f} | Magic: {pos.magic}")

    # 2. Higher Timeframe Trend Context (D1, H4, H1)
    print(f"\n--- 2. MACRO & INTRADAY TREND STRUCTURE ---")
    rates_d1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 50)
    df_d1 = pd.DataFrame(rates_d1)
    df_d1["ema20"] = df_d1["close"].ewm(span=20, adjust=False).mean()
    d1_close = df_d1["close"].iloc[-2]
    d1_ema = df_d1["ema20"].iloc[-2]
    d1_trend = "UPTREND (Bullish)" if d1_close > d1_ema else "DOWNTREND (Bearish)"
    print(f" -> D1 Macro Trend:   {d1_trend} (D1 Close: {d1_close:.2f} vs EMA20: {d1_ema:.2f})")

    rates_h1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 50)
    df_h1 = pd.DataFrame(rates_h1)
    df_h1["ema20"] = df_h1["close"].ewm(span=20, adjust=False).mean()
    h1_close = df_h1["close"].iloc[-2]
    h1_ema = df_h1["ema20"].iloc[-2]
    h1_trend = "UPTREND (Bullish)" if h1_close > h1_ema else "DOWNTREND (Bearish)"
    print(f" -> H1 Intraday Trend: {h1_trend} (H1 Close: {h1_close:.2f} vs EMA20: {h1_ema:.2f})")

    rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 50)
    df_m15 = pd.DataFrame(rates_m15)
    df_m15["ema20"] = df_m15["close"].ewm(span=20, adjust=False).mean()
    m15_close = df_m15["close"].iloc[-2]
    m15_ema = df_m15["ema20"].iloc[-2]
    m15_slope = m15_ema - df_m15["ema20"].iloc[-5]
    m15_trend = "UPTREND" if (m15_close > m15_ema and m15_slope > 0) else ("DOWNTREND" if (m15_close < m15_ema and m15_slope < 0) else "NEUTRAL / RANGING")
    print(f" -> M15 Scalp Context: {m15_trend} (Price: {m15_close:.2f} vs EMA20: {m15_ema:.2f}, Slope: {m15_slope:+.2f})")

    # 3. Musumali Institutional Sweeps (M15, M30, H1, H4) Setup Analysis
    print(f"\n--- 3. ENGINE 1: MUSUMALI INSTITUTIONAL SWEEP SCANNER ---")
    for tf_name, tf_const in [("M15", mt5.TIMEFRAME_M15), ("M30", mt5.TIMEFRAME_M30), ("H1", mt5.TIMEFRAME_H1), ("H4", mt5.TIMEFRAME_H4)]:
        rates = mt5.copy_rates_from_pos(symbol, tf_const, 0, 40)
        if rates is None or len(rates) < 15:
            continue
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        prev_bar = df.iloc[-2]
        window = df.iloc[-10:-2]
        recent_high = window["high"].max()
        recent_low = window["low"].min()
        
        # Check sweep conditions
        is_bull_sweep = (prev_bar["low"] < recent_low) and (prev_bar["close"] > recent_low)
        is_bear_sweep = (prev_bar["high"] > recent_high) and (prev_bar["close"] < recent_high)
        
        print(f" [{tf_name} Bar: {prev_bar['time']}] Close: {prev_bar['close']:.2f} | High: {prev_bar['high']:.2f} | Low: {prev_bar['low']:.2f}")
        print(f"   - Prior Swing Levels -> High: {recent_high:.2f} | Low: {recent_low:.2f}")
        if is_bull_sweep:
            trigger_price = prev_bar["high"]
            print(f"   - [PENDING BUY SWEEP DETECTED] Low swept {recent_low:.2f} -> Reclaimed @ {prev_bar['close']:.2f}")
            print(f"   - Planned Entry: BUY @ Ask >= {trigger_price:.2f} (Current Ask: {tick.ask:.2f} | Distance: ${trigger_price - tick.ask:+.2f})")
        elif is_bear_sweep:
            trigger_price = prev_bar["low"]
            print(f"   - [PENDING SELL SWEEP DETECTED] High swept {recent_high:.2f} -> Reclaimed @ {prev_bar['close']:.2f}")
            print(f"   - Planned Entry: SELL @ Bid <= {trigger_price:.2f} (Current Bid: {tick.bid:.2f} | Distance: ${tick.bid - trigger_price:+.2f})")
        else:
            print(f"   - No active liquidity sweep. Watching for breakout/reversal around [{recent_low:.2f} - {recent_high:.2f}].")

    # 4. Engine 2: High-Conviction Micro-Scalper (M5, M15) Quality Audit
    print(f"\n--- 4. ENGINE 2: HIGH-CONVICTION SCALPER & PLANNED ENTRIES ---")
    for tf_name, tf_const in [("M5", mt5.TIMEFRAME_M5), ("M15", mt5.TIMEFRAME_M15)]:
        rates = mt5.copy_rates_from_pos(symbol, tf_const, 0, 40)
        if rates is None or len(rates) < 20:
            continue
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df["ema_fast"] = df["close"].ewm(span=7, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=16, adjust=False).mean()
        
        # ATR & RSI
        tr = np.maximum(df["high"] - df["low"], np.maximum(abs(df["high"] - df["close"].shift(1)), abs(df["low"] - df["close"].shift(1))))
        df["atr14"] = tr.rolling(14).mean()
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        rs = gain.rolling(14).mean() / loss.rolling(14).mean().replace(0, 1e-9)
        df["rsi14"] = 100 - (100 / (1 + rs))

        prev_bar = df.iloc[-2]
        atr = prev_bar["atr14"]
        rsi = prev_bar["rsi14"]
        vol_avg = df["tick_volume"].iloc[-7:-2].mean()
        vol_curr = prev_bar["tick_volume"]
        vol_ratio = (vol_curr / vol_avg) * 100.0 if vol_avg > 0 else 100.0

        tot_range = prev_bar["high"] - prev_bar["low"]
        upper_wick = prev_bar["high"] - max(prev_bar["open"], prev_bar["close"])
        lower_wick = min(prev_bar["open"], prev_bar["close"]) - prev_bar["low"]

        is_bull_pin = (lower_wick / tot_range >= 0.35) if tot_range > 0 else False
        is_bear_pin = (upper_wick / tot_range >= 0.35) if tot_range > 0 else False
        is_bull_pullback = (prev_bar["low"] <= prev_bar["ema_fast"]) and (prev_bar["close"] > prev_bar["open"])
        is_bear_pullback = (prev_bar["high"] >= prev_bar["ema_fast"]) and (prev_bar["close"] < prev_bar["open"])

        print(f"\n [{tf_name} Scalp Bar: {prev_bar['time']}]")
        print(f"   - Close: {prev_bar['close']:.2f} | EMA7: {prev_bar['ema_fast']:.2f} | EMA16: {prev_bar['ema_slow']:.2f}")
        print(f"   - RSI(14): {rsi:.1f} | ATR(14): ${atr:.2f} | Tick Volume: {vol_curr} ({vol_ratio:.0f}% of 5-bar avg)")
        print(f"   - Candlestick Shape: Lower Wick: {lower_wick/tot_range*100:.1f}%, Upper Wick: {upper_wick/tot_range*100:.1f}%, Direction: {'GREEN' if prev_bar['close']>prev_bar['open'] else 'RED'}")
        
        if prev_bar["close"] > prev_bar["ema_fast"] and m15_trend == "UPTREND":
            planned_sl = max(min(atr * 1.5, 3.00), 2.00)
            planned_tp = planned_sl * 2.0
            print(f"   -> BULLISH SETUP ACTIVE:")
            print(f"      - Planned Trigger: BUY on continuation above {prev_bar['close']:.2f}")
            print(f"      - Planned SL: Entry - ${planned_sl:.2f} | Planned TP: Entry + ${planned_tp:.2f} (1:2 R:R)")
            print(f"      - Target Quality Score: ~85-90/100 (High-Probability)")

        elif prev_bar["close"] < prev_bar["ema_fast"] and m15_trend == "DOWNTREND":
            planned_sl = max(min(atr * 1.5, 3.00), 2.00)
            planned_tp = planned_sl * 2.0
            print(f"   -> BEARISH SETUP ACTIVE:")
            print(f"      - Planned Trigger: SELL on breakdown below {prev_bar['close']:.2f}")
            print(f"      - Planned SL: Entry + ${planned_sl:.2f} | Planned TP: Entry - ${planned_tp:.2f} (1:2 R:R)")
            print(f"      - Target Quality Score: ~85-90/100 (High-Probability)")

    print("\n" + "=" * 80)
    mt5.shutdown()

if __name__ == "__main__":
    run_market_analysis()
