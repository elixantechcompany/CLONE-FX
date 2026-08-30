"""
Main Entry Point for Gold (XAUUSD) Trading Bot with Infinite Self-Healing Watchdog
"""

import sys
import time
import logging
from src.bot import GoldTradingBot

if __name__ == "__main__":
    retry_delay = 5
    while True:
        bot = None
        try:
            bot = GoldTradingBot(config_path="config/config.yaml")
            bot.start()
        except KeyboardInterrupt:
            print("\n[MANUAL SHUTDOWN] Shutting down bot safely...")
            if bot:
                try:
                    bot.stop()
                except Exception:
                    pass
            sys.exit(0)
        except Exception as e:
            print(f"\n[CRITICAL RESILIENCE WATCHDOG] Bot process encountered disruption: {e}")
            print(f"[CRITICAL RESILIENCE WATCHDOG] Automatically restarting bot in {retry_delay} seconds...")
            if bot:
                try:
                    bot.stop()
                except Exception:
                    pass
            time.sleep(retry_delay)

