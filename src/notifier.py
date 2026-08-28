"""
Notification and Alert Dispatcher (Telegram & Logging)
Enforces Fix 32: Periodic Self-Reporting Heartbeat, Emergency Circuit Breaker Alerts,
and Interactive Telegram Bot Remote Control (/status, /pnl, /pause, /resume, /closeall).
"""

import logging
import urllib.request
import urllib.parse
import json
import threading
import time
from typing import Optional, Callable

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
            req = urllib.request.Request(url, data=data, headers={"User-Agent": "GoldBot/1.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                return resp.status == 200
        except Exception as e:
            logger.warning(f"Telegram dispatch failed: {e}")
            return False

    def notify_heartbeat(self, heartbeat_text: str):
        """Sends periodic self-reporting heartbeat."""
        if self.telegram_enabled:
            self.send_telegram(f"💓 *[GoldBot Heartbeat]*\n```\n{heartbeat_text}\n```")

    def notify_trade_event(self, event_type: str, details: str):
        """Sends critical trade execution or circuit breaker alert."""
        if self.telegram_enabled:
            icon = "🚨" if "CIRCUIT" in event_type or "HARD LOSS" in event_type else "🎯"
            self.send_telegram(f"{icon} *[{event_type}]*\n{details}")

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
                req = urllib.request.Request(url, headers={"User-Agent": "GoldBot/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        if data.get("ok"):
                            for result in data.get("result", []):
                                self.last_update_id = max(self.last_update_id, result.get("update_id", 0))
                                message = result.get("message", {})
                                text = message.get("text", "").strip()
                                sender_chat_id = str(message.get("chat", {}).get("id", ""))

                                # Security check: only allow commands from authorized chat_id
                                if self.chat_id and sender_chat_id != self.chat_id:
                                    continue

                                if text.startswith("/"):
                                    self._handle_command(text)
            except Exception as e:
                # Network glitch or timeout - wait briefly and retry
                time.sleep(3)

            time.sleep(1)

    def _handle_command(self, cmd_text: str):
        """Executes interactive remote bot commands."""
        cmd = cmd_text.split()[0].lower()
        if not self.bot_instance:
            return

        logger.info(f"[TELEGRAM REMOTE COMMAND] Received: {cmd}")

        if cmd in ("/status", "/start", "/help"):
            acc = self.bot_instance.connector.get_account_summary() if self.bot_instance.connector else {}
            equity = acc.get("equity", 0.0)
            balance = acc.get("balance", 0.0)
            positions = self.bot_instance.executor.get_open_positions(self.bot_instance.active_symbol) if self.bot_instance.executor else []
            cb_status = self.bot_instance.risk_manager.get_circuit_breaker_status() if self.bot_instance.risk_manager else "N/A"
            session_name = self.bot_instance.risk_manager.get_current_trading_session() if self.bot_instance.risk_manager else "N/A"
            
            resp = (
                f"🤖 *[GoldBot Live Status]*\n"
                f"• *Equity*: ${equity:.2f} | *Balance*: ${balance:.2f}\n"
                f"• *Active Session*: {session_name}\n"
                f"• *Open Trades*: {len(positions)}/{self.bot_instance.total_max_open}\n"
                f"• *Circuit Breakers*: {cb_status}\n\n"
                f"Available Commands:\n"
                f"/status - Live Capital & Positions\n"
                f"/pnl - Daily Performance Breakdown\n"
                f"/pause - Pause New Trade Entries\n"
                f"/resume - Resume Live Entries\n"
                f"/closeall - Emergency Close Open Trades"
            )
            self.send_telegram(resp)

        elif cmd == "/pnl":
            if self.bot_instance.risk_manager:
                perf = self.bot_instance.risk_manager.get_module_performance_summary()
                resp = (
                    f"📊 *[GoldBot Performance Breakdown]*\n"
                    f"• *Total Day P&L*: ${perf['total_day_pnl']:+.2f}\n"
                    f"• *Scalp (#1001)*: ${perf['scalp_pnl']:+.2f} ({perf['scalp_wins']}W / {perf['scalp_trades']} trades)\n"
                    f"• *Musumali (#2001)*: ${perf['musumali_pnl']:+.2f} ({perf['musumali_wins']}W / {perf['musumali_trades']} trades)"
                )
                self.send_telegram(resp)

        elif cmd == "/pause":
            if self.bot_instance:
                self.bot_instance.is_manually_paused = True
                self.send_telegram("⏸ *[Trading Paused]*: New entries halted across both modules. Existing positions remain managed.")

        elif cmd == "/resume":
            if self.bot_instance:
                self.bot_instance.is_manually_paused = False
                self.send_telegram("▶️ *[Trading Resumed]*: Dual-engine live scanning and execution re-enabled.")

        elif cmd == "/closeall":
            if self.bot_instance and self.bot_instance.executor and self.bot_instance.active_symbol:
                positions = self.bot_instance.executor.get_open_positions(self.bot_instance.active_symbol)
                count = len(positions)
                for pos in positions:
                    self.bot_instance.executor.close_position(pos["ticket"], self.bot_instance.active_symbol, reason="Telegram_Manual_CloseAll")
                self.send_telegram(f"🛑 *[Emergency CloseAll]*: Closed {count} open position(s) at market.")
