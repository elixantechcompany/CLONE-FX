"""
Real-Time Visual Performance & Liquidity Heatmap Dashboard Exporter
Exports live candle data, detected Musumali liquidity zones, open positions,
and performance metrics to dashboard/data.json for interactive visualization.
"""

import json
import logging
import os
import time
import datetime
from typing import Optional, List, Dict
import pandas as pd
import MetaTrader5 as mt5

logger = logging.getLogger("GoldBot.Dashboard")


class DashboardExporter:
    def __init__(self, config: dict, output_dir: str = "dashboard"):
        self.config = config
        self.dash_cfg = config.get("dashboard", {})
        self.enabled = self.dash_cfg.get("enabled", True)
        self.output_dir = output_dir
        self.export_interval = self.dash_cfg.get("export_interval_seconds", 5)
        self.last_export_time = 0.0
        
        os.makedirs(self.output_dir, exist_ok=True)
        self.data_file = os.path.join(self.output_dir, "data.json")

    def export_data(
        self,
        symbol: str,
        account_summary: dict,
        all_positions: list,
        daily_perf: dict,
        circuit_status: str,
        active_session: str,
        daily_trend: str,
        trend_reason: str,
        zones_data: Optional[List[dict]] = None,
    ):
        """Exports real-time trading and chart data for the web dashboard."""
        if not self.enabled:
            return

        now = time.time()
        if (now - self.last_export_time) < self.export_interval:
            return

        self.last_export_time = now

        try:
            # 1. Fetch recent M5 candles for interactive chart (last 80 bars)
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 80)
            candles = []
            if rates is not None and len(rates) > 0:
                for r in rates:
                    candles.append({
                        "time": int(r["time"]),
                        "open": float(r["open"]),
                        "high": float(r["high"]),
                        "low": float(r["low"]),
                        "close": float(r["close"]),
                        "volume": int(r["tick_volume"]),
                    })

            # 2. Format Open Positions with Position Lifecycle States
            pos_list = []
            for p in all_positions:
                ticket = int(p.get("ticket", 0))
                p_item = {
                    "ticket": ticket,
                    "type": str(p.get("type", "BUY")),
                    "volume": float(p.get("volume", 0.01)),
                    "open_price": float(p.get("price_open", 0.0)),
                    "current_price": float(p.get("price_current", 0.0)),
                    "sl": float(p.get("sl", 0.0)),
                    "tp": float(p.get("tp", 0.0)),
                    "profit": float(p.get("profit", 0.0)),
                    "magic": int(p.get("magic", 1001)),
                    "module": "Micro-Scalper (#1001)" if p.get("magic") == 1001 else "Musumali Sweep (#2001)",
                }
                pos_list.append(p_item)

            # 3. Format Liquidity Zones
            formatted_zones = []
            if zones_data:
                for z in zones_data[-10:]:
                    formatted_zones.append({
                        "price": float(z.get("price", 0.0)),
                        "type": str(z.get("type", "SWING")),
                        "swept": bool(z.get("swept", False)),
                        "timeframe": str(z.get("timeframe", "H1")),
                    })

            # 4. Assemble complete payload
            payload = {
                "last_updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "timestamp": int(now),
                "symbol": symbol,
                "account": {
                    "balance": round(float(account_summary.get("balance", 0.0)), 2),
                    "equity": round(float(account_summary.get("equity", 0.0)), 2),
                    "margin_free": round(float(account_summary.get("margin_free", 0.0)), 2),
                    "margin_level": round(float(account_summary.get("margin_level", 0.0)), 2),
                },
                "performance": {
                    "total_day_pnl": round(float(daily_perf.get("total_day_pnl", 0.0)), 2),
                    "scalp_pnl": round(float(daily_perf.get("scalp_pnl", 0.0)), 2),
                    "scalp_trades": int(daily_perf.get("scalp_trades", 0)),
                    "scalp_wins": int(daily_perf.get("scalp_wins", 0)),
                    "scalp_winrate": round((daily_perf.get("scalp_wins", 0) / max(1, daily_perf.get("scalp_trades", 1))) * 100.0, 1),
                    "musumali_pnl": round(float(daily_perf.get("musumali_pnl", 0.0)), 2),
                    "musumali_trades": int(daily_perf.get("musumali_trades", 0)),
                    "musumali_wins": int(daily_perf.get("musumali_wins", 0)),
                    "musumali_winrate": round((daily_perf.get("musumali_wins", 0) / max(1, daily_perf.get("musumali_trades", 1))) * 100.0, 1),
                },
                "market_state": {
                    "session": active_session,
                    "daily_trend": daily_trend,
                    "trend_reason": trend_reason,
                    "circuit_status": circuit_status,
                },
                "positions": pos_list,
                "zones": formatted_zones,
                "candles": candles,
            }

            # Atomic write
            temp_file = self.data_file + ".tmp"
            with open(temp_file, "w") as f:
                json.dump(payload, f, indent=2)
            os.replace(temp_file, self.data_file)

        except Exception as e:
            logger.warning(f"Error exporting dashboard data: {e}")
