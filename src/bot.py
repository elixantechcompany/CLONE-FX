"""
Funded & Multi-Account Trading Bot Orchestrator (High-Efficiency & Fault-Tolerant)
Orchestrates:
  1. Strict 4-Account Architecture Isolation:
     - Account A: $1,000 BrightFunded (Independent, Shared Strategy, Zero Copy)
     - Account B: $1,000 BrightFunded (Independent, Shared Strategy, Zero Copy)
     - Account C: $20 Personal Account (Copy Master, Shared Strategy)
     - Account D: $20 Personal Account (Copy Follower, C -> D Only)
  2. MT5 Native "Algo Trading" Primary Master Switch:
     - Algo ON: Normal automated operations permitted.
     - Algo OFF: Process remains running; new trades blocked; positions actively managed.
     - Zero manual /start or /resume commands required for normal operations.
  3. 7-Stage Connection State Machine & Auto-Recovery:
     - Independent connection monitoring & fault isolation per account.
     - 10-Step State & Position Reconciliation on recovery.
     - Absolute Reconnection Rule: Zero stale/missed trade execution.
  4. Multi-Symbol Scanning: XAUUSD and BTCUSD.
  5. Dual Shared Strategy Engines:
     - Engine 1: Musumali Institutional Sweeps (M30, H1, H4) [Magic: 2001]
     - Engine 2: Agile Micro-Scalper (M1, M5, M15) [Magic: 1001]
  6. Isolated Copy Trading Engine (Account C -> Account D with 8-Step Safety Checks).
"""

import logging
import os
import gc
from logging.handlers import RotatingFileHandler
import time
import datetime
import json
from typing import List, Optional, Set, Tuple, Dict, Any
import pandas as pd
import MetaTrader5 as mt5
import yaml
from dotenv import load_dotenv

from src.account_manager import MultiAccountManager, AccountContext
from src.connection import MT5Connector
from src.connection_state import ConnectionState
from src.execution import OrderExecutor
from src.m1_scalper import M1Scalper
from src.risk_manager import RiskManager
from src.strategy import MusumaliStrategy
from src.signal_ranker import SignalRanker, TradeCandidate
from src.copy_engine import CopyTradingEngine, CopyEvent
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

        f_handler = RotatingFileHandler("logs/trading_bot.log", maxBytes=15 * 1024 * 1024, backupCount=5)
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
        self.poll_interval = float(self.config.get("system", {}).get("poll_interval_seconds", 2.0))

        # Multi-Account Manager
        self.account_manager = MultiAccountManager(self.config)

        # Isolated Copy Engine (Strictly C -> D)
        self.copy_engine = CopyTradingEngine(self.config, self.account_manager)

        # Shared Strategy Engines
        self.musumali_strategy = MusumaliStrategy(self.config)
        self.m1_scalper = M1Scalper(self.config)
        self.signal_ranker = SignalRanker(self.config)
        self.notifier = Notifier(self.config)
        self.dashboard_exporter = DashboardExporter(self.config)

        # Active broker symbols mapping: {"XAUUSD": "XAUUSDm", "BTCUSD": "BTCUSDm"}
        self.active_broker_symbols: Dict[str, str] = {}

        # Traded candles persistence (Preserved across restarts and reconnects)
        self.traded_candles_file = "data/traded_candles.json"
        self.traded_candle_ids: Set[str] = set()
        self._load_traded_candles()
        self.last_trade_execution_time = 0.0
        self.is_manually_paused = False

        # Heartbeat and resource maintenance timers
        self.last_quick_heartbeat_time = 0.0
        self.last_comprehensive_heartbeat_time = 0.0
        self.quick_heartbeat_interval = float(self.config.get("system", {}).get("quick_heartbeat_interval_seconds", 60.0))
        self.comprehensive_heartbeat_interval = float(self.config.get("system", {}).get("heartbeat_interval_seconds", 900.0))
        self.last_gc_time = time.time()
        self.tick_counter = 0

        self.is_running = False

    def _load_traded_candles(self):
        """Loads previously executed candle setup IDs to prevent duplicate trades across restarts."""
        try:
            if os.path.exists(self.traded_candles_file):
                with open(self.traded_candles_file, "r") as f:
                    data = json.load(f)
                    self.traded_candle_ids = set(data.get("candle_ids", [])[-50:])
                    self.logger.info(f"Loaded {len(self.traded_candle_ids)} recent traded setup IDs from disk.")
        except Exception as e:
            self.logger.warning(f"Could not load traded candles: {e}")

    def _save_traded_candles(self):
        """Persists traded setup IDs atomically to prevent corruption."""
        try:
            os.makedirs(os.path.dirname(self.traded_candles_file), exist_ok=True)
            temp_file = self.traded_candles_file + ".tmp"
            with open(temp_file, "w") as f:
                json.dump({"candle_ids": list(self.traded_candle_ids)[-50:]}, f)
            os.replace(temp_file, self.traded_candles_file)
        except Exception as e:
            self.logger.warning(f"Could not persist traded candles: {e}")

    def initialize_accounts(self) -> bool:
        """Initializes connectors, state machines, risk managers, and executors for all active accounts."""
        active_accounts = self.account_manager.get_active_accounts()
        if not active_accounts:
            self.logger.error("No active accounts found in configuration.")
            return False

        successful_connections = 0

        for acc in active_accounts:
            # Bind isolated RiskManager & OrderExecutor with account profile
            if acc.risk_manager is None:
                acc.risk_manager = RiskManager(
                    self.config,
                    acc.connector,
                    account_id=acc.account_id,
                    account_type=acc.account_type,
                )
            if acc.executor is None:
                acc.executor = OrderExecutor(
                    self.config,
                    connector=acc.connector,
                    risk_manager=acc.risk_manager,
                    account_id=acc.account_id,
                )
                if acc.is_copy_master:
                    acc.executor.add_event_callback(self._on_master_account_event)

            max_attempts = 3
            connected = False
            for attempt in range(1, max_attempts + 1):
                if acc.connector.initialize():
                    connected = True
                    successful_connections += 1
                    break
                self.logger.warning(f"[{acc.account_id.upper()}] MT5 terminal connection attempt {attempt}/{max_attempts} failed...")
                time.sleep(2)

            if not connected:
                self.logger.warning(
                    f"[{acc.account_id.upper()}] Could not connect to MT5 terminal on startup. "
                    f"Account marked in CONNECTION_LOST state. Other accounts will continue trading normally."
                )
                acc.state_machine.transition_to(
                    ConnectionState.CONNECTION_LOST,
                    reason="Initial connection failed on startup"
                )
                continue

            # Resolve symbols on broker
            resolved = acc.connector.resolve_all_symbols(self.config.get("symbols", {}))
            self.active_broker_symbols.update(resolved)

            # Initial state transition based on MT5 native Algo Trading switch
            acc.update_connection_state()

            # Initial Position Reconciliation
            acc.reconcile_account_state(self.active_broker_symbols)

        if successful_connections == 0:
            self.logger.error("Zero accounts could connect to MT5. Please check MT5 terminals and credentials.")
            return False

        return True

    def _on_master_account_event(self, account_id: str, event_type: str, data: dict):
        """Callback triggered when Account C (Master) opens, modifies, or closes a position."""
        try:
            if account_id.lower() != "account_c":
                return

            if not self.copy_engine or not self.copy_engine.enabled or self.copy_engine.is_paused:
                return

            if event_type == "OPEN":
                event = self.copy_engine.create_copy_event(
                    origin_account_id=account_id,
                    symbol=data["symbol"],
                    direction=data["direction"],
                    entry=data["entry"],
                    sl=data["sl"],
                    tp=data["tp"],
                    volume=data["volume"],
                    master_ticket=data["ticket"],
                    event_type="OPEN",
                    magic=data.get("magic", 1001),
                )
                if event:
                    self.copy_engine.process_copy_event(event)

            elif event_type in ("SL_MODIFY", "TP_MODIFY"):
                event = self.copy_engine.create_copy_event(
                    origin_account_id=account_id,
                    symbol=data["symbol"],
                    direction="BUY",
                    entry=0.0,
                    sl=data.get("sl", 0.0),
                    tp=data.get("tp", 0.0),
                    volume=0.0,
                    master_ticket=data["ticket"],
                    event_type=event_type,
                )
                if event:
                    self.copy_engine.process_copy_event(event)

            elif event_type == "PARTIAL_CLOSE":
                event = self.copy_engine.create_copy_event(
                    origin_account_id=account_id,
                    symbol=data["symbol"],
                    direction="BUY",
                    entry=0.0,
                    sl=0.0,
                    tp=0.0,
                    volume=0.0,
                    master_ticket=data["ticket"],
                    event_type="PARTIAL_CLOSE",
                    partial_volume=data.get("partial_volume", 0.0),
                )
                if event:
                    self.copy_engine.process_copy_event(event)

            elif event_type == "CLOSE":
                event = self.copy_engine.create_copy_event(
                    origin_account_id=account_id,
                    symbol=data["symbol"],
                    direction="BUY",
                    entry=0.0,
                    sl=0.0,
                    tp=0.0,
                    volume=0.0,
                    master_ticket=data["ticket"],
                    event_type="CLOSE",
                )
                if event:
                    self.copy_engine.process_copy_event(event)
        except Exception as e:
            self.logger.warning(f"Error in copy event callback: {e}")

    def start(self):
        """Starts 24/7 multi-account, multi-symbol trading bot with infinite resource-safe loop."""
        self.logger.info("=" * 80)
        self.logger.info("   STARTING MULTI-ACCOUNT PRECISION 24/7 TRADING BOT")
        self.logger.info("   PRIMARY MASTER SWITCH: MT5 Native 'Algo Trading'")
        self.logger.info("   ACCOUNT A: $1,000 BrightFunded (Independent, Zero Copy)")
        self.logger.info("   ACCOUNT B: $1,000 BrightFunded (Independent, Zero Copy)")
        self.logger.info("   ACCOUNT C: $20 Personal Account (Copy Master)")
        self.logger.info("   ACCOUNT D: $20 Personal Account (Copy Follower, C -> D Only)")
        self.logger.info("   Engine 1: Musumali Sweeps (Magic #2001) | Engine 2: Micro-Scalper (Magic #1001)")
        self.logger.info(f"   Poll Interval: {self.poll_interval:.1f}s | CPU Optimization: ENABLED")
        self.logger.info("=" * 80)

        if not self.initialize_accounts():
            self.logger.error("Account initialization failed. Halting bot.")
            return

        self.is_running = True
        try:
            self.notifier.start_command_poller(self)
        except Exception as e:
            self.logger.warning(f"Could not start Telegram command poller: {e}")

        try:
            while self.is_running:
                try:
                    self._tick_cycle()
                except Exception as e:
                    self.logger.exception(f"Error during tick cycle: {e}")

                # Maintain low memory footprint via periodic garbage collection
                self.tick_counter += 1
                if self.tick_counter % 300 == 0:
                    gc.collect()

                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            self.logger.info("Shutdown requested by user (Ctrl+C).")
        finally:
            self.stop()

    def _tick_cycle(self):
        """
        Unified tick execution across accounts, symbols, and strategy engines.
        Handles independent connection state machines, Algo Trading switch detection,
        and zero-stale-trade execution.
        """
        now = time.time()
        active_accounts = self.account_manager.get_active_accounts()
        strategy_accounts = self.account_manager.get_strategy_accounts()  # Accounts A, B, C
        broker_symbols = list(self.active_broker_symbols.values())
        session_name = "Session"

        # =====================================================================
        # 1. INDEPENDENT ACCOUNT CONNECTION & POSITION MANAGEMENT
        # =====================================================================
        for acc in active_accounts:
            try:
                acc.connector.ensure_terminal_context()
                prev_state = acc.state_machine.current_state
                cur_state = acc.update_connection_state()

                # Handle Reconnection / Recovery if disconnected
                if cur_state in (ConnectionState.CONNECTION_LOST, ConnectionState.RECONNECTING):
                    # Attempt reconnect
                    acc.state_machine.transition_to(
                        ConnectionState.RECONNECTING,
                        reason="Attempting auto-reconnection"
                    )
                    reconnected = acc.connector.reconnect(self.config.get("symbols", {}))
                    if reconnected:
                        self.logger.info(f"[{acc.account_id.upper()}] [CONNECTION RESTORED] Restoring state...")
                        acc.reconcile_account_state(self.active_broker_symbols)
                    else:
                        # Continue with other accounts without blocking
                        continue

                # Synchronize balance, equity, margin
                acc.sync_account_metrics()
                if acc.risk_manager:
                    acc.risk_manager.reset_daily_metrics_if_needed(acc.equity)
                    session_name = acc.risk_manager.get_current_trading_session()
                    acc.trading_state = acc.risk_manager.trading_state

                # SEPARATION: Manage active trades through Intelligent Exit Brain
                # (Existing positions remain actively managed even if Algo Trading is OFF)
                if acc.executor:
                    acc.executor.manage_active_positions(broker_symbols)

            except Exception as e:
                self.logger.warning(f"[{acc.account_id.upper()}] Account cycle warning: {e}")

        # =====================================================================
        # 2. MULTI-SYMBOL SCANNING (SHARED STRATEGY CODE - LIVE CURRENT MARKET DATA)
        # =====================================================================
        # ABSOLUTE RECONNECTION RULE:
        # Signals are strictly derived from CURRENT live market data.
        # Missed signals from offline intervals are NEVER executed.
        trade_candidates: List[TradeCandidate] = []

        for canonical, broker_sym in self.active_broker_symbols.items():
            try:
                sym_info = mt5.symbol_info(broker_sym)
                if sym_info is None:
                    continue
                cur_spread = sym_info.spread

                # Engine 1: Musumali Institutional Sweeps (M30, H1)
                if self.musumali_strategy.strat_cfg.get("enabled", True):
                    sig_m, entry_m, sl_m, tp_m, cid_m, zid_m, score_m, reason_m = self.musumali_strategy.generate_signal(
                        broker_sym, traded_candle_ids=self.traded_candle_ids
                    )
                    if sig_m and cid_m and cid_m not in self.traded_candle_ids:
                        trade_candidates.append(TradeCandidate(
                            symbol=broker_sym,
                            engine_name="Musumali_Sweep",
                            magic=self.musumali_strategy.magic_number,
                            direction=sig_m,
                            entry=entry_m,
                            sl=sl_m,
                            tp=tp_m,
                            candle_id=cid_m,
                            zone_id=zid_m,
                            base_quality_score=score_m,
                            setup_reason=reason_m,
                            timeframe="H1",
                            spread=cur_spread,
                        ))

                # Engine 2: Agile Micro-Scalper (M1, M5)
                if self.m1_scalper.enabled:
                    sig_s, entry_s, sl_s, tp_s, cid_s, score_s, reason_s, _, _, _ = self.m1_scalper.scan_for_scalp_candidates(
                        broker_sym
                    )
                    if sig_s and cid_s and cid_s not in self.traded_candle_ids:
                        trade_candidates.append(TradeCandidate(
                            symbol=broker_sym,
                            engine_name="M1_Scalp",
                            magic=self.m1_scalper.magic_number,
                            direction=sig_s,
                            entry=entry_s,
                            sl=sl_s,
                            tp=tp_s,
                            candle_id=cid_s,
                            zone_id=None,
                            base_quality_score=score_s,
                            setup_reason=reason_s,
                            timeframe="M1",
                            spread=cur_spread,
                        ))
            except Exception as e:
                self.logger.warning(f"Market scanner cycle warning for {broker_sym}: {e}")

        # =====================================================================
        # 3. PORTFOLIO SIGNAL CONVICTION RANKING
        # =====================================================================
        ranked_candidates = []
        try:
            ranked_candidates = self.signal_ranker.rank_candidates(trade_candidates)
        except Exception as e:
            self.logger.warning(f"Signal ranker warning: {e}")
            ranked_candidates = trade_candidates

        # =====================================================================
        # 4. CANDIDATE EXECUTION ACROSS STRATEGY ACCOUNTS (A, B, C INDEPENDENTLY)
        # =====================================================================
        for cand in ranked_candidates:
            candle_traded_any = False
            for acc in strategy_accounts:
                try:
                    if not acc.executor or not acc.risk_manager:
                        continue

                    # PRIMARY MASTER SWITCH: MT5 Algo Trading must be ALLOWED
                    if not acc.is_trading_permitted or self.is_manually_paused:
                        # Skip new trade execution if Algo Trading is OFF or account is paused
                        continue

                    all_open = acc.executor.get_open_positions()

                    # Dynamic Sizing bounded by this account's profile risk limits
                    lot_size = acc.risk_manager.calculate_lot_size(
                        symbol=cand.symbol,
                        entry_price=cand.entry,
                        stop_loss_price=cand.sl,
                        equity=acc.equity,
                        quality_score=int(cand.conviction_score),
                        open_trades_count=len(all_open),
                    )

                    if lot_size <= 0.0:
                        continue

                    # Mandatory Pre-Trade Safety Check on exact calculated lot size
                    passed, failures, expected_loss = acc.risk_manager.pre_trade_risk_check(
                        symbol=cand.symbol,
                        engine_magic=cand.magic,
                        order_type=cand.direction,
                        entry_price=cand.entry,
                        stop_loss_price=cand.sl,
                        take_profit_price=cand.tp,
                        volume=lot_size,
                        quality_score=int(cand.conviction_score),
                        all_open_positions=all_open,
                        equity=acc.equity,
                        free_margin=acc.free_margin,
                        candle_id=cand.candle_id,
                        traded_candle_ids=self.traded_candle_ids,
                        last_trade_time=self.last_trade_execution_time,
                    )

                    if passed:
                        ticket = acc.executor.execute_market_order(
                            symbol=cand.symbol,
                            order_type=cand.direction,
                            volume=lot_size,
                            sl=cand.sl,
                            tp=cand.tp,
                            magic=cand.magic,
                            comment=cand.engine_name,
                            zone_id=cand.zone_id,
                            candle_id=cand.candle_id,
                        )

                        if ticket:
                            candle_traded_any = True
                            self.last_trade_execution_time = time.time()
                            acc.risk_manager.record_trade_placed(magic=cand.magic, symbol=cand.symbol)
                            acc.state_machine.record_order_op()
                            self.notifier.notify_trade_event(
                                "TRADE OPENED",
                                f"Ticket #{ticket} | {cand.symbol} {cand.direction} {lot_size} lots @ {cand.entry:.2f}\n"
                                f"SL: {cand.sl:.2f} | TP: {cand.tp:.2f} | Risk: ${expected_loss:.2f} | Conviction: {cand.conviction_score}/100\n"
                                f"Reason: {cand.setup_reason}",
                                account_id=acc.account_id,
                            )
                except Exception as e:
                    self.logger.warning(f"[{acc.account_id.upper()}] Execution loop warning: {e}")

            if candle_traded_any:
                self.traded_candle_ids.add(cand.candle_id)
                self._save_traded_candles()

        # =====================================================================
        # 5. HEARTBEAT & DASHBOARD EXPORT
        # =====================================================================
        try:
            if (now - self.last_quick_heartbeat_time) >= self.quick_heartbeat_interval:
                self.last_quick_heartbeat_time = now
                for acc in active_accounts:
                    positions = acc.executor.get_open_positions() if acc.executor else []
                    cb_status = acc.risk_manager.get_circuit_breaker_status(acc.equity) if acc.risk_manager else ""
                    algo_tag = "ALGO:ON" if acc.is_algo_trading_allowed else "ALGO:OFF"
                    self.logger.info(
                        f"[{acc.account_id.upper()} Heartbeat] State: {acc.state_machine.current_state.value} | {algo_tag} | "
                        f"Equity: ${acc.equity:.2f} | Open Trades: {len(positions)}/2 | {cb_status}"
                    )

            if (now - self.last_comprehensive_heartbeat_time) >= self.comprehensive_heartbeat_interval:
                self.last_comprehensive_heartbeat_time = now
                self._emit_comprehensive_heartbeat(active_accounts, session_name)

            # Export Real-Time Dashboard JSON
            all_positions_export = []
            for acc in active_accounts:
                if acc.executor:
                    for p in acc.executor.get_open_positions():
                        p_copy = dict(p)
                        p_copy["account_id"] = acc.account_id.upper()
                        all_positions_export.append(p_copy)

            self.dashboard_exporter.export_data(
                active_symbols=self.active_broker_symbols,
                accounts_summary=self.account_manager.get_all_summaries(),
                all_positions=all_positions_export,
                active_session=session_name,
                copy_engine_status=self.copy_engine.get_status() if self.copy_engine else None,
            )
        except Exception as e:
            self.logger.warning(f"Dashboard/Heartbeat export warning: {e}")

    def _emit_comprehensive_heartbeat(self, active_accounts: List[AccountContext], session_name: str):
        """Emits comprehensive multi-account diagnostic report."""
        try:
            now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            lines = [
                f"\n{'='*80}",
                f" [COMPREHENSIVE MULTI-ACCOUNT BOT HEARTBEAT] {now_utc}",
                f" Active Session: {session_name} | Symbols: {list(self.active_broker_symbols.keys())}",
                f"{'-'*80}",
            ]
            for acc in active_accounts:
                perf = acc.risk_manager.get_module_performance_summary() if acc.risk_manager else {"total_day_pnl": 0.0, "scalp_pnl": 0.0, "scalp_wins": 0, "scalp_trades": 0, "musumali_pnl": 0.0, "musumali_wins": 0, "musumali_trades": 0}
                sm_summary = acc.state_machine.get_summary()
                lines.append(
                    f" [*] {acc.name} ({acc.account_id.upper()} - {acc.mode}):\n"
                    f"    - Connection State: {sm_summary['current_state']} | MT5 Algo Trading: {'ENABLED' if acc.is_algo_trading_allowed else 'DISABLED'}\n"
                    f"    - Equity: ${acc.equity:.2f} | Balance: ${acc.balance:.2f} | Free Margin: ${acc.free_margin:.2f}\n"
                    f"    - Daily Realized P&L: ${perf['total_day_pnl']:+.2f} (Scalp: ${perf['scalp_pnl']:+.2f} [{perf['scalp_wins']}W/{perf['scalp_trades']-perf['scalp_wins']}L], Musumali: ${perf['musumali_pnl']:+.2f} [{perf['musumali_wins']}W/{perf['musumali_trades']-perf['musumali_wins']}L])\n"
                    f"    - Daily State: {acc.trading_state} | Drawdown: -{acc.daily_drawdown_pct:.1f}%\n"
                )
            if self.copy_engine:
                cp = self.copy_engine.get_status()
                lines.append(
                    f" [COPY] Copy Engine (C -> D): Enabled={cp['enabled']} | Paused={cp['is_paused']} | Active Copied={cp['active_copied_count']}"
                )
            lines.append("=" * 80)
            report = "\n".join(lines)
            self.logger.info(report)
            self.notifier.notify_heartbeat(report)
        except Exception as e:
            self.logger.warning(f"Error in comprehensive heartbeat: {e}")

    def stop(self):
        """Safely shuts down bot and all account connections."""
        self.is_running = False
        try:
            self.notifier.stop_command_poller()
        except Exception:
            pass
        for acc in self.account_manager.accounts.values():
            try:
                acc.connector.shutdown()
            except Exception:
                pass
        self.logger.info("Trading Bot terminated cleanly.")
