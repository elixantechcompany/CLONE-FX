"""
Real-Time Multi-Symbol & Multi-Account Dashboard Exporter
Exports live candle data, open positions across accounts, performance metrics,
copy engine states, Connection State Machine states, and MT5 Algo Trading switch status to dashboard/data.json.
"""

import json
import logging
import os
import time
import datetime
from typing import Optional, List, Dict, Any
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
        active_symbols: Optional[Any] = None,
        accounts_summary: Optional[Any] = None,
        all_positions: Optional[list] = None,
        active_session: str = "London",
        copy_engine_status: Optional[dict] = None,
        zones_data: Optional[List[dict]] = None,
        symbol: Optional[str] = None,
        account_summary: Optional[dict] = None,
        daily_perf: Optional[dict] = None,
        circuit_status: Optional[str] = None,
        daily_trend: Optional[str] = None,
        trend_reason: Optional[str] = None,
    ):
        """Exports unified real-time dashboard data with Connection State Machine and MT5 Algo Trading status."""
        if not self.enabled:
            return

        now = time.time()
        if (now - self.last_export_time) < self.export_interval:
            return

        self.last_export_time = now

        # Normalize parameters for backward compatibility
        if isinstance(active_symbols, str):
            symbol = active_symbols
            active_symbols = {"XAUUSD": symbol}
        elif active_symbols is None and symbol is not None:
            active_symbols = {"XAUUSD": symbol}
        elif active_symbols is None:
            active_symbols = {"XAUUSD": "XAUUSDm"}

        if accounts_summary is None and account_summary is not None:
            accounts_summary = [{
                "account_id": "account_a",
                "name": "BrightFunded Account A",
                "balance": account_summary.get("balance", 1000.0),
                "equity": account_summary.get("equity", 1000.0),
                "daily_pnl": daily_perf.get("total_day_pnl", 0.0) if daily_perf else 0.0,
                "trading_state": "NORMAL",
                "connection_state": "CONNECTED_TRADING_ALLOWED",
                "algo_trading_allowed": True,
                "daily_drawdown_pct": 0.0,
            }]
        elif accounts_summary is None:
            accounts_summary = []

        all_positions = all_positions or []

        try:
            # 1. Fetch recent M5 candles for primary symbol
            primary_sym = active_symbols.get("XAUUSD") if isinstance(active_symbols, dict) else "XAUUSDm"
            if not primary_sym:
                primary_sym = list(active_symbols.values())[0] if isinstance(active_symbols, dict) and active_symbols else "XAUUSD"
            rates = mt5.copy_rates_from_pos(primary_sym, mt5.TIMEFRAME_M5, 0, 80)
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

            # 2. Format Open Positions
            pos_list = []
            for p in all_positions:
                ticket = int(p.get("ticket", 0))
                p_item = {
                    "ticket": ticket,
                    "account_id": str(p.get("account_id", "ACCOUNT_A")).upper(),
                    "symbol": str(p.get("symbol", "XAUUSDm")),
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

            primary_acc = accounts_summary[0] if accounts_summary else {"equity": 1000.0, "balance": 1000.0, "daily_pnl": 0.0}
            payload = {
                "last_updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "timestamp": int(now),
                "active_symbols": active_symbols,
                "primary_symbol": primary_sym,
                "active_session": active_session,
                "master_switch": {
                    "primary_switch": "MT5_NATIVE_ALGO_TRADING",
                    "algo_trading_active": any(a.get("algo_trading_allowed", False) for a in accounts_summary) if accounts_summary else True,
                },
                "account": {
                    "balance": round(float(primary_acc.get("balance", 1000.0)), 2),
                    "equity": round(float(primary_acc.get("equity", 1000.0)), 2),
                    "margin_free": round(float(primary_acc.get("free_margin", primary_acc.get("margin_free", 1000.0))), 2),
                },
                "performance": {
                    "total_day_pnl": round(float(primary_acc.get("daily_pnl", 0.0)), 2),
                },
                "accounts": accounts_summary,
                "copy_engine": copy_engine_status or {},
                "positions": pos_list,
                "candles": candles,
            }

            temp_file = self.data_file + ".tmp"
            with open(temp_file, "w") as f:
                json.dump(payload, f, indent=2)
            os.replace(temp_file, self.data_file)

        except Exception as e:
            logger.warning(f"Error exporting dashboard data: {e}")
