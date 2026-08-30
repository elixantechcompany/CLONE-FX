"""
Funded Account Trading Bot Orchestrator (Multi-Symbol & Multi-Account Architecture)
Orchestrates simultaneously:
  1. Multi-Account Isolation: Account 1 and Account 2.
  2. Multi-Symbol Scanning: XAUUSD and BTCUSD.
  3. Dual Strategy Engines:
     - Engine 1: Musumali Institutional Sweeps (M30, H1, H4) [Magic: 2001]
     - Engine 2: Agile Micro-Scalper (M1, M5, M15) [Magic: 1001]
  4. Portfolio Signal Ranking & 20-Point Pre-Trade Safety Verification.
  5. Bot Restart State Recovery & 24/7 Resilience.
"""

import logging
import os
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
from src.execution import OrderExecutor
from src.m1_scalper import M1Scalper
from src.risk_manager import RiskManager
from src.strategy import MusumaliStrategy
from src.signal_ranker import SignalRanker, TradeCandidate
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
        self.poll_interval = self.config.get("system", {}).get("poll_interval_seconds", 1)

        # Initialize Multi-Account Manager
        self.account_manager = MultiAccountManager(self.config)

        # Core Engines
        self.musumali_strategy = MusumaliStrategy(self.config)
        self.m1_scalper = M1Scalper(self.config)
        self.signal_ranker = SignalRanker(self.config)
        self.notifier = Notifier(self.config)
        self.dashboard_exporter = DashboardExporter(self.config)

        # Active broker symbols mapping: {"XAUUSD": "XAUUSDm", "BTCUSD": "BTCUSDm"}
        self.active_broker_symbols: Dict[str, str] = {}

        # Traded candles persistence
        self.traded_candles_file = "data/traded_candles.json"
        self.traded_candle_ids: Set[str] = set()
        self._load_traded_candles()
        self.last_trade_execution_time = 0.0
        self.is_manually_paused = False

        # Heartbeat timers
        self.last_quick_heartbeat_time = 0.0
        self.last_comprehensive_heartbeat_time = 0.0
        self.quick_heartbeat_interval = self.config.get("system", {}).get("quick_heartbeat_interval_seconds", 60)
        self.comprehensive_heartbeat_interval = self.config.get("system", {}).get("heartbeat_interval_seconds", 900)

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
        """Persists traded setup IDs."""
        try:
            os.makedirs(os.path.dirname(self.traded_candles_file), exist_ok=True)
            with open(self.traded_candles_file, "w") as f:
                json.dump({"candle_ids": list(self.traded_candle_ids)[-50:]}, f)
        except Exception as e:
            self.logger.warning(f"Could not persist traded candles: {e}")

    def initialize_accounts(self) -> bool:
        """Initializes connectors, risk managers, and order executors for all active accounts."""
        active_accounts = self.account_manager.get_active_accounts()
        if not active_accounts:
            self.logger.error("No active accounts found in configuration.")
            return False

        for acc in active_accounts:
            if not acc.connector.initialize():
                self.logger.warning(f"Waiting for MT5 terminal connection on [{acc.account_id}]...")
                while not acc.connector.initialize():
                    time.sleep(3)

            # Bind isolated RiskManager & OrderExecutor to this AccountContext
            acc.risk_manager = RiskManager(self.config, acc.connector, account_id=acc.account_id)
            acc.executor = OrderExecutor(self.config, connector=acc.connector, risk_manager=acc.risk_manager, account_id=acc.account_id)

            # Resolve symbols on broker
            resolved = acc.connector.resolve_all_symbols(self.config.get("symbols", {}))
            self.active_broker_symbols.update(resolved)

            # Bot Restart Recovery for this account
            self._recover_account_positions(acc)

        return True

    def _recover_account_positions(self, acc: AccountContext):
        """
        Bot Restart Recovery (Directive 38):
        Reconnects to account, reads open MT5 positions, recovers state,
        reconstructs initial risk & peak R, and resumes active management.
        """
        self.logger.info(f"[{acc.account_id}] [RESTART RECOVERY] Checking for existing open positions...")
        acc.sync_account_metrics()

        for canonical, broker_sym in self.active_broker_symbols.items():
            positions = acc.executor.get_open_positions(broker_sym)
            for pos in positions:
                ticket = pos["ticket"]
                self.logger.info(
                    f"[{acc.account_id}] [RECOVERED POSITION] Ticket #{ticket} ({broker_sym} {pos['type']} {pos['volume']} lots @ {pos['price_open']:.2f}, "
                    f"SL: {pos['sl']:.2f}, TP: {pos['tp']:.2f}, P&L: ${pos['profit']:+.2f})"
                )
                # Register into Intelligent Exit Engine
                acc.executor.exit_engine.register_position(
                    ticket=ticket,
                    symbol=broker_sym,
                    pos_type=pos["type"],
                    volume=pos["volume"],
                    open_price=pos["price_open"],
                    sl=pos["sl"],
                    tp=pos["tp"],
                    magic=pos["magic"],
                    account_id=acc.account_id,
                )

    def start(self):
        """Starts 24/7 multi-account, multi-symbol trading bot."""
        self.logger.info("=" * 80)
        self.logger.info("   STARTING FUNDED ACCOUNT MULTI-SYMBOL & MULTI-ACCOUNT 24/7 BOT")
        self.logger.info("   Target: BrightFunded Free $1K Challenge | Baseline: $1,000.00 | Goal: +$100.00")
        self.logger.info("   Daily Stop: -$25.00 ($5 Buffer) | Trailing Stop: -$50.00 ($10 Buffer) | Single Risk: $2.50-$5.00")
        self.logger.info("   Engine 1: Musumali Sweeps (Magic #2001) | Engine 2: Micro-Scalper (Magic #1001)")
        self.logger.info("=" * 80)

        if not self.initialize_accounts():
            self.logger.error("Account initialization failed. Halting bot.")
            return

        self.is_running = True
        self.notifier.start_command_poller(self)

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

    def _tick_cycle(self):
        """Unified tick execution across accounts, symbols, and strategy engines."""
        now = time.time()
        active_accounts = self.account_manager.get_active_accounts()
        broker_symbols = list(self.active_broker_symbols.values())
        session_name = "Session"

        # 1. Update and manage active positions for every account
        for acc in active_accounts:
            if not acc.connector.is_connected():
                self.logger.warning(f"[{acc.account_id}] Connection dropped! Reconnecting...")
                acc.connector.reconnect(self.config.get("symbols", {}))
                continue

            acc.sync_account_metrics()
            acc.risk_manager.reset_daily_metrics_if_needed(acc.equity)
            session_name = acc.risk_manager.get_current_trading_session()

            # Manage active trades through Intelligent Exit Brain
            acc.executor.manage_active_positions(broker_symbols)

            # Evaluate circuit breakers & state
            can_trade, breaker_reason = acc.risk_manager.check_circuit_breakers(acc.equity)
            if self.is_manually_paused:
                can_trade = False
                breaker_reason = "Manual Telegram /pause active"
            acc.trading_state = acc.risk_manager.trading_state

        # 2. Multi-Symbol Scanning across both engines
        trade_candidates: List[TradeCandidate] = []

        for canonical, broker_sym in self.active_broker_symbols.items():
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

        # 3. Portfolio Signal Conviction Ranking (Directive 27)
        ranked_candidates = self.signal_ranker.rank_candidates(trade_candidates)

        # 4. Candidate Execution across Active Accounts
        for cand in ranked_candidates:
            for acc in active_accounts:
                all_open = acc.executor.get_open_positions()

                # Dynamic Sizing strictly bounded by BrightFunded $5.00 max risk ($2.50-$5.00)
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

                # Mandatory 20-Point Pre-Trade Safety Check on exact calculated lot size
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
                        self.traded_candle_ids.add(cand.candle_id)
                        self._save_traded_candles()
                        self.last_trade_execution_time = time.time()
                        acc.risk_manager.record_trade_placed(magic=cand.magic, symbol=cand.symbol)
                        self.notifier.notify_trade_event(
                            "TRADE OPENED",
                            f"Ticket #{ticket} | {cand.symbol} {cand.direction} {lot_size} lots @ {cand.entry:.2f}\n"
                            f"SL: {cand.sl:.2f} | TP: {cand.tp:.2f} | Risk: ${expected_loss:.2f} | Conviction: {cand.conviction_score}/100\n"
                            f"Reason: {cand.setup_reason}",
                            account_id=acc.account_id,
                        )

        # 5. Heartbeat & Dashboard Export
        if (now - self.last_quick_heartbeat_time) >= self.quick_heartbeat_interval:
            self.last_quick_heartbeat_time = now
            for acc in active_accounts:
                positions = acc.executor.get_open_positions()
                cb_status = acc.risk_manager.get_circuit_breaker_status(acc.equity)
                self.logger.info(
                    f"[{acc.account_id} Heartbeat] Equity: ${acc.equity:.2f} | Open Trades: {len(positions)}/2 | {cb_status}"
                )

        if (now - self.last_comprehensive_heartbeat_time) >= self.comprehensive_heartbeat_interval:
            self.last_comprehensive_heartbeat_time = now
            self._emit_comprehensive_heartbeat(active_accounts, session_name)

        # Export Real-Time Dashboard JSON
        all_positions_export = []
        for acc in active_accounts:
            for p in acc.executor.get_open_positions():
                p_copy = dict(p)
                p_copy["account_id"] = acc.account_id
                all_positions_export.append(p_copy)

        self.dashboard_exporter.export_data(
            active_symbols=self.active_broker_symbols,
            accounts_summary=self.account_manager.get_all_summaries(),
            all_positions=all_positions_export,
            active_session=session_name,
        )

    def _emit_comprehensive_heartbeat(self, active_accounts: List[AccountContext], session_name: str):
        """Emits comprehensive multi-account diagnostic report."""
        now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        lines = [
            f"\n{'='*80}",
            f" [COMPREHENSIVE FUNDED BOT HEARTBEAT] {now_utc}",
            f" Active Session: {session_name} | Symbols: {list(self.active_broker_symbols.keys())}",
            f"{'-'*80}",
        ]
        for acc in active_accounts:
            perf = acc.risk_manager.get_module_performance_summary()
            lines.append(
                f" 📌 {acc.name} ({acc.account_id}):\n"
                f"    - Equity: ${acc.equity:.2f} | Balance: ${acc.balance:.2f} | Free Margin: ${acc.free_margin:.2f}\n"
                f"    - Daily Realized P&L: ${perf['total_day_pnl']:+.2f} (Scalp: ${perf['scalp_pnl']:+.2f} [{perf['scalp_wins']}W/{perf['scalp_trades']-perf['scalp_wins']}L], Musumali: ${perf['musumali_pnl']:+.2f} [{perf['musumali_wins']}W/{perf['musumali_trades']-perf['musumali_wins']}L])\n"
                f"    - Daily State: {acc.trading_state} | Drawdown: -{acc.daily_drawdown_pct:.1f}%\n"
            )
        lines.append("=" * 80)
        report = "\n".join(lines)
        self.logger.info(report)
        self.notifier.notify_heartbeat(report)

    def stop(self):
        """Safely shuts down bot and all account connections."""
        self.is_running = False
        self.notifier.stop_command_poller()
        for acc in self.account_manager.accounts.values():
            acc.connector.shutdown()
        self.logger.info("Funded Trading Bot terminated cleanly.")
