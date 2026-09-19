"""
Account & Multi-Terminal Fleet Manager
Handles dynamic account creation (min $20 balance), local MT5 terminal process orchestration,
daily balance baselines, prop-firm circuit breakers, and synchronization with Supabase & UI.
"""

import os
import sys
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any
import yaml
from dotenv import load_dotenv

logger = logging.getLogger("GoldBot.AccountManager")


class AccountManager:
    def __init__(self, config_path: str = "config/config.yaml", env_path: str = "config/.env"):
        self.config_path = Path(config_path)
        self.env_path = Path(env_path)
        self.config: Dict[str, Any] = {}
        self.accounts: List[Dict[str, Any]] = []
        self.daily_baselines: Dict[str, float] = {}
        self.high_water_marks: Dict[str, float] = {}
        self.load_all()

    def load_all(self):
        """Loads configuration and accounts from YAML and environment variables."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.config = yaml.safe_load(f) or {}
            except Exception as e:
                logger.error(f"Failed to load {self.config_path}: {e}")
                self.config = {}

        if self.env_path.exists():
            load_dotenv(self.env_path)
        load_dotenv()

        acc_cfg = self.config.get("accounts", {})
        raw_list = acc_cfg.get("account_list", [])
        self.accounts = []

        for item in raw_list:
            acc_id = item.get("id", "").lower()
            if not acc_id:
                continue

            # Resolve credentials from env
            login_var = item.get("env_login_var")
            pass_var = item.get("env_password_var")
            srv_var = item.get("env_server_var")
            path_var = item.get("env_path_var")

            login = os.getenv(login_var) if login_var else None
            password = os.getenv(pass_var) if pass_var else None
            server = os.getenv(srv_var) if srv_var else None
            mt5_path = os.getenv(path_var) if path_var else None

            # Check fallbacks
            if not login and item.get("fallback_login_var"):
                login = os.getenv(item.get("fallback_login_var"))
            if not password and item.get("fallback_password_var"):
                password = os.getenv(item.get("fallback_password_var"))
            if not server and item.get("fallback_server_var"):
                server = os.getenv(item.get("fallback_server_var"))

            acc_data = {
                "id": acc_id,
                "name": item.get("name", f"Account {acc_id.upper()}"),
                "type": item.get("type", "PERSONAL"),  # PERSONAL, BRIGHTFUNDED, PROP_FIRM
                "balance": float(item.get("balance", 20.0)),
                "equity": float(item.get("balance", 20.0)),
                "mode": item.get("mode", "INDEPENDENT"),  # INDEPENDENT, COPY_MASTER, COPY_FOLLOWER
                "execution_mode": item.get("execution_mode", "AUTOMATED_EA"),  # AUTOMATED_EA, VISUAL_SCANNER
                "max_daily_loss_pct": float(item.get("max_daily_loss_pct", 4.0 if item.get("type") == "BRIGHTFUNDED" else 10.0)),
                "risk_per_trade_pct": float(item.get("risk_per_trade_pct", 0.25 if item.get("type") == "BRIGHTFUNDED" else 1.0)),
                "min_rr": float(item.get("min_rr", 2.0)),
                "login": login,
                "password": password,
                "server": server,
                "path": mt5_path or self._detect_default_mt5_path(acc_id),
                "is_active": item.get("is_active", True),
                "connection_state": "DISCONNECTED",
                "circuit_breaker_tripped": False,
                "daily_pnl": 0.0,
            }

            # Initialize daily baseline tracking
            if acc_id not in self.daily_baselines:
                self.daily_baselines[acc_id] = acc_data["balance"]
            if acc_id not in self.high_water_marks:
                self.high_water_marks[acc_id] = acc_data["balance"]

            self.accounts.append(acc_data)

    def _detect_default_mt5_path(self, acc_id: str) -> str:
        """Autodetects common MT5 terminal installations on Windows."""
        common_paths = [
            r"C:\Program Files\MetaTrader 5\terminal64.exe",
            r"C:\Users\PwezaCore\Desktop\MT5_Account_C\terminal64.exe",
            r"C:\Users\PwezaCore\Desktop\MT5 NEW ACC\FBS DEMO\terminal64.exe",
            r"C:\Program Files\Exness MetaTrader 5\terminal64.exe",
            r"C:\Program Files\HFM MetaTrader 5\terminal64.exe",
        ]
        if "c" in acc_id and os.path.exists(r"C:\Users\PwezaCore\Desktop\MT5_Account_C\terminal64.exe"):
            return r"C:\Users\PwezaCore\Desktop\MT5_Account_C\terminal64.exe"
        if "d" in acc_id and os.path.exists(r"C:\Users\PwezaCore\Desktop\MT5 NEW ACC\FBS DEMO\terminal64.exe"):
            return r"C:\Users\PwezaCore\Desktop\MT5 NEW ACC\FBS DEMO\terminal64.exe"
        for p in common_paths:
            if os.path.exists(p):
                return p
        return r"C:\Program Files\MetaTrader 5\terminal64.exe"

    def add_account(
        self,
        name: str,
        account_type: str,
        balance: float,
        login: str,
        password: str,
        server: str,
        path: Optional[str] = None,
        mode: str = "INDEPENDENT",
        execution_mode: str = "AUTOMATED_EA",
        max_daily_loss_pct: Optional[float] = None,
        risk_per_trade_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Creates and registers a new trading account.
        Enforces a minimum balance floor of $20.00 USD.
        """
        # Strict $20 Minimum Validation
        balance_float = float(balance)
        if balance_float < 20.0:
            raise ValueError(f"Account creation rejected: Minimum balance required is $20.00 USD (Got: ${balance_float:.2f})")

        acc_num = len(self.accounts) + 1
        acc_id = f"account_{chr(96 + acc_num)}"  # account_e, account_f, etc.

        # Auto-configure safe prop-firm risk limits
        is_prop = (account_type or "").upper() in ["BRIGHTFUNDED", "PROP_FIRM", "CHALLENGE"]
        loss_pct = max_daily_loss_pct if max_daily_loss_pct is not None else (4.0 if is_prop else 10.0)
        risk_pct = risk_per_trade_pct if risk_per_trade_pct is not None else (0.25 if is_prop else 1.0)

        terminal_path = path or self._detect_default_mt5_path(acc_id)

        # 1. Update .env variables
        env_prefix = acc_id.upper()
        self._append_to_env({
            f"{env_prefix}_LOGIN": str(login).strip(),
            f"{env_prefix}_PASSWORD": str(password).strip(),
            f"{env_prefix}_SERVER": str(server).strip(),
            f"{env_prefix}_MT5_PATH": str(terminal_path).strip(),
        })

        # 2. Add to config.yaml account_list
        yaml_entry = {
            "id": acc_id,
            "name": name.strip(),
            "type": account_type.upper(),
            "balance": balance_float,
            "mode": mode.upper(),
            "execution_mode": execution_mode.upper(),
            "copy_enabled": (mode.upper() == "COPY_FOLLOWER" or mode.upper() == "COPY_MASTER"),
            "max_daily_loss_pct": loss_pct,
            "risk_per_trade_pct": risk_pct,
            "min_rr": 2.0,
            "env_login_var": f"{env_prefix}_LOGIN",
            "env_password_var": f"{env_prefix}_PASSWORD",
            "env_server_var": f"{env_prefix}_SERVER",
            "env_path_var": f"{env_prefix}_MT5_PATH",
            "is_active": True,
        }

        if "accounts" not in self.config:
            self.config["accounts"] = {"enabled": True, "multi_account_mode": True, "account_list": []}
        if "account_list" not in self.config["accounts"]:
            self.config["accounts"]["account_list"] = []

        self.config["accounts"]["account_list"].append(yaml_entry)
        self._save_config()

        # 3. Reload in-memory list
        self.load_all()

        # 4. Sync to Supabase
        self.sync_account_to_supabase(yaml_entry)

        logger.info(f"Successfully created and registered {acc_id.upper()}: {name} (${balance_float:.2f})")
        return yaml_entry

    def toggle_execution_mode(self, acc_id: str, new_mode: str) -> Dict[str, Any]:
        """Toggles an account between 'AUTOMATED_EA' and 'VISUAL_SCANNER'."""
        acc_id = acc_id.lower()
        if new_mode not in ["AUTOMATED_EA", "VISUAL_SCANNER"]:
            raise ValueError("Mode must be either 'AUTOMATED_EA' or 'VISUAL_SCANNER'")

        for item in self.config.get("accounts", {}).get("account_list", []):
            if item.get("id") == acc_id:
                item["execution_mode"] = new_mode
                self._save_config()
                self.load_all()
                logger.info(f"[{acc_id.upper()}] Execution mode updated to {new_mode}")
                return item

        raise KeyError(f"Account {acc_id} not found")

    def remove_account(self, acc_id: str) -> bool:
        """Removes an account from configuration and in-memory fleet."""
        acc_id = acc_id.lower()
        acc_list = self.config.get("accounts", {}).get("account_list", [])
        original_len = len(acc_list)
        filtered = [a for a in acc_list if a.get("id", "").lower() != acc_id]

        if len(filtered) < original_len:
            self.config["accounts"]["account_list"] = filtered
            self._save_config()
            self.load_all()
            logger.info(f"Account [{acc_id.upper()}] removed from fleet.")
            return True
        return False

    @staticmethod
    def resolve_system_mt5_path(custom_path: Optional[str] = None) -> Optional[str]:
        """Resolves valid MT5 terminal64.exe executable from custom path or standard Windows locations."""
        if custom_path and os.path.exists(custom_path):
            return custom_path

        candidates = [
            r"C:\Program Files\MetaTrader 5\terminal64.exe",
            r"C:\Program Files\Exness MT5\terminal64.exe",
            r"C:\Program Files\Exness MetaTrader 5\terminal64.exe",
            r"C:\Program Files\FTMO MetaTrader 5\terminal64.exe",
            r"C:\Program Files\BrightFunded MT5\terminal64.exe",
            r"C:\Program Files\MetaTrader 5 Terminal\terminal64.exe",
            os.path.expanduser(r"~\AppData\Local\Programs\MetaTrader 5\terminal64.exe"),
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return None

    def launch_terminal(self, acc_id: str) -> bool:
        """
        Launches the dedicated MT5 terminal executable for this account locally.
        Runs terminal64.exe as a detached background process.
        """
        acc_id = acc_id.lower()
        acc = next((a for a in self.accounts if a["id"] == acc_id), None)

        path = self.resolve_system_mt5_path(acc.get("path") if acc else None)
        if not path:
            logger.error("Cannot launch terminal: MT5 executable not found on system")
            return False

        try:
            terminal_dir = str(Path(path).parent)
            logger.info(f"Launching MT5 terminal process for [{acc_id.upper() if acc else 'DEFAULT'}] -> {path}")
            subprocess.Popen([path], cwd=terminal_dir, shell=False)
            return True
        except Exception as e:
            logger.error(f"Failed to launch terminal for {acc_id}: {e}")
            return False

    def launch_all_terminals(self) -> List[Dict[str, Any]]:
        """Launches all distinct MT5 terminals across configured active accounts."""
        results = []
        launched_paths = set()

        for acc in self.accounts:
            if not acc.get("is_active"):
                continue
            path = acc.get("path")
            if path and path not in launched_paths:
                success = self.launch_terminal(acc["id"])
                results.append({"id": acc["id"], "path": path, "launched": success})
                if success:
                    launched_paths.add(path)
        return results

    def update_account_equity(self, acc_id: str, equity: float) -> Dict[str, Any]:
        """
        Updates live equity and checks Prop Firm Drawdown circuit breaker.
        Circuit Breaker triggers if (Baseline - Equity) >= Max Allowed Loss.
        """
        acc_id = acc_id.lower()
        acc = next((a for a in self.accounts if a["id"] == acc_id), None)
        if not acc:
            return {}

        baseline = self.daily_baselines.get(acc_id, acc["balance"])
        max_allowed_loss = baseline * (acc["max_daily_loss_pct"] / 100.0)
        current_loss = baseline - equity

        acc["equity"] = equity
        acc["daily_pnl"] = equity - baseline
        acc["daily_drawdown_dollars"] = max(0.0, current_loss)
        acc["daily_drawdown_pct"] = (max(0.0, current_loss) / baseline) * 100.0

        # Update high water mark
        if equity > self.high_water_marks.get(acc_id, 0.0):
            self.high_water_marks[acc_id] = equity

        # Check Circuit Breaker
        if current_loss >= max_allowed_loss:
            acc["circuit_breaker_tripped"] = True
            logger.warning(f"⚠️ [CIRCUIT BREAKER TRIGGERED] {acc_id.upper()} ({acc['name']}): Loss ${current_loss:.2f} >= Limit ${max_allowed_loss:.2f}! Trading Halted.")
        else:
            acc["circuit_breaker_tripped"] = False

        return acc

    def get_fleet_summary(self) -> List[Dict[str, Any]]:
        """Returns structured status of all trading accounts for the UI."""
        self.load_all()
        summary = []
        for a in self.accounts:
            balance = a["balance"]
            equity = a.get("equity", balance)
            daily_pnl = a.get("daily_pnl", 0.0)
            connection_state = a.get("connection_state", "DISCONNECTED")

            # Check live MT5 terminal connection if available
            try:
                import MetaTrader5 as mt5
                term_path = self.resolve_system_mt5_path(a.get("path"))
                init_ok = mt5.initialize(path=term_path) if term_path else mt5.initialize()
                if init_ok:
                    acc_info = mt5.account_info()
                    term_info = mt5.terminal_info()
                    if acc_info and (not a.get("login") or str(acc_info.login) == str(a.get("login"))):
                        balance = float(acc_info.balance)
                        equity = float(acc_info.equity)
                        daily_pnl = float(acc_info.profit)
                        connection_state = "CONNECTED" if (term_info and term_info.connected) else "TERMINAL_OPEN"
                        a["balance"] = balance
                        a["equity"] = equity
                        a["daily_pnl"] = daily_pnl
                        a["connection_state"] = connection_state
            except Exception as e:
                logger.debug(f"Live MT5 sync check: {e}")

            baseline = self.daily_baselines.get(a["id"], balance)
            max_loss_dollars = baseline * (a["max_daily_loss_pct"] / 100.0)
            cur_loss = baseline - equity
            drawdown_pct = max(0.0, (cur_loss / baseline) * 100.0)

            summary.append({
                "id": a["id"],
                "name": a["name"],
                "type": a["type"],
                "balance": balance,
                "equity": equity,
                "daily_pnl": daily_pnl,
                "daily_drawdown_pct": round(drawdown_pct, 2),
                "max_daily_loss_pct": a["max_daily_loss_pct"],
                "max_daily_loss_dollars": round(max_loss_dollars, 2),
                "risk_per_trade_pct": a["risk_per_trade_pct"],
                "min_rr": a["min_rr"],
                "mode": a["mode"],
                "execution_mode": a.get("execution_mode", "AUTOMATED_EA"),
                "circuit_breaker_tripped": a.get("circuit_breaker_tripped", False),
                "connection_state": connection_state,
                "path": a.get("path"),
                "is_active": a.get("is_active", True),
            })
        return summary

    def sync_account_to_supabase(self, acc_entry: Dict[str, Any]):
        """Persists account entry into Supabase accounts_overview table."""
        try:
            import urllib.request
            url = os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "https://xeckbeavsvyoporldjzm.supabase.co"
            key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
            if not key:
                return

            rest_url = f"{url}/rest/v1/accounts_overview"
            payload = json.dumps({
                "account_id": acc_entry["id"],
                "name": acc_entry["name"],
                "account_type": acc_entry["type"],
                "balance": acc_entry["balance"],
                "equity": acc_entry["balance"],
                "daily_pnl": 0.0,
                "daily_drawdown_pct": 0.0,
                "is_active": acc_entry["is_active"],
            }).encode("utf-8")

            req = urllib.request.Request(
                rest_url,
                data=payload,
                headers={
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "Prefer": "resolution=merge-duplicates",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as res:
                logger.info(f"Synced account {acc_entry['id']} to Supabase: status {res.status}")
        except Exception as e:
            logger.warning(f"Supabase sync notice: {e}")

    def _append_to_env(self, key_values: Dict[str, str]):
        """Appends new credential environment variables to .env."""
        try:
            existing_lines = []
            if self.env_path.exists():
                with open(self.env_path, "r", encoding="utf-8") as f:
                    existing_lines = f.readlines()

            keys_written = set()
            new_lines = []
            for line in existing_lines:
                found = False
                for k, v in key_values.items():
                    if line.strip().startswith(f"{k}="):
                        new_lines.append(f"{k}={v}\n")
                        keys_written.add(k)
                        found = True
                        break
                if not found:
                    new_lines.append(line)

            for k, v in key_values.items():
                if k not in keys_written:
                    new_lines.append(f"{k}={v}\n")

            with open(self.env_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
        except Exception as e:
            logger.error(f"Failed to update {self.env_path}: {e}")

    def _save_config(self):
        """Serializes updated config back to config/config.yaml."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(self.config, f, default_flow_style=False, sort_keys=False)
        except Exception as e:
            logger.error(f"Failed to write config: {e}")
