"""
Main Entry Point for Gold (XAUUSD) Trading Bot
"""

import sys
from src.bot import GoldTradingBot

if __name__ == "__main__":
    bot = GoldTradingBot(config_path="config/config.yaml")
    try:
        bot.start()
    except KeyboardInterrupt:
        print("\nShutting down bot safely...")
        bot.stop()
        sys.exit(0)
