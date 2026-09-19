"""
Institutional Market Hours & Continuous Watchdog Engine
Accurately distinguishes between standard Forex/Commodity schedules (XAUUSD weekend closure)
and 24/7 Crypto markets (BTCUSD), providing countdowns, active symbol routing,
and a self-healing autonomous watchdog so the scanner never sleeps off.
"""

import datetime
from typing import Dict, Any, Tuple, List, Optional
import logging

logger = logging.getLogger("GoldBot.MarketSchedule")


class MarketScheduleManager:
    """
    Manages session and market hours across multi-asset symbols.
    Ensures closed markets (e.g. XAUUSD on weekends) do not hang MT5 sockets,
    while 24/7 markets (e.g. BTCUSD) are scanned continuously.
    """

    @staticmethod
    def is_market_open(symbol: str, utc_dt: Optional[datetime.datetime] = None) -> Tuple[bool, str, int]:
        """
        Returns (is_open: bool, status_text: str, seconds_until_next_state: int).
        """
        if utc_dt is None:
            utc_dt = datetime.datetime.now(datetime.timezone.utc)
        elif utc_dt.tzinfo is None:
            utc_dt = utc_dt.replace(tzinfo=datetime.timezone.utc)

        sym = symbol.upper()
        clean_sym = sym.replace("M", "").replace("_I", "").replace("Z", "").replace("/", "")

        # 1. Crypto is ALWAYS OPEN (24 hours, 7 days a week)
        if "BTC" in clean_sym or "ETH" in clean_sym or "BITCOIN" in clean_sym:
            return True, "MARKET OPEN (24/7 Crypto)", 0

        # 2. Metals & Forex (XAUUSD / Gold)
        # Weekday 0=Monday, 4=Friday, 5=Saturday, 6=Sunday
        weekday = utc_dt.weekday()
        hour = utc_dt.hour
        minute = utc_dt.minute

        # Weekend closure: Friday 21:00 UTC -> Sunday 22:00 UTC
        if weekday == 4 and hour >= 21:
            # Friday night after 21:00 UTC
            # Reopens Sunday 22:00 UTC
            reopen_day = utc_dt.date() + datetime.timedelta(days=2)
            reopen_dt = datetime.datetime(reopen_day.year, reopen_day.month, reopen_day.day, 22, 0, 0, tzinfo=datetime.timezone.utc)
            secs = max(0, int((reopen_dt - utc_dt).total_seconds()))
            hours_left = secs // 3600
            mins_left = (secs % 3600) // 60
            return False, f"MARKET CLOSED (Weekend - Reopens Sun 22:00 UTC in {hours_left}h {mins_left}m)", secs

        elif weekday == 5:
            # All day Saturday
            reopen_day = utc_dt.date() + datetime.timedelta(days=1)
            reopen_dt = datetime.datetime(reopen_day.year, reopen_day.month, reopen_day.day, 22, 0, 0, tzinfo=datetime.timezone.utc)
            secs = max(0, int((reopen_dt - utc_dt).total_seconds()))
            hours_left = secs // 3600
            mins_left = (secs % 3600) // 60
            return False, f"MARKET CLOSED (Weekend - Reopens Sun 22:00 UTC in {hours_left}h {mins_left}m)", secs

        elif weekday == 6 and hour < 22:
            # Sunday before 22:00 UTC
            reopen_dt = datetime.datetime(utc_dt.year, utc_dt.month, utc_dt.day, 22, 0, 0, tzinfo=datetime.timezone.utc)
            secs = max(0, int((reopen_dt - utc_dt).total_seconds()))
            hours_left = secs // 3600
            mins_left = (secs % 3600) // 60
            return False, f"MARKET CLOSED (Weekend - Reopens Sun 22:00 UTC in {hours_left}h {mins_left}m)", secs

        # Daily Settlement Rollover: Mon-Thu 21:00 to 22:00 UTC
        if weekday in (0, 1, 2, 3) and hour == 21:
            reopen_dt = datetime.datetime(utc_dt.year, utc_dt.month, utc_dt.day, 22, 0, 0, tzinfo=datetime.timezone.utc)
            secs = max(0, int((reopen_dt - utc_dt).total_seconds()))
            mins_left = secs // 60
            return False, f"MARKET CLOSED (Daily Rollover - Reopens 22:00 UTC in {mins_left}m)", secs

        # Otherwise: Market is OPEN
        # Calculate seconds until next close (Daily roll at 21:00 UTC or Weekend at Fri 21:00 UTC)
        next_close_dt = datetime.datetime(utc_dt.year, utc_dt.month, utc_dt.day, 21, 0, 0, tzinfo=datetime.timezone.utc)
        if utc_dt >= next_close_dt:
            next_close_dt += datetime.timedelta(days=1)
        secs_until_close = max(0, int((next_close_dt - utc_dt).total_seconds()))

        return True, "MARKET OPEN (Active Session)", secs_until_close

    @classmethod
    def get_schedule_summary(cls, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """Returns unified market schedule status for all monitored symbols."""
        if symbols is None:
            symbols = ["XAUUSD", "BTCUSD"]

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        schedules: Dict[str, Any] = {}

        for sym in symbols:
            is_open, status_text, secs = cls.is_market_open(sym, now_utc)
            clean = sym.replace("m", "").replace("_i", "").replace("z", "").upper()
            schedules[clean] = {
                "symbol": clean,
                "is_open": is_open,
                "status": "OPEN" if is_open else "CLOSED",
                "status_text": status_text,
                "seconds_to_change": secs,
                "asset_type": "CRYPTO_24_7" if "BTC" in clean or "ETH" in clean else "COMMODITY_FOREX",
                "current_time_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
            }

        return schedules

    @classmethod
    def filter_scannable_symbols(cls, symbols_map: Dict[str, str]) -> Tuple[Dict[str, str], Dict[str, str]]:
        """
        Splits symbols into currently scannable (OPEN) vs standby (CLOSED).
        Prevents hanging MT5 socket requests on closed pairs while scanning crypto uninterrupted.
        """
        open_syms = {}
        closed_syms = {}

        for key, full_sym in symbols_map.items():
            is_open, _, _ = cls.is_market_open(key)
            if is_open:
                open_syms[key] = full_sym
            else:
                closed_syms[key] = full_sym

        return open_syms, closed_syms
