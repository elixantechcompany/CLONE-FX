"""
Main High-Conviction Bot Orchestrator for Gold (XAUUSD)
Orchestrates:
  Engine: High-Conviction Musumali Liquidity Sweeps (M15, M30, H1) [Magic: 999888]
Features:
  - Strict Trend Alignment Filter (Zero Counter-Trend Trading)
  - Structural Rejection Wick Stop Loss + 1:2 R:R Target Profit
  - Dynamic Break-Even & Profit Retracement Guardian
  - 24/7 Autonomous Non-Stop Analysis
"""

import logging
import os
from logging.handlers import RotatingFileHandler
import time
from typing import Optional, Set
import MetaTrader5 as mt5
import yaml
from dotenv import load_dotenv

from src.connection import MT5Connector
from src.execution import OrderExecutor
from src.risk_manager import RiskManager
from src.strategy import MusumaliStrategy


def setup_logger(log_level: str = "INFO") -> logging.Logger:
    """Configures structured console and rotating file logging."""
    os.makedirs("logs", exist_ok=True)
    logger = logging.getLogger("GoldBot")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    if not logger.handlers:
        c_handler = logging.StreamHandler()
        c_format = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s", "%Y-%m-%d %H:%M:%S")
        c_handler.setFormatter(c_format)
        logger.addHandler(c_handler)

        f_handler = RotatingFileHandler("logs/trading_bot.log", maxBytes=10 * 1024 * 1024, backupCount=5)
        f_format = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s", "%Y-%m-%d %H:%M:%S")
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
        self.poll_interval = self.config.get("system", {}).get("poll_interval_seconds", 2)
        self.heartbeat_interval = self.config.get("system", {}).get("heartbeat_interval_seconds", 60)

        # Limits & Harmony Rules
        self.harmony_cfg = self.config.get("harmony_rules", {})
        self.total_max_open = self.harmony_cfg.get("total_max_open_positions", 2)
        self.prevent_opposing = self.harmony_cfg.get("prevent_opposing_trades", True)
        self.cooldown_sec = self.harmony_cfg.get("cooldown_seconds_per_trade", 10)

        # Signal De-Duplication Lock (Ensures ONLY 1 trade per unique setup candle)
        self.traded_candle_ids: Set[str] = set()
        self.last_trade_execution_time = 0.0

        # Initialize Submodules
        self.connector = MT5Connector()
        self.risk_manager = RiskManager(self.config, self.connector)
        self.executor = OrderExecutor(self.config)
        self.musumali_strategy = MusumaliStrategy(self.config)

        self.active_symbol: Optional[str] = None
        self.is_running = False
        self.last_heartbeat_time = 0.0

    def start(self):
        """Starts the High-Conviction 24/7 trading bot."""
        self.logger.info("=" * 65)
        self.logger.info("   STARTING HIGH-CONVICTION GOLD (XAUUSD) 24/7 BOT")
        self.logger.info("   Strategy: Musumali Institutional Liquidity Sweeps (M15, M30, H1)")
        self.logger.info("   Filters: Intraday Trend Confluence + Structural SL + Anti-Giveback Guard")
        self.logger.info("=" * 65)

        if not self.connector.initialize():
            self.logger.error("Failed to connect to MT5. Please verify MT5 is open and Algo Trading is enabled.")
            return

        candidates = self.config.get("symbols", {}).get("candidates", ["XAUUSDm", "XAUUSD"])
        self.active_symbol = self.connector.resolve_symbol(candidates)
        if not self.active_symbol:
            self.logger.error("Could not find a valid Gold symbol. Halting execution.")
            self.connector.shutdown()
            return

        self.is_running = True
        self.logger.info(f"Bot Active 24/7! Monitoring {self.active_symbol} | Max Positions: {self.total_max_open}")

        try:
            while self.is_running:
                self._tick_cycle()
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            self.logger.info("Shutdown requested by user (Ctrl+C).")
        except Exception as e:
            self.logger.exception(f"Unexpected error in trading loop: {e}")
        finally:
            self.stop()

    def _tick_cycle(self):
        """Unified tick execution: scans for high-probability setups and manages active positions."""
        acc = self.connector.get_account_summary()
        if not acc:
            return

        equity = acc["equity"]
        now = time.time()

        # Step 1: Manage open positions (Break-Even lock, Retracement closer, Target TP)
        all_positions = self.executor.get_open_positions(self.active_symbol)
        self.executor.manage_active_positions(self.active_symbol)

        # Periodic Heartbeat Update
        if (now - self.last_heartbeat_time) >= self.heartbeat_interval:
            self.last_heartbeat_time = now
            tick = mt5.symbol_info_tick(self.active_symbol)
            bid_str = f"{tick.bid:.2f}" if tick else "N/A"
            ask_str = f"{tick.ask:.2f}" if tick else "N/A"
            self.logger.info(
                f"[Heartbeat 24/7] {self.active_symbol} Ask: {ask_str} | Bid: {bid_str} | "
                f"Active Trades: {len(all_positions)} | Equity: ${equity:.2f}"
            )

        # Check Total Max Open Positions Cap
        if len(all_positions) >= self.total_max_open:
            return

        # Check Execution Cooldown
        if (now - self.last_trade_execution_time) < self.cooldown_sec:
            return

        # Check Spread Safety
        spread_ok, current_spread = self.risk_manager.check_spread_allowed(self.active_symbol)
        if not spread_ok:
            return

        # Active Direction Filter (Conflict Prevention)
        has_open_buy = any(p["type"] == "BUY" for p in all_positions)
        has_open_sell = any(p["type"] == "SELL" for p in all_positions)

        # =====================================================================
        # STRATEGY SCAN: High-Conviction Institutional Sweeps (M15, M30, H1)
        # =====================================================================
        sig, entry, sl, tp, candle_id = self.musumali_strategy.generate_signal(self.active_symbol)
        if sig in ("BUY", "SELL") and candle_id and candle_id not in self.traded_candle_ids:
            if not (self.prevent_opposing and ((sig == "BUY" and has_open_sell) or (sig == "SELL" and has_open_buy))):
                ticket = self.executor.execute_market_order(
                    symbol=self.active_symbol,
                    order_type=sig,
                    volume=0.01,
                    sl=sl,
                    tp=tp,
                    magic=self.executor.magic_musumali,
                    comment="Musumali_HighProb",
                )
                if ticket:
                    self.traded_candle_ids.add(candle_id)
                    self.last_trade_execution_time = now
                    self.risk_manager.record_trade_placed()

    def stop(self):
        """Cleans up and terminates the bot safely."""
        self.is_running = False
        self.connector.shutdown()
        self.logger.info("Gold Trading Bot stopped safely.")
