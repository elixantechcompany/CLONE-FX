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
from src.notifier import Notifier
from src.dashboard import DashboardExporter


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
        self.is_manually_paused = False

        # Initialize Submodules
        self.connector = MT5Connector()
        self.notifier = Notifier(self.config)
        self.risk_manager = RiskManager(self.config, self.connector)
        self.executor = OrderExecutor(self.config, risk_manager=self.risk_manager)
        self.musumali_strategy = MusumaliStrategy(self.config)
        self.m1_scalper = M1Scalper(self.config)
        self.dashboard_exporter = DashboardExporter(self.config)

        self.active_symbol: Optional[str] = None
        self.is_running = False
        self.last_quick_heartbeat_time = 0.0
        self.last_comprehensive_heartbeat_time = 0.0
        self.quick_heartbeat_interval = self.config.get("system", {}).get("quick_heartbeat_interval_seconds", 60)
        self.comprehensive_heartbeat_interval = self.config.get("system", {}).get("heartbeat_interval_seconds", 900)
        self.last_logged_scalp_bar: Optional[str] = None
        self.last_logged_h1_bar: Optional[str] = None

    def _load_traded_candles(self):
        """Loads previously traded candle IDs from disk, keeping only recent active session IDs."""
        try:
            if os.path.exists(self.traded_candles_file):
                with open(self.traded_candles_file, "r") as f:
                    data = json.load(f)
                    # Keep only recent 20 candle IDs to prevent stale blocks
                    raw_ids = data.get("candle_ids", [])
                    self.traded_candle_ids = set(raw_ids[-20:])
                    self.logger.info(f"Loaded {len(self.traded_candle_ids)} recent traded candle IDs from disk.")
        except Exception as e:
            self.logger.warning(f"Could not load traded candles from disk: {e}")

    def _save_traded_candles(self):
        """Saves traded candle IDs to disk."""
        try:
            os.makedirs(os.path.dirname(self.traded_candles_file), exist_ok=True)
            with open(self.traded_candles_file, "w") as f:
                json.dump({"candle_ids": list(self.traded_candle_ids)[-20:]}, f)
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

        # Start interactive Telegram remote control listener
        self.notifier.start_command_poller(self)

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
        Fix 11 & Fix 33: Audits directional conflicts. A new opposite-direction signal does NOT
        close existing positions; existing positions are left running and the new signal is evaluated independently.
        """
        opposing_type = "SELL" if new_sig == "BUY" else "BUY"
        opposing_positions = [p for p in all_positions if p["type"] == opposing_type]

        total_long = sum(p["volume"] for p in all_positions if p["type"] == "BUY") + (new_lots if new_sig == "BUY" else 0.0)
        total_short = sum(p["volume"] for p in all_positions if p["type"] == "SELL") + (new_lots if new_sig == "SELL" else 0.0)
        net_delta = round(total_long - total_short, 2)

        if opposing_positions:
            other_vol = sum(p["volume"] for p in opposing_positions)
            opp_tickets = [str(p["ticket"]) for p in opposing_positions]
            # Fix 33: Explicit Audit Logging per Directive Part 12
            self.logger.info(
                f"[OPPOSING SIGNAL AUDIT FIX 33] New {new_sig} signal detected while {opposing_type} "
                f"position #{','.join(opp_tickets)} ({other_vol:.2f} lots) open — existing position left running, "
                f"new signal evaluated independently."
            )
            max_conflict_lots = self.harmony_cfg.get("max_opposing_lot_exposure", 0.05)
            prevent_opposing = self.harmony_cfg.get("prevent_opposing_trades", False)
            if prevent_opposing or abs(net_delta) > max_conflict_lots:
                return False, f"Opposing exposure limit reached ({other_vol:.2f} lots opposing, Net Delta: {net_delta:+.2f})"

        return True, "OK"

    def _emit_self_reporting_heartbeat(
        self,
        equity: float,
        acc: dict,
        all_positions: list,
        musumali_positions: list,
        scalper_positions: list,
        daily_trend: str,
        trend_reason: str,
        spread_ok: bool,
        current_spread: int,
        session_name: str,
        in_news: bool,
        news_reason: str,
        can_trade: bool,
        breaker_reason: str,
    ):
        """
        Fix 32: Self-Reporting Heartbeat. Emits a comprehensive periodic diagnostic report
        every 15-30 minutes so market status and setup conditions don't require manual checking.
        """
        now_utc_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        perf = self.risk_manager.get_module_performance_summary()
        cb_status = self.risk_manager.get_circuit_breaker_status()
        tick = mt5.symbol_info_tick(self.active_symbol)
        ask_str = f"{tick.ask:.2f}" if tick else "N/A"
        bid_str = f"{tick.bid:.2f}" if tick else "N/A"

        # Check M15 context
        m15_ctx, m15_reason, m15_slope = self.m1_scalper.get_trend_context(self.active_symbol)

        # Build Status Diagnostics for Engine 1
        e1_status = "ACTIVE"
        e1_diag = "Scanning M15/M30/H1/H4 for liquidity sweep boundaries"
        if not can_trade:
            e1_status = "HALTED"
            e1_diag = breaker_reason
        elif in_news:
            e1_status = "NEWS_BLACKOUT"
            e1_diag = news_reason
        elif not spread_ok:
            e1_status = "SPREAD_FILTER"
            e1_diag = f"Spread {current_spread} pts > max allowed"

        # Build Status Diagnostics for Engine 2
        e2_status = "ACTIVE"
        e2_diag = f"Scanning M1/M5/M15 pullbacks & breakouts (Context: {m15_ctx})"
        if not can_trade:
            e2_status = "HALTED"
            e2_diag = breaker_reason
        elif in_news:
            e2_status = "NEWS_BLACKOUT"
            e2_diag = news_reason

        open_summary = "None (0/2 Active)"
        if all_positions:
            open_items = []
            for p in all_positions:
                open_items.append(f"#{p['ticket']} ({p['type']} {p['volume']} lots @ {p['price_open']:.2f}, P&L: ${p['profit']:+.2f})")
            open_summary = " | ".join(open_items)

        report = (
            f"\n{'='*80}\n"
            f" [SELF-REPORTING HEARTBEAT FIX 32] {now_utc_str} | System 24/7 Healthy\n"
            f"{'-'*80}\n"
            f" 1. Capital & Performance Overview:\n"
            f"    - Balance: ${acc.get('balance', equity):.2f} | Equity: ${equity:.2f} | Margin Free: ${acc.get('margin_free', equity):.2f}\n"
            f"    - Realized P&L Today: ${perf['total_day_pnl']:+.2f} (Scalp: ${perf['scalp_pnl']:+.2f} [{perf['scalp_wins']}W/{perf['scalp_trades']-perf['scalp_wins']}L], Musumali: ${perf['musumali_pnl']:+.2f} [{perf['musumali_wins']}W/{perf['musumali_trades']-perf['musumali_wins']}L])\n"
            f"    - Open Positions: {open_summary}\n"
            f"    - Circuit Breakers: {cb_status}\n\n"
            f" 2. Multi-Timeframe Trend Assessment:\n"
            f"    - D1 Macro Bias:   {daily_trend} ({trend_reason})\n"
            f"    - M15 Scalp Bias:  {m15_ctx} (Slope: {m15_slope:+.2f})\n"
            f"    - Current Market:  Ask {ask_str} / Bid {bid_str} | Spread: {current_spread} pts ({'OK' if spread_ok else 'HIGH'})\n\n"
            f" 3. Module Setup Qualification & Diagnostic Status:\n"
            f"    - Active Session:  {session_name} | Macro News: {'BLACKOUT' if in_news else 'CLEAR'}\n"
            f"    - Engine 1 (Musumali Sweeps #2001): [{e1_status}] -> {e1_diag}\n"
            f"    - Engine 2 (M1/M5 Scalper #1001):   [{e2_status}] -> {e2_diag}\n"
            f"{'='*80}"
        )
        self.logger.info(report)
        self.notifier.notify_heartbeat(report)

    def _handle_connection_loss(self):
        """
        Self-healing connection recovery watchdog.
        When internet or MT5 is disrupted, polls connectivity and reconnects automatically.
        """
        self.logger.warning("[CONNECTION DISRUPTION] Network or MT5 connection dropped! Entering self-healing recovery loop...")
        candidates = self.config.get("symbols", {}).get("candidates", ["XAUUSDm", "XAUUSD"])
        retry_count = 0
        while self.is_running:
            retry_count += 1
            time.sleep(3)
            self.logger.info(f"[CONNECTION RECOVERY] Attempting reconnect #{retry_count}...")
            if self.connector.reconnect(candidate_symbols=candidates):
                self.active_symbol = self.connector.connected_symbol
                self.logger.info("[CONNECTION RECOVERY SUCCESS] Internet and MT5 re-established! Resuming 24/7 trading.")
                break

    def _tick_cycle(self):
        """Unified tick execution: manages active profits, checks circuit breakers, and runs both engines."""
        # Connection Health Check (Auto-recovery on network/MT5 drop)
        if not self.connector.is_connected():
            self._handle_connection_loss()
            return

        acc = self.connector.get_account_summary()
        if not acc:
            return

        equity = acc["equity"]
        now = time.time()
        self.risk_manager.reset_daily_metrics_if_needed(equity)

        # Step 1: Manage active open positions (Break-Even, Trailing Stop, Retracement Guard)
        all_positions = self.executor.get_open_positions(self.active_symbol)
        self.executor.manage_active_positions(self.active_symbol)

        musumali_positions = [p for p in all_positions if p["magic"] == self.executor.magic_musumali]
        scalper_positions = [p for p in all_positions if p["magic"] == self.executor.magic_scalper]

        # Evaluate Daily Trend Bias for Heartbeat & Diagnostic
        daily_trend, trend_reason = self.musumali_strategy.get_daily_market_trend(self.active_symbol)

        # Circuit Breakers & Daily Limits (Fix 15 & Fix 30)
        can_trade, breaker_reason = self.risk_manager.check_circuit_breakers(equity)
        if self.is_manually_paused:
            can_trade = False
            breaker_reason = "Manual Telegram /pause command active"

        # Session Filter & Dynamic Tuning Check (Fix 28)
        session_ok, session_name, session_reason = self.risk_manager.is_session_allowed()
        session_tuning = self.risk_manager.get_session_tuning_params()

        # Spread Safety Check (Fix 25)
        spread_ok, current_spread, spread_reason = self.risk_manager.check_spread_allowed(self.active_symbol)

        # News Blackout Window Check (Fix 27)
        in_news, news_reason = self.risk_manager.is_in_news_blackout()

        # Periodic Quick 1-Minute Heartbeat
        if (now - self.last_quick_heartbeat_time) >= self.quick_heartbeat_interval:
            self.last_quick_heartbeat_time = now
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

        # Fix 32: Periodic Comprehensive Self-Reporting Heartbeat (Every 15 mins / 900s)
        if (now - self.last_comprehensive_heartbeat_time) >= self.comprehensive_heartbeat_interval:
            self.last_comprehensive_heartbeat_time = now
            self._emit_self_reporting_heartbeat(
                equity=equity,
                acc=acc,
                all_positions=all_positions,
                musumali_positions=musumali_positions,
                scalper_positions=scalper_positions,
                daily_trend=daily_trend,
                trend_reason=trend_reason,
                spread_ok=spread_ok,
                current_spread=current_spread,
                session_name=session_name,
                in_news=in_news,
                news_reason=news_reason,
                can_trade=can_trade,
                breaker_reason=breaker_reason,
            )

        # =====================================================================
        # ENGINE 1: Musumali Institutional Sweeps (H1, H4) [Magic: 2001]
        # =====================================================================
        if self.musumali_strategy.strat_cfg.get("enabled", True):
            in_cd_m, cd_msg_m = self.risk_manager.is_module_in_cooldown(self.executor.magic_musumali)
            
            rates_h1 = mt5.copy_rates_from_pos(self.active_symbol, mt5.TIMEFRAME_H1, 0, 3)
            h1_bar_time = str(pd.to_datetime(rates_h1[-2]["time"], unit="s")) if (rates_h1 is not None and len(rates_h1) >= 2) else None

            t_sig_start = time.time()
            sig, entry, sl, tp, candle_id, zone_id, setup_reason = self.musumali_strategy.generate_signal(
                self.active_symbol, traded_candle_ids=self.traded_candle_ids
            )
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
                elif in_news:
                    self.logger.info(
                        f"[MUSUMALI HTF CANDLE DECISION FIX 20] H1 Bar: {h1_bar_time} | Daily Gate: {daily_trend} | "
                        f"Status: NEWS_BLACKOUT | Action: SKIPPED | Reason: {news_reason}"
                    )
                elif not session_ok:
                    self.logger.info(
                        f"[MUSUMALI HTF CANDLE DECISION FIX 20] H1 Bar: {h1_bar_time} | Daily Gate: {daily_trend} | "
                        f"Status: SESSION_BLOCKED | Action: SKIPPED | Reason: {session_reason}"
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

            trade_cooldown = self.harmony_cfg.get("cooldown_seconds_per_trade", 0)
            time_since_trade = time.time() - self.last_trade_execution_time
            in_trade_cooldown = (trade_cooldown > 0 and time_since_trade < trade_cooldown)

            # Fix 30: Prevent duplicate orders for identical setup
            is_dup_m = any(p["magic"] == self.executor.magic_musumali and p["type"] == sig for p in all_positions) if sig else False

            if can_trade and spread_ok and not in_news and session_ok and not in_cd_m and not in_trade_cooldown and not is_dup_m and sig in ("BUY", "SELL") and candle_id:
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
            sig_s, entry_s, sl_s, tp_s, candle_id_s, reason_s, trend_context_s, latest_bar_time, no_trade_reason = (
                self.m1_scalper.scan_for_scalp_candidates(
                    self.active_symbol,
                    quality_threshold=session_tuning.get("quality_score_threshold", 50)
                )
            )

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
                elif in_news:
                    self.logger.info(
                        f"[M1 SCALP CANDLE DECISION FIX 20] M1 Bar: {latest_bar_time} | M15 Trend: {trend_context_s} | "
                        f"Status: NEWS_BLACKOUT | Action: SKIPPED | Reason: {news_reason}"
                    )
                elif not session_ok:
                    self.logger.info(
                        f"[M1 SCALP CANDLE DECISION FIX 20] M1 Bar: {latest_bar_time} | M15 Trend: {trend_context_s} | "
                        f"Status: SESSION_BLOCKED | Action: SKIPPED | Reason: {session_reason}"
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

            # Fix 30: Prevent duplicate orders for identical setup
            is_dup_s = any(p["magic"] == self.executor.magic_scalper and p["type"] == sig_s for p in all_positions) if sig_s else False

            if can_trade and spread_ok and not in_news and session_ok and not in_cd_s and not in_trade_cooldown and not is_dup_s:
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
                        # Fix 7 & 12 & Auto-Compounding: Dynamic Position Sizing
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
                            # Fix 4: Immediate execution with zero artificial delay
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

        # Step 4: Export real-time visual dashboard state
        all_positions_final = self.executor.get_open_positions(self.active_symbol)
        perf = self.risk_manager.get_module_performance_summary()
        cb_status = self.risk_manager.get_circuit_breaker_status()
        self.dashboard_exporter.export_data(
            symbol=self.active_symbol,
            account_summary=acc,
            all_positions=all_positions_final,
            daily_perf=perf,
            circuit_status=cb_status,
            active_session=session_name,
            daily_trend=daily_trend,
            trend_reason=trend_reason,
        )

    def stop(self):
        """Cleans up and terminates the bot safely."""
        self.is_running = False
        self.notifier.stop_command_poller()
        self.connector.shutdown()
        self.logger.info("Gold Trading Bot stopped safely.")

