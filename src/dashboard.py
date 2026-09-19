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

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

from src.market_structure import MarketStructureAnalyzer
from src.perfect_setups import PerfectSetupDetector
from src.account_manager import AccountManager
from src.market_schedule import MarketScheduleManager
from src.early_warning import EarlyWarningDetector
from src.ea_engine import EAExecutionEngine

logger = logging.getLogger("GoldBot.Dashboard")


class DashboardExporter:
    def __init__(self, config: dict, output_dir: str = "dashboard"):
        self.config = config
        self.dash_cfg = config.get("dashboard", {})
        self.enabled = self.dash_cfg.get("enabled", True)
        self.output_dir = output_dir
        self.export_interval = self.dash_cfg.get("export_interval_seconds", 2.5)
        self.last_export_time = 0.0

        os.makedirs(self.output_dir, exist_ok=True)
        self.data_file = os.path.join(self.output_dir, "data.json")

        self.structure_analyzer = MarketStructureAnalyzer(config)
        self.setup_detector = PerfectSetupDetector(config)
        self.account_manager = AccountManager()
        self.ea_engine = EAExecutionEngine(config)
        self.master_ea_enabled = True

    def set_master_ea(self, enabled: bool):
        self.master_ea_enabled = bool(enabled)
        logger.info(f"Master EA execution set to: {self.master_ea_enabled}")

    def export_data(
        self,
        active_symbols: Optional[Any] = None,
        accounts_summary: Optional[Any] = None,
        all_positions: Optional[list] = None,
        active_session: str = "Live Autonomous Scanner",
        copy_engine_status: Optional[dict] = None,
        zones_data: Optional[List[dict]] = None,
        symbol: Optional[str] = None,
        account_summary: Optional[dict] = None,
        daily_perf: Optional[dict] = None,
        circuit_status: Optional[str] = None,
        daily_trend: Optional[str] = None,
        trend_reason: Optional[str] = None,
    ):
        """Exports unified real-time dashboard data with Market Structure, Schedules, and Early Warnings."""
        if not self.enabled:
            return

        now = time.time()
        if (now - self.last_export_time) < self.export_interval:
            return

        self.last_export_time = now

        # Normalize parameters
        if isinstance(active_symbols, str):
            symbol = active_symbols
            active_symbols = {"XAUUSD": symbol}
        elif active_symbols is None and symbol is not None:
            active_symbols = {"XAUUSD": symbol}
        elif active_symbols is None:
            active_symbols = {"XAUUSD": "XAUUSDm", "BTCUSD": "BTCUSDm"}

        fleet = self.account_manager.get_fleet_summary()
        if (accounts_summary is None or len(accounts_summary) == 0) and account_summary is not None:
            accounts_summary = [account_summary]
        elif accounts_summary is None or len(accounts_summary) == 0:
            accounts_summary = fleet
        all_positions = all_positions or []

        try:
            # 1. Market Schedules check
            market_schedules = MarketScheduleManager.get_schedule_summary(list(active_symbols.keys()))

            # Primary symbol
            primary_sym = active_symbols.get("XAUUSD", "XAUUSDm")
            if not primary_sym:
                primary_sym = list(active_symbols.values())[0] if active_symbols else "XAUUSD"

            candles = []
            candles_by_symbol = {}

            # 2. Fetch Higher-Timeframe (H4) candles for holding trade analysis
            for sym_key, sym_val in active_symbols.items():
                is_open = market_schedules.get(sym_key, {}).get("is_open", True)
                sym_candles = []

                if is_open and mt5 is not None:
                    rates = mt5.copy_rates_from_pos(sym_val, mt5.TIMEFRAME_H4, 0, 90)
                    if rates is not None and len(rates) > 0:
                        for r in rates:
                            sym_candles.append({
                                "time": int(r["time"]),
                                "open": float(r["open"]),
                                "high": float(r["high"]),
                                "low": float(r["low"]),
                                "close": float(r["close"]),
                                "volume": int(r["tick_volume"]),
                            })

                if not sym_candles:
                    df_fallback = self.structure_analyzer._generate_fallback_rates(sym_val, "H4", count=90)
                    for _, r in df_fallback.iterrows():
                        sym_candles.append({
                            "time": int(r["time"]),
                            "open": float(r["open"]),
                            "high": float(r["high"]),
                            "low": float(r["low"]),
                            "close": float(r["close"]),
                            "volume": int(r["tick_volume"]),
                        })

                candles_by_symbol[sym_key] = sym_candles
                if sym_val == primary_sym or sym_key == "XAUUSD":
                    candles = sym_candles

            m5_candles_by_symbol = candles_by_symbol

            # 3. Format Open Positions
            if (not all_positions or len(all_positions) == 0) and mt5 is not None:
                try:
                    mt5_positions = mt5.positions_get()
                    if mt5_positions:
                        all_positions = []
                        for mp in mt5_positions:
                            p_type_str = "BUY" if mp.type == 0 else "SELL"
                            all_positions.append({
                                "ticket": int(mp.ticket),
                                "account_id": "ACCOUNT_D",
                                "symbol": str(mp.symbol),
                                "type": p_type_str,
                                "volume": float(mp.volume),
                                "price_open": float(mp.price_open),
                                "price_current": float(mp.price_current),
                                "sl": float(mp.sl),
                                "tp": float(mp.tp),
                                "profit": float(mp.profit),
                                "magic": int(mp.magic),
                            })
                except Exception as e:
                    logger.debug(f"Live MT5 positions sync: {e}")

            pos_list = []
            for p in (all_positions or []):
                ticket = int(p.get("ticket", 0))
                p_item = {
                    "ticket": ticket,
                    "account_id": str(p.get("account_id", "")).upper(),
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

            # 4. Market Structure & Perfect Setups Analysis
            structure_all: Dict[str, Any] = {}
            active_setups_all: List[Dict[str, Any]] = []
            forming_setups_all: List[Dict[str, Any]] = []

            for sym_key, sym_val in active_symbols.items():
                struct = self.structure_analyzer.analyze_symbol_structure(sym_val)
                clean_key = sym_key.upper()
                structure_all[clean_key] = struct

                # Only evaluate new live triggers if market is open
                is_open = market_schedules.get(clean_key, {}).get("is_open", True)
                if is_open:
                    cur_spread = 20
                    if mt5 is not None:
                        info = mt5.symbol_info(sym_val)
                        if info:
                            cur_spread = info.spread
                    act_s, form_s = self.setup_detector.evaluate_setups(
                        symbol=sym_val,
                        structure_data=struct,
                        spread_pts=cur_spread,
                    )
                    active_setups_all.extend(act_s)
                    forming_setups_all.extend(form_s)

            # 4b. Autonomous EA Execution Engine (Executes on Magic #2001, isolates manual trades #0)
            if self.master_ea_enabled and active_setups_all:
                try:
                    self.ea_engine.process_active_setups(active_setups_all, self.master_ea_enabled)
                except Exception as e:
                    logger.warning(f"[Dashboard] Autonomous EA execution cycle error: {e}")

            # 5. Early Warning & Profit Defense Analysis
            early_warnings_all = []
            # Check warnings on active setups
            for s in active_setups_all:
                sym_clean = s.get("symbol", "XAUUSD").replace("m", "").replace("_i", "").replace("z", "").upper()
                curr_price = float(structure_all.get(sym_clean, {}).get("current_price", s.get("entry_price", 0.0)))
                w_list = EarlyWarningDetector.analyze_signal_warnings(
                    s, curr_price, m5_candles_by_symbol.get(sym_clean, [])
                )
                s["early_warnings"] = w_list
                for w in w_list:
                    early_warnings_all.append({**w, "source": "SIGNAL", "symbol": sym_clean})

            # Check warnings on open account positions
            pos_warnings = EarlyWarningDetector.evaluate_all_open_positions(pos_list, m5_candles_by_symbol)
            for pw in pos_warnings:
                early_warnings_all.append({**pw, "source": "LIVE_TRADE"})

            primary_struct = structure_all.get(list(structure_all.keys())[0]) if structure_all else {}
            primary_acc = accounts_summary[0] if accounts_summary else {
                "account_id": "NONE",
                "name": "No Accounts Connected",
                "balance": 0.0,
                "equity": 0.0,
                "daily_pnl": 0.0,
                "status": "AWAITING_ACCOUNT",
            }

            killzone_info = PerfectSetupDetector.get_killzone_status()
            cur_p = primary_struct.get("current_price", 2742.50)
            adr_info = PerfectSetupDetector.check_adr_exhaustion(primary_sym, cur_p)

            payload = {
                "last_updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "timestamp": int(now),
                "active_symbols": active_symbols,
                "primary_symbol": primary_sym,
                "active_session": active_session,
                "market_schedules": market_schedules,
                "killzone": killzone_info,
                "adr": adr_info,
                "master_switch": {
                    "primary_switch": "MT5_NATIVE_ALGO_TRADING",
                    "algo_trading_active": self.master_ea_enabled,
                },
                "account": {
                    "balance": round(float(primary_acc.get("balance", 0.0)), 2),
                    "equity": round(float(primary_acc.get("equity", 0.0)), 2),
                    "margin_free": round(float(primary_acc.get("free_margin", primary_acc.get("margin_free", 0.0))), 2),
                },
                "performance": {
                    "total_day_pnl": round(float((daily_perf or {}).get("total_day_pnl", primary_acc.get("daily_pnl", 0.0))), 2),
                },
                "market_state": {
                    "daily_trend": primary_struct.get("macro_bias", daily_trend or "RANGING"),
                    "overall_regime": primary_struct.get("overall_regime", "ACCUMULATION"),
                    "session": active_session,
                    "spread_pts": 20,
                },
                "market_structure": structure_all,
                "perfect_setups": active_setups_all,
                "forming_setups": forming_setups_all,
                "signals_history": self.setup_detector.signals_history or [],
                "early_warnings": early_warnings_all,
                "accounts": accounts_summary,
                "copy_engine": copy_engine_status or {},
                "positions": pos_list,
                "candles": candles,
            }

            temp_file = self.data_file + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            
            # Safe atomic replace with retry on Windows
            for attempt in range(5):
                try:
                    os.replace(temp_file, self.data_file)
                    break
                except PermissionError:
                    time.sleep(0.05)

        except Exception as e:
            logger.warning(f"Error exporting dashboard data: {e}", exc_info=True)

