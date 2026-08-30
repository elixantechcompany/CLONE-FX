"""
Notification and Alert Dispatcher (Multi-Account & Multi-Symbol Telegram Alerts)
Enforces:
  1. Multi-Account Capital & Performance Monitoring.
  2. Instant Alerts for: Trade Opened, Closed, SL Hit, Early Invalidation Exit,
     Profit Target Reached, Daily Loss Warning, Circuit Trip, Missing SL Fail-Safe.
  3. Interactive Telegram Remote Control (/status, /pnl, /pause, /resume, /closeall).
"""

import logging
import urllib.request
import urllib.parse
import json
import threading
import time
from typing import Optional, Callable, Dict, Any, List

logger = logging.getLogger("GoldBot.Notifier")


class Notifier:
    def __init__(self, config: dict):
        self.config = config
        self.notif_cfg = config.get("notifications", {})
        self.telegram_enabled = self.notif_cfg.get("telegram_enabled", False)
        self.bot_token = self.notif_cfg.get("telegram_bot_token", "").strip()
        self.chat_id = str(self.notif_cfg.get("telegram_chat_id", "")).strip()
        self.interactive_enabled = self.notif_cfg.get("interactive_commands_enabled", True)

        self.last_update_id = 0
        self.bot_instance = None
        self._polling_thread: Optional[threading.Thread] = None
        self._stop_polling = False

    def send_telegram(self, message: str) -> bool:
        """Dispatches an alert message to configured Telegram Chat ID."""
        if not self.telegram_enabled or not self.bot_token or not self.chat_id:
            return False

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown",
            }
            data = urllib.parse.urlencode(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"User-Agent": "GoldBot/2.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                return resp.status == 200
        except Exception as e:
            logger.warning(f"Telegram dispatch failed: {e}")
            return False

    def notify_heartbeat(self, heartbeat_text: str):
        """Sends periodic self-reporting heartbeat."""
        if self.telegram_enabled:
            self.send_telegram(f"💓 *[Funded Bot Heartbeat]*\n```\n{heartbeat_text}\n```")

    def notify_trade_event(self, event_type: str, details: str, account_id: str = "account_1"):
        """Sends critical trade execution or circuit breaker alert."""
        if self.telegram_enabled:
            icon = "🚨" if ("CIRCUIT" in event_type or "HARD LOSS" in event_type or "FAIL" in event_type) else ("🎯" if "TARGET" in event_type else "⚡")
            self.send_telegram(f"{icon} *[{event_type} | {account_id}]*\n{details}")

    def start_command_poller(self, bot_instance):
        """Starts background listener for interactive Telegram commands."""
        if not self.telegram_enabled or not self.interactive_enabled or not self.bot_token:
            return

        self.bot_instance = bot_instance
        self._stop_polling = False
        self._polling_thread = threading.Thread(target=self._poll_loop, daemon=True, name="TelegramCommandPoller")
        self._polling_thread.start()
        logger.info("Telegram interactive command poller started (/status, /pnl, /pause, /resume, /closeall).")

    def stop_command_poller(self):
        """Stops background command listener."""
        self._stop_polling = True

    def _poll_loop(self):
        """Polling loop fetching new Telegram commands."""
        while not self._stop_polling:
            try:
                url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates?offset={self.last_update_id + 1}&timeout=10"
                req = urllib.request.Request(url, headers={"User-Agent": "GoldBot/2.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        if data.get("ok"):
                            for result in data.get("result", []):
                                self.last_update_id = max(self.last_update_id, result.get("update_id", 0))
                                message = result.get("message", {})
                                text = message.get("text", "").strip()
                                sender_chat_id = str(message.get("chat", {}).get("id", ""))

                                if self.chat_id and sender_chat_id != self.chat_id:
                                    continue

                                if text.startswith("/"):
                                    self._handle_command(text)
            except Exception:
                time.sleep(3)

            time.sleep(1)

    def _handle_command(self, cmd_text: str):
        """Executes interactive remote bot commands across accounts."""
        cmd = cmd_text.split()[0].lower()
        if not self.bot_instance:
            return

        logger.info(f"[TELEGRAM REMOTE COMMAND] Received: {cmd}")

        if cmd in ("/status", "/start", "/help"):
            accounts_summary = self.bot_instance.account_manager.get_all_summaries() if hasattr(self.bot_instance, "account_manager") else []
            lines = ["🤖 *[Funded Trading Bot Live Status]*\n"]
            for acc in accounts_summary:
                lines.append(
                    f"📌 *{acc['name']}* (`{acc['account_id']}`):\n"
                    f"  • *Equity*: ${acc['equity']:.2f} | *Balance*: ${acc['balance']:.2f}\n"
                    f"  • *Daily P&L*: ${acc['daily_pnl']:+.2f} | *Peak*: ${acc['daily_high_water']:.2f}\n"
                    f"  • *Drawdown*: -{acc['daily_drawdown_pct']:.1f}% | *State*: {acc['trading_state']}\n"
                )

            lines.append(
                "Commands:\n"
                "/status - Capital & Account States\n"
                "/pnl - Detailed P&L Breakdown\n"
                "/pause - Pause Live Entries\n"
                "/resume - Resume Live Entries\n"
                "/closeall - Emergency Close All Positions"
            )
            self.send_telegram("\n".join(lines))

        elif cmd == "/pnl":
            lines = ["📊 *[Funded Bot Daily P&L Breakdown]*\n"]
            for acc_id, ctx in getattr(self.bot_instance.account_manager, "accounts", {}).items():
                if ctx.risk_manager:
                    perf = ctx.risk_manager.get_module_performance_summary()
                    lines.append(
                        f"📌 *{ctx.name}* (`{acc_id}`):\n"
                        f"  • *Total Day P&L*: ${perf['total_day_pnl']:+.2f}\n"
                        f"  • *Scalp (#1001)*: ${perf['scalp_pnl']:+.2f} ({perf['scalp_wins']}W / {perf['scalp_trades']} trades)\n"
                        f"  • *Musumali (#2001)*: ${perf['musumali_pnl']:+.2f} ({perf['musumali_wins']}W / {perf['musumali_trades']} trades)\n"
                    )
            self.send_telegram("\n".join(lines))

        elif cmd == "/pause":
            if self.bot_instance:
                self.bot_instance.is_manually_paused = True
                self.send_telegram("⏸ *[Trading Paused]*: New entries halted across all accounts. Existing positions remain managed.")

        elif cmd == "/resume":
            if self.bot_instance:
                self.bot_instance.is_manually_paused = False
                self.send_telegram("▶️ *[Trading Resumed]*: Dual-engine live scanning and execution re-enabled across accounts.")

        elif cmd == "/closeall":
            if self.bot_instance:
                closed_count = 0
                for acc_id, ctx in getattr(self.bot_instance.account_manager, "accounts", {}).items():
                    if ctx.executor:
                        for sym in self.bot_instance.active_broker_symbols.values():
                            positions = ctx.executor.get_open_positions(sym)
                            for pos in positions:
                                ctx.executor.close_position(pos["ticket"], sym, reason="Telegram_Emergency_CloseAll")
                                closed_count += 1
                self.send_telegram(f"🛑 *[Emergency CloseAll]*: Closed {closed_count} open position(s) at market.")
