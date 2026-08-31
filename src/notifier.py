"""
Notification and Alert Dispatcher (Multi-Account & Multi-Symbol Telegram Alerts)
Enforces:
  1. Multi-Account Capital & Performance Monitoring (Accounts A, B, C, D).
  2. Instant Alerts for: Trade Opened, Closed, SL Hit, Early Invalidation Exit,
     Profit Target Reached, Daily Loss Warning, Circuit Trip, Missing SL Fail-Safe,
     Connection Drops, Auto-Recovery.
  3. Interactive Telegram Remote Control:
     - /status, /pnl, /closeall
     - Emergency Kill Switches: /stop_a, /stop_b, /stop_c, /stop_d, /stop_copy, /stop_all
     - Resume Switches: /resume_a, /resume_b, /resume_c, /resume_d, /resume_copy, /resume_all
     (Note: MT5 Native 'Algo Trading' is the Primary Operational Master Switch).
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
            self.send_telegram(f"💓 *[Multi-Account Bot Heartbeat]*\n```\n{heartbeat_text}\n```")

    def notify_trade_event(self, event_type: str, details: str, account_id: str = "account_a"):
        """Sends critical trade execution or circuit breaker alert."""
        if self.telegram_enabled:
            icon = "🚨" if ("CIRCUIT" in event_type or "HARD LOSS" in event_type or "FAIL" in event_type) else ("🎯" if "TARGET" in event_type else "⚡")
            self.send_telegram(f"{icon} *[{event_type} | {account_id.upper()}]*\n{details}")

    def notify_connection_event(self, event_type: str, details: str, account_id: str = "account_a"):
        """Sends connection disruption or recovery alert."""
        if self.telegram_enabled:
            icon = "🔌" if "LOST" in event_type else "✅"
            self.send_telegram(f"{icon} *[{event_type} | {account_id.upper()}]*\n{details}")

    def start_command_poller(self, bot_instance):
        """Starts background listener for interactive Telegram commands."""
        if not self.telegram_enabled or not self.interactive_enabled or not self.bot_token:
            return

        self.bot_instance = bot_instance
        self._stop_polling = False
        self._polling_thread = threading.Thread(target=self._poll_loop, daemon=True, name="TelegramCommandPoller")
        self._polling_thread.start()
        logger.info("Telegram interactive command poller started.")

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
        mgr = getattr(self.bot_instance, "account_manager", None)
        copy_eng = getattr(self.bot_instance, "copy_engine", None)

        if cmd in ("/status", "/start", "/help"):
            accounts_summary = mgr.get_all_summaries() if mgr else []
            lines = [
                "🤖 *[Multi-Account Trading Bot Live Status]*",
                "⚙️ *Master Switch*: MT5 Native 'Algo Trading'\n",
            ]
            for acc in accounts_summary:
                p_tag = f"({acc['account_type']} - {acc['mode']})"
                c_state = acc.get("connection_state", "UNKNOWN")
                algo_state = "🟢 ALGO ON" if acc.get("algo_trading_allowed") else "🔴 ALGO OFF"
                paused_tag = " ⏸ [EMERGENCY PAUSE]" if acc.get("is_paused") else ""
                lines.append(
                    f"📌 *{acc['name']}* `{acc['account_id'].upper()}` {p_tag}:\n"
                    f"  • *State*: `{c_state}` | *Switch*: {algo_state}{paused_tag}\n"
                    f"  • *Equity*: ${acc['equity']:.2f} | *Balance*: ${acc['balance']:.2f}\n"
                    f"  • *Daily P&L*: ${acc['daily_pnl']:+.2f} | *Drawdown*: -{acc['daily_drawdown_pct']:.1f}%\n"
                )

            if copy_eng:
                cp = copy_eng.get_status()
                lines.append(
                    f"🔁 *Copy Engine (C -> D)*: {'⏸ [PAUSED]' if cp['is_paused'] else '▶️ [ACTIVE]'} | Copied: {cp['active_copied_count']}\n"
                )

            lines.append(
                "Commands:\n"
                "/status - Capital & Connection States\n"
                "/pnl - Detailed P&L Breakdown\n"
                "/stop_a, /stop_b, /stop_c, /stop_d - Emergency Stop Specific Account\n"
                "/resume_a, /resume_b, /resume_c, /resume_d - Resume Account\n"
                "/stop_copy, /resume_copy - Control Copy Engine\n"
                "/stop_all, /resume_all - Global Emergency Pause/Resume\n"
                "/closeall - Emergency Close All Positions"
            )
            self.send_telegram("\n".join(lines))

        elif cmd == "/pnl":
            lines = ["📊 *[Multi-Account Daily P&L Breakdown]*\n"]
            for acc_id, ctx in getattr(mgr, "accounts", {}).items():
                if ctx.risk_manager:
                    perf = ctx.risk_manager.get_module_performance_summary()
                    lines.append(
                        f"📌 *{ctx.name}* (`{acc_id.upper()}`):\n"
                        f"  • *Total Day P&L*: ${perf['total_day_pnl']:+.2f}\n"
                        f"  • *Scalp (#1001)*: ${perf['scalp_pnl']:+.2f} ({perf['scalp_wins']}W / {perf['scalp_trades']} trades)\n"
                        f"  • *Musumali (#2001)*: ${perf['musumali_pnl']:+.2f} ({perf['musumali_wins']}W / {perf['musumali_trades']} trades)\n"
                    )
            self.send_telegram("\n".join(lines))

        # Individual Account Emergency Kill Switches
        elif cmd in ("/stop_a", "/stop_account_a"):
            if mgr and mgr.pause_account("account_a", "Telegram /stop_a (Emergency Stop)"):
                self.send_telegram("⏸ *[ACCOUNT A EMERGENCY PAUSED]*: BrightFunded Account A halted. Accounts B, C, D continue trading.")

        elif cmd in ("/resume_a", "/resume_account_a"):
            if mgr and mgr.resume_account("account_a"):
                self.send_telegram("▶️ *[ACCOUNT A RESUMED]*: BrightFunded Account A trading re-enabled.")

        elif cmd in ("/stop_b", "/stop_account_b"):
            if mgr and mgr.pause_account("account_b", "Telegram /stop_b (Emergency Stop)"):
                self.send_telegram("⏸ *[ACCOUNT B EMERGENCY PAUSED]*: BrightFunded Account B halted. Accounts A, C, D continue trading.")

        elif cmd in ("/resume_b", "/resume_account_b"):
            if mgr and mgr.resume_account("account_b"):
                self.send_telegram("▶️ *[ACCOUNT B RESUMED]*: BrightFunded Account B trading re-enabled.")

        elif cmd in ("/stop_c", "/stop_account_c"):
            if mgr and mgr.pause_account("account_c", "Telegram /stop_c (Emergency Stop)"):
                self.send_telegram("⏸ *[ACCOUNT C EMERGENCY PAUSED]*: Master Account C halted.")

        elif cmd in ("/resume_c", "/resume_account_c"):
            if mgr and mgr.resume_account("account_c"):
                self.send_telegram("▶️ *[ACCOUNT C RESUMED]*: Master Account C trading re-enabled.")

        elif cmd in ("/stop_d", "/stop_account_d"):
            if mgr and mgr.pause_account("account_d", "Telegram /stop_d (Emergency Stop)"):
                self.send_telegram("⏸ *[ACCOUNT D EMERGENCY PAUSED]*: Follower Account D halted. Accounts A, B, C continue unaffected.")

        elif cmd in ("/resume_d", "/resume_account_d"):
            if mgr and mgr.resume_account("account_d"):
                self.send_telegram("▶️ *[ACCOUNT D RESUMED]*: Follower Account D trading re-enabled.")

        # Copy Engine Kill Switches
        elif cmd in ("/stop_copy", "/pause_copy"):
            if copy_eng:
                copy_eng.pause_copy_engine("Telegram /stop_copy")
                self.send_telegram("⏸ *[COPY ENGINE PAUSED]*: Copying C -> D halted. Accounts A and B continue trading independently.")

        elif cmd in ("/resume_copy", "/start_copy"):
            if copy_eng:
                copy_eng.resume_copy_engine()
                self.send_telegram("▶️ *[COPY ENGINE RESUMED]*: Copying C -> D re-enabled.")

        # Global Emergency Controls
        elif cmd in ("/stop_all", "/pause"):
            if self.bot_instance:
                self.bot_instance.is_manually_paused = True
                if mgr:
                    mgr.pause_all("Global /stop_all (Emergency Stop)")
                self.send_telegram("🛑 *[GLOBAL EMERGENCY PAUSE]*: New entries halted across all accounts. Existing positions remain managed.")

        elif cmd in ("/resume_all", "/resume"):
            if self.bot_instance:
                self.bot_instance.is_manually_paused = False
                if mgr:
                    mgr.resume_all()
                self.send_telegram("▶️ *[GLOBAL RESUME]*: Trading re-enabled across all active accounts.")

        elif cmd == "/closeall":
            if self.bot_instance and mgr:
                closed_count = 0
                for acc_id, ctx in mgr.accounts.items():
                    if ctx.executor:
                        for sym in self.bot_instance.active_broker_symbols.values():
                            positions = ctx.executor.get_open_positions(sym)
                            for pos in positions:
                                ctx.executor.close_position(pos["ticket"], sym, reason="Telegram_Emergency_CloseAll")
                                closed_count += 1
                self.send_telegram(f"🛑 *[Emergency CloseAll]*: Closed {closed_count} open position(s) at market.")
