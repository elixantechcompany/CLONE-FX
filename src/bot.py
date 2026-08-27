"""
Main Dual-Engine Bot Orchestrator for Gold (XAUUSD)
Orchestrates simultaneously:
  Engine 1: Musumali Institutional Liquidity Sweeps (M5, M15, M30, H1) [Magic: 999888]
  Engine 2: High-Frequency Micro-Scalper (M1, M5) [Magic: 888777]

Features:
  1. Simultaneous Aggressive Multi-Engine Trade Execution.
  2. 4-Tier Dynamic Profit Management (Break-Even Lock, Trailing Stop, Retracement Guard, Dollar Target Closer).
  3. Dynamic ATR Risk Management & Circuit Breakers.
  4. Auto-Reconnection & 24/7 Resilience.
"""

import logging
import os
from logging.handlers import RotatingFileHandler
import time
import datetime
import json
from typing import List, Optional, Set, Tuple
import pandas as pd
import MetaTrader5 as mt5
import yaml
from dotenv import load_dotenv

from src.connection import MT5Connector
from src.execution import OrderExecutor
from src.m1_scalper import M1Scalper
from src.risk_manager import RiskManager
from src.strategy import MusumaliStrategy


def setup_logger(log_level: str = "INFO") -> logging.Logger:
    """Configures structured console and rotating file logging."""
    os.makedirs("logs", exist_ok=True)
    logger = logging.getLogger("GoldBot")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    if not logger.handlers:
        c_handler = logging.StreamHandler()
        c_format = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        c_handler.setFormatter(c_format)
        logger.addHandler(c_handler)

        f_handler = RotatingFileHandler("logs/trading_bot.log", maxBytes=10 * 1024 * 1024, backupCount=5)
        f_format = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        f_handler.setFormatter(f_format)
        logger.addHandler(f_handler)

    return logger


class GoldTradingBot:
    def __init__(self, config_path: str = "config/config.yaml"):
        load_dotenv(dotenv_path="config/.env")
        load_dotenv()

        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)

        self.logger = setup_logger(self.config.get("system", {}).get("log_level", "INFO"))
        self.poll_interval = self.config.get("system", {}).get("poll_interval_seconds", 1)
        self.heartbeat_interval = self.config.get("system", {}).get("heartbeat_interval_seconds", 60)

        # Limits & Harmony Rules (Fix 10 & Fix 12)
        self.harmony_cfg = self.config.get("harmony_rules", {})
        self.magic_musumali = self.config.get("musumali_strategy", {}).get("magic_number", 2001)
        self.magic_scalper = self.config.get("m1_scalper", {}).get("magic_number", 1001)
        self.total_max_open = self.harmony_cfg.get("total_max_open_positions", 5)
        self.max_musumali = self.harmony_cfg.get("max_musumali_positions", 2)
        self.max_scalper = self.harmony_cfg.get("max_scalper_positions", 3)
        self.prevent_opposing = self.harmony_cfg.get("prevent_opposing_trades", False)
        self.cooldown_sec = self.harmony_cfg.get("cooldown_seconds_per_trade", 0)
        self.fixed_lot = self.config.get("risk_management", {}).get("fixed_lot_size", 0.01)

        # Persistent Signal De-Duplication Lock (Ensures 1 trade per unique setup candle across restarts)
        self.traded_candles_file = "data/traded_candles.json"
        self.traded_candle_ids: Set[str] = set()
        self._load_traded_candles()
        self.last_trade_execution_time = 0.0

        # Initialize Submodules
        self.connector = MT5Connector()
        self.risk_manager = RiskManager(self.config, self.connector)
        self.executor = OrderExecutor(self.config, risk_manager=self.risk_manager)
        self.musumali_strategy = MusumaliStrategy(self.config)
        self.m1_scalper = M1Scalper(self.config)

        self.active_symbol: Optional[str] = None
        self.is_running = False
        self.last_heartbeat_time = 0.0
        self.last_logged_scalp_bar: Optional[str] = None
        self.last_logged_h1_bar: Optional[str] = None

    def _load_traded_candles(self):
        """Loads previously traded candle IDs from disk to prevent re-entering on bot restarts."""
        try:
            if os.path.exists(self.traded_candles_file):
                with open(self.traded_candles_file, "r") as f:
                    data = json.load(f)
                    self.traded_candle_ids = set(data.get("candle_ids", []))
                    self.logger.info(f"Loaded {len(self.traded_candle_ids)} previously traded candle IDs from disk.")
        except Exception as e:
            self.logger.warning(f"Could not load traded candles from disk: {e}")

    def _save_traded_candles(self):
        """Saves traded candle IDs to disk."""
        try:
            os.makedirs(os.path.dirname(self.traded_candles_file), exist_ok=True)
            with open(self.traded_candles_file, "w") as f:
                json.dump({"candle_ids": list(self.traded_candle_ids)}, f)
        except Exception as e:
            self.logger.warning(f"Could not persist traded candles: {e}")

    def start(self):
        """Starts the Dual-Engine 24/7 trading bot with auto-reconnection."""
        self.logger.info("=" * 70)
        self.logger.info("   STARTING AGGRESSIVE DUAL-ENGINE GOLD (XAUUSD) 24/7 BOT")
        self.logger.info(f"   Engine 1: Musumali Institutional Sweeps (Magic: {self.magic_musumali}) [Max: {self.max_musumali}]")
        self.logger.info(f"   Engine 2: High-Frequency Micro-Scalper (Magic: {self.magic_scalper}) [Max: {self.max_scalper}]")
        self.logger.info("   Profit Closer: Multi-Tier Trailing Stop + Unified +1R Breakeven Engine")
        self.logger.info("=" * 70)

        # Auto-connect loop
        while not self.connector.initialize():
            self.logger.warning("Waiting for MT5 terminal connection... Retrying in 5 seconds.")
            time.sleep(5)

        candidates = self.config.get("symbols", {}).get("candidates", ["XAUUSDm", "XAUUSD"])
        self.active_symbol = self.connector.resolve_symbol(candidates)
        if not self.active_symbol:
            self.logger.error("Could not find a valid Gold symbol. Halting execution.")
            self.connector.shutdown()
            return

        self.is_running = True
        musumali_tfs = [tf[0] for tf in self.musumali_strategy.scan_timeframes]
        scalper_tfs = self.m1_scalper.timeframes
        sig_only = self.musumali_strategy.strat_cfg.get("signal_only_mode", True)
        musumali_mode_str = "SIGNAL-ONLY (Dry Run / Validation Mode)" if sig_only else "LIVE ORDER EXECUTION"

        self.logger.info(
            f"Bot Active 24/7! Monitoring {self.active_symbol} | Max Concurrency: {self.total_max_open} positions "
            f"(Musumali #{self.magic_musumali}: {self.max_musumali}, Scalp #{self.magic_scalper}: {self.max_scalper})"
        )
        self.logger.info(
            f"[MODULE TIMEFRAME ISOLATION AUDIT FIX 8] "
            f"Engine 1 (Musumali_Sweep, Magic #{self.magic_musumali}) -> Higher Timeframes: {musumali_tfs} [{musumali_mode_str}] | "
            f"Engine 2 (M1_Scalp, Magic #{self.magic_scalper}) -> Scalp Timeframe: {scalper_tfs} [LIVE ORDER EXECUTION]"
        )

        try:
            while self.is_running:
                try:
                    self._tick_cycle()
                except Exception as e:
                    self.logger.exception(f"Error during tick cycle: {e}")
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            self.logger.info("Shutdown requested by user (Ctrl+C).")
        finally:
            self.stop()

    def _audit_opposing_exposure(
        self,
        module_name: str,
        new_sig: str,
        new_lots: float,
        other_positions: List[dict],
        all_positions: List[dict],
    ) -> Tuple[bool, str]:
        """
        Fix 11: Monitors, audits, and logs directional conflicts between M1_Scalp and Musumali_Sweep.
        Provides full visibility into net exposure at all times without silent conflicts.
        """
        opposing_type = "SELL" if new_sig == "BUY" else "BUY"
        opposing_positions = [p for p in other_positions if p["type"] == opposing_type]

        total_long = sum(p["volume"] for p in all_positions if p["type"] == "BUY") + (new_lots if new_sig == "BUY" else 0.0)
        total_short = sum(p["volume"] for p in all_positions if p["type"] == "SELL") + (new_lots if new_sig == "SELL" else 0.0)
        net_delta = round(total_long - total_short, 2)

        if opposing_positions:
            other_vol = sum(p["volume"] for p in opposing_positions)
            self.logger.warning(
                f"[MODULE OPPOSITION AUDIT FIX 11] {module_name} {new_sig} ({new_lots:.2f} lots) triggered while opposite "
                f"positions are open ({other_vol:.2f} lots {opposing_type})! "
                f"Net Exposure: {total_long:.2f}L / {total_short:.2f}S (Net Delta: {net_delta:+.2f} lots)"
            )
            max_conflict_lots = self.harmony_cfg.get("max_opposing_lot_exposure", 0.05)
            prevent_opposing = self.harmony_cfg.get("prevent_opposing_trades", False)
            if prevent_opposing or abs(net_delta) > max_conflict_lots:
                return False, f"Opposing exposure limit exceeded ({other_vol:.2f} lots opposing, Net Delta: {net_delta:+.2f})"

        return True, "OK"

    def _tick_cycle(self):
        """Unified tick execution: manages active profits, checks circuit breakers, and runs both engines."""
        acc = self.connector.get_account_summary()
        if not acc:
            return

        equity = acc["equity"]
        now = time.time()

        # Step 1: Manage active open positions (Break-Even, Trailing Stop, Retracement Guard)
        all_positions = self.executor.get_open_positions(self.active_symbol)
        self.executor.manage_active_positions(self.active_symbol)

        musumali_positions = [p for p in all_positions if p["magic"] == self.executor.magic_musumali]
        scalper_positions = [p for p in all_positions if p["magic"] == self.executor.magic_scalper]

        # Step 1b: Check Opposite Momentum Reversals on Active Positions (Cuts early when market turns)
        for pos in scalper_positions:
            is_reversed, rev_msg = self.m1_scalper.check_momentum_reversal(self.active_symbol, pos["type"])
            if is_reversed:
                self.logger.info(
                    f"[OPPOSITE MOMENTUM EXIT] Scalp #{pos['ticket']} ({pos['type']}) closing early: {rev_msg} (Profit: ${pos['profit']:+.2f})"
                )
                self.executor.close_position(pos["ticket"], self.active_symbol, reason=f"MomentumReversal_{pos['type']}")

        # Evaluate Daily Trend Bias for Heartbeat & Diagnostic
        daily_trend, trend_reason = self.musumali_strategy.get_daily_market_trend(self.active_symbol)

        # Periodic Heartbeat, Per-Module P&L & Funnel Audit Update (Fix 13)
        if (now - self.last_heartbeat_time) >= self.heartbeat_interval:
            self.last_heartbeat_time = now
            tick = mt5.symbol_info_tick(self.active_symbol)
            bid_str = f"{tick.bid:.2f}" if tick else "N/A"
            ask_str = f"{tick.ask:.2f}" if tick else "N/A"
            perf = self.risk_manager.get_module_performance_summary()
            cb_status = self.risk_manager.get_circuit_breaker_status()
            self.logger.info(
                f"[Heartbeat 24/7] {self.active_symbol} Ask: {ask_str} | Bid: {bid_str} | "
                f"Open Trades: {len(all_positions)}/{self.total_max_open} "
                f"(Musumali #{self.magic_musumali}: {len(musumali_positions)}/{self.max_musumali}, Scalp #{self.magic_scalper}: {len(scalper_positions)}/{self.max_scalper}) | "
                f"Equity: ${equity:.2f} | Daily Trend Gate: {daily_trend}"
            )
            self.logger.info(f"[CIRCUIT BREAKER STATUS FIX 18] {cb_status}")
            self.logger.info(
                f"[DAILY MODULE P&L AUDIT FIX 13] Scalp P&L Today: ${perf['scalp_pnl']:+.2f} ({perf['scalp_trades']} trades, {perf['scalp_wins']}W) | "
                f"Musumali P&L Today: ${perf['musumali_pnl']:+.2f} ({perf['musumali_trades']} trades, {perf['musumali_wins']}W) | "
                f"Total Day P&L: ${perf['total_day_pnl']:+.2f}"
            )
            # Fix 3: Instrument & Log 4-Stage Entry Filter Funnel
            self.musumali_strategy.log_funnel_audit()

        # Circuit Breakers & Daily Limits
        can_trade, breaker_reason = self.risk_manager.check_circuit_breakers(equity)

        # Spread Safety Check
        spread_ok, current_spread = self.risk_manager.check_spread_allowed(self.active_symbol)
        spread_reason = f"Spread {current_spread} > max allowed" if not spread_ok else "OK"

        # =====================================================================
        # ENGINE 1: Musumali Institutional Sweeps (H1, H4) [Magic: 2001]
        # =====================================================================
        if self.musumali_strategy.strat_cfg.get("enabled", True):
            in_cd_m, cd_msg_m = self.risk_manager.is_module_in_cooldown(self.executor.magic_musumali)
            
            rates_h1 = mt5.copy_rates_from_pos(self.active_symbol, mt5.TIMEFRAME_H1, 0, 3)
            h1_bar_time = str(pd.to_datetime(rates_h1[-2]["time"], unit="s")) if (rates_h1 is not None and len(rates_h1) >= 2) else None

            t_sig_start = time.time()
            sig, entry, sl, tp, candle_id, zone_id, setup_reason = self.musumali_strategy.generate_signal(self.active_symbol)
            t_sig_done = time.time()

            # Fix 20: Mandatory Decision Logging on Every H1 Candle Close
            if h1_bar_time and h1_bar_time != self.last_logged_h1_bar:
                self.last_logged_h1_bar = h1_bar_time
                if not can_trade:
                    self.logger.info(
                        f"[MUSUMALI HTF CANDLE DECISION FIX 20] H1 Bar: {h1_bar_time} | Daily Gate: {daily_trend} | "
                        f"Status: HALTED | Action: SKIPPED | Reason: {breaker_reason}"
                    )
                elif not spread_ok:
                    self.logger.info(
                        f"[MUSUMALI HTF CANDLE DECISION FIX 20] H1 Bar: {h1_bar_time} | Daily Gate: {daily_trend} | "
                        f"Status: SPREAD_HIGH | Action: SKIPPED | Reason: {spread_reason}"
                    )
                elif in_cd_m:
                    self.logger.info(
                        f"[MUSUMALI HTF CANDLE DECISION FIX 20] H1 Bar: {h1_bar_time} | Daily Gate: {daily_trend} | "
                        f"Status: PAUSED | Action: SKIPPED | Reason: {cd_msg_m}"
                    )
                elif sig:
                    self.logger.info(
                        f"[MUSUMALI HTF CANDLE DECISION FIX 20] H1 Bar: {h1_bar_time} | Daily Gate: {daily_trend} | "
                        f"Status: ACTIVE | Action: VALID_SIGNAL ({sig}) | Reason: {setup_reason}"
                    )
                else:
                    self.logger.info(
                        f"[MUSUMALI HTF CANDLE DECISION FIX 20] H1 Bar: {h1_bar_time} | Daily Gate: {daily_trend} | "
                        f"Status: ACTIVE | Action: SKIPPED | Reason: No H1 liquidity sweep or confirmation break"
                    )

            if can_trade and spread_ok and not in_cd_m and sig in ("BUY", "SELL") and candle_id:
                if candle_id in self.traded_candle_ids:
                    pass  # Already executed on this specific candle
                elif len(all_positions) >= self.total_max_open:
                    self.logger.info(
                        f"[SIGNAL SKIPPED FIX 6] Setup {candle_id} ({sig}) valid but skipped — "
                        f"reason: Max total concurrency ({len(all_positions)}/{self.total_max_open}) reached."
                    )
                elif len(musumali_positions) >= self.max_musumali:
                    self.logger.info(
                        f"[SIGNAL SKIPPED FIX 6] Setup {candle_id} ({sig}) valid but skipped — "
                        f"reason: Max Musumali positions ({len(musumali_positions)}/{self.max_musumali}) reached."
                    )
                else:
                    zone_allowed, zone_msg = self.risk_manager.is_zone_allowed(zone_id)
                    if not zone_allowed:
                        self.logger.info(
                            f"[SIGNAL SKIPPED FIX 6] Setup {candle_id} ({sig}) valid but skipped — "
                            f"reason: {zone_msg}"
                        )
                    else:
                        signal_only = self.musumali_strategy.strat_cfg.get("signal_only_mode", False)
                        if signal_only:
                            self.traded_candle_ids.add(candle_id)
                            self._save_traded_candles()
                            self.logger.info(
                                f"[MUSUMALI SIGNAL-ONLY AUDIT FIX 9 (DRY-RUN)] Generated valid {sig} setup on H1/H4 ({candle_id}) @ {entry:.2f} | "
                                f"SL: {sl:.2f} | TP: {tp:.2f} | Daily Trend Gate: {daily_trend} | Reason: {setup_reason}"
                            )
                        else:
                            # Fix 7 & 12: Dynamic Position Sizing with Shared Risk Budget Awareness
                            lot_size = self.risk_manager.calculate_lot_size(
                                self.active_symbol, entry, sl, equity, open_trades_count=len(all_positions)
                            )

                            # Fix 11: Opposing Trade Visibility & Exposure Check
                            opp_ok, opp_msg = self._audit_opposing_exposure(
                                "Musumali_Sweep", sig, lot_size, scalper_positions, all_positions
                            )
                            if not opp_ok:
                                self.logger.info(f"[SIGNAL SKIPPED FIX 11] Setup {candle_id} ({sig}) skipped — {opp_msg}")
                            else:
                                # Fix 4: Immediate execution with zero artificial delay
                                t_send_start = time.time()
                                ticket = self.executor.execute_market_order(
                                    symbol=self.active_symbol,
                                    order_type=sig,
                                    volume=lot_size,
                                    sl=sl,
                                    tp=tp,
                                    magic=self.executor.magic_musumali,
                                    comment="Musumali_Sweep",
                                    zone_id=zone_id,
                                )
                                t_send_done = time.time()

                                if ticket:
                                    self.traded_candle_ids.add(candle_id)
                                    self._save_traded_candles()
                                    self.last_trade_execution_time = t_send_done
                                    self.risk_manager.record_trade_placed(magic=self.executor.magic_musumali)
                                    latency_ms = (t_send_done - t_sig_done) * 1000.0
                                    self.logger.info(
                                        f"[EXECUTION SPEED FIX 4] Signal -> Order placed in {latency_ms:.1f}ms with 0s delay."
                                    )
                                    self.logger.info(
                                        f"[TREND AUDIT ENTRY FIX 2] Placed {sig} #{ticket} under Daily Trend Gate: {daily_trend} ({trend_reason})"
                                    )
                                    self.logger.info(f"[ENGINE 1 EXECUTED] #{ticket} ({lot_size} lots, Magic: {self.executor.magic_musumali}) | {setup_reason}")

        # Refresh positions before Engine 2
        all_positions = self.executor.get_open_positions(self.active_symbol)
        scalper_positions = [p for p in all_positions if p["magic"] == self.executor.magic_scalper]
        musumali_positions = [p for p in all_positions if p["magic"] == self.executor.magic_musumali]

        # =====================================================================
        # ENGINE 2: High-Frequency Micro-Scalper (M1) [Magic: 1001]
        # =====================================================================
        if self.m1_scalper.enabled:
            in_cd_s, cd_msg_s = self.risk_manager.is_module_in_cooldown(self.executor.magic_scalper)
            require_daily_align = self.m1_scalper.scalp_cfg.get("require_daily_trend_alignment", False)
            sig_s, entry_s, sl_s, tp_s, candle_id_s, reason_s, trend_context_s, latest_bar_time, no_trade_reason = self.m1_scalper.generate_scalp_signal(self.active_symbol)

            # Fix 19 & Fix 20: Mandatory Decision Logging on Every M1 Candle Close
            if latest_bar_time and latest_bar_time != self.last_logged_scalp_bar:
                self.last_logged_scalp_bar = latest_bar_time
                if not can_trade:
                    self.logger.info(
                        f"[M1 SCALP CANDLE DECISION FIX 20] M1 Bar: {latest_bar_time} | M15 Trend: {trend_context_s} | "
                        f"Status: HALTED | Action: SKIPPED | Reason: {breaker_reason}"
                    )
                elif not spread_ok:
                    self.logger.info(
                        f"[M1 SCALP CANDLE DECISION FIX 20] M1 Bar: {latest_bar_time} | M15 Trend: {trend_context_s} | "
                        f"Status: SPREAD_HIGH | Action: SKIPPED | Reason: {spread_reason}"
                    )
                elif in_cd_s:
                    self.logger.info(
                        f"[M1 SCALP CANDLE DECISION FIX 20] M1 Bar: {latest_bar_time} | M15 Trend: {trend_context_s} | "
                        f"Status: PAUSED | Action: SKIPPED | Reason: {cd_msg_s}"
                    )
                elif sig_s:
                    self.logger.info(
                        f"[M1 SCALP CANDLE DECISION FIX 20] M1 Bar: {latest_bar_time} | M15 Trend: {trend_context_s} | "
                        f"Status: ACTIVE | Action: TRADE_TRIGGERED ({sig_s}) | Reason: {reason_s}"
                    )
                else:
                    self.logger.info(
                        f"[M1 SCALP CANDLE DECISION FIX 20] M1 Bar: {latest_bar_time} | M15 Trend: {trend_context_s} | "
                        f"Status: ACTIVE | Action: SKIPPED | Reason: {no_trade_reason}"
                    )

            if can_trade and spread_ok and not in_cd_s:
                # Check if signal is allowed (Bidirectional or Trend-Aligned)
                signal_allowed = False
                if sig_s in ("BUY", "SELL"):
                    if not require_daily_align:
                        # Bidirectional M1 scalping with M15 trend awareness (Fix 16)
                        signal_allowed = True
                    elif (daily_trend == "UPTREND" and sig_s == "BUY") or (daily_trend == "DOWNTREND" and sig_s == "SELL"):
                        signal_allowed = True

                if signal_allowed and candle_id_s:
                    if candle_id_s in self.traded_candle_ids:
                        pass
                    elif len(all_positions) >= self.total_max_open:
                        self.logger.info(
                            f"[SIGNAL SKIPPED FIX 6] Scalp {candle_id_s} ({sig_s}) valid but skipped — "
                            f"reason: Max total concurrency ({len(all_positions)}/{self.total_max_open}) reached."
                        )
                    elif len(scalper_positions) >= self.max_scalper:
                        self.logger.info(
                            f"[SIGNAL SKIPPED FIX 6] Scalp {candle_id_s} ({sig_s}) valid but skipped — "
                            f"reason: Max Scalper positions ({len(scalper_positions)}/{self.max_scalper}) reached."
                        )
                    else:
                        # Fix 7 & 12: Dynamic Position Sizing with Shared Risk Budget Awareness
                        lot_size_s = self.risk_manager.calculate_lot_size(
                            self.active_symbol, entry_s, sl_s, equity, open_trades_count=len(all_positions)
                        )

                        # Fix 11: Opposing Trade Visibility & Exposure Check
                        opp_ok_s, opp_msg_s = self._audit_opposing_exposure(
                            "M1_Scalp", sig_s, lot_size_s, musumali_positions, all_positions
                        )
                        if not opp_ok_s:
                            self.logger.info(f"[SIGNAL SKIPPED FIX 11] Scalp {candle_id_s} ({sig_s}) skipped — {opp_msg_s}")
                        else:
                            t_send_start = time.time()
                            ticket_s = self.executor.execute_market_order(
                                symbol=self.active_symbol,
                                order_type=sig_s,
                                volume=lot_size_s,
                                sl=sl_s,
                                tp=tp_s,
                                magic=self.executor.magic_scalper,
                                comment="M1_Scalp",
                                zone_id=None,
                            )
                            t_send_done = time.time()

                            if ticket_s:
                                self.traded_candle_ids.add(candle_id_s)
                                self._save_traded_candles()
                                self.last_trade_execution_time = t_send_done
                                self.risk_manager.record_trade_placed(magic=self.executor.magic_scalper)
                                latency_ms = (t_send_done - t_send_start) * 1000.0
                                self.logger.info(
                                    f"[EXECUTION SPEED FIX 4] Scalp Order #{ticket_s} placed in {latency_ms:.1f}ms with 0s delay."
                                )
                                self.logger.info(
                                    f"[M1 SCALP TREND AUDIT FIX 16] Placed {sig_s} #{ticket_s} ({lot_size_s} lots, Magic: {self.executor.magic_scalper}) under Trend Context: {trend_context_s}"
                                )
                                self.logger.info(f"[ENGINE 2 EXECUTED] #{ticket_s} ({lot_size_s} lots, Magic: {self.executor.magic_scalper}) | {reason_s}")

    def stop(self):
        """Cleans up and terminates the bot safely."""
        self.is_running = False
        self.connector.shutdown()
        self.logger.info("Gold Trading Bot stopped safely.")

