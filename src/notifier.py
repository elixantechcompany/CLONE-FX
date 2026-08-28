"""
Notification and Alert Dispatcher (Telegram & Logging)
Enforces Fix 32: Periodic Self-Reporting Heartbeat and Emergency Circuit Breaker Alerts.
"""

import logging
import urllib.request
import urllib.parse
import json

logger = logging.getLogger("GoldBot.Notifier")


class Notifier:
    def __init__(self, config: dict):
        self.config = config
        self.notif_cfg = config.get("notifications", {})
        self.telegram_enabled = self.notif_cfg.get("telegram_enabled", False)
        self.bot_token = self.notif_cfg.get("telegram_bot_token", "").strip()
        self.chat_id = str(self.notif_cfg.get("telegram_chat_id", "")).strip()

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
