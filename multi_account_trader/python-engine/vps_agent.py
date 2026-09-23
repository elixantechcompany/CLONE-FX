"""
vps_agent.py — Production-Ready Multi-Account VPS Trading Agent
===============================================================
XAUUSD automated execution engine for AWS Windows VPS.

Strategy logic:
  - 50 EMA multi-timeframe filter  : price must be above EMA on BOTH H4 and H1
                                      to allow BUY; below both for SELL.
  - ATR stop-loss (1.5 × ATR-14)   : dynamic SL on H1 data.
  - Minimum 1:2 risk-reward ratio  : TP = entry ± (SL_distance × 2).
  - 3.5% Supabase drawdown guard   : equity checked every 60 s; emergency
                                      close triggered if daily loss ≥ 3.5 %.
  - 5-minute signal freshness      : stale signals are skipped / cleaned.
  - Emergency kill-switch          : polls `emergency_commands` table in
                                      Supabase; executes KILL_ALL immediately.

Usage on VPS:
    python vps_agent.py            # run once (use run_vps_agent.bat for loop)

Environment variables (copy .env.template → .env and fill in):
    SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
    MT5_LOGIN_1, MT5_PASSWORD_1, MT5_SERVER_1   (repeat for accounts 2-5)
    MT5_PATH                                      (optional — full path to terminal64.exe)
    DAILY_LOSS_LIMIT_PCT    default 3.5
    RISK_PER_TRADE_PCT      default 1.0
    MT5_SYMBOL              default XAUUSD
    SIGNAL_INTERVAL_SECONDS default 60
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import MetaTrader5 as mt5
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client, Client

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "vps_agent.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("vps_agent")

# ─────────────────────────────────────────────────────────────────────────────
# Config — loaded from .env
# ─────────────────────────────────────────────────────────────────────────────
load_dotenv(Path(__file__).parent / ".env")

SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SYMBOL: str = os.getenv("MT5_SYMBOL", "XAUUSD")
DAILY_LOSS_LIMIT_PCT: float = float(os.getenv("DAILY_LOSS_LIMIT_PCT", "3.5"))
RISK_PER_TRADE_PCT: float = float(os.getenv("RISK_PER_TRADE_PCT", "1.0"))
SIGNAL_INTERVAL: int = int(os.getenv("SIGNAL_INTERVAL_SECONDS", "60"))
MT5_PATH: Optional[str] = os.getenv("MT5_PATH") or None  # e.g. C:\Program Files\MetaTrader 5\terminal64.exe

EMA_PERIOD = 50
ATR_PERIOD = 14
ATR_MULTIPLIER = 1.5
MIN_RR = 2.0
SIGNAL_TTL_MINUTES = 5
MAGIC = 234567
EQUITY_POLL_SECONDS = 60


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Account:
    index: int                       # 1-based slot number
    login: int
    password: str
    server: str
    balance: float = 0.0
    equity: float = 0.0
    daily_start_equity: float = 0.0
    connected: bool = False
    halted: bool = False             # True once daily drawdown limit hit


@dataclass
class Signal:
    direction: str                   # "BUY" | "SELL"
    entry: float
    stop_loss: float
    take_profit: float
    rr: float
    h4_ema: float
    h1_ema: float
    atr: float
    generated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_fresh(self) -> bool:
        age = (datetime.utcnow() - self.generated_at).total_seconds()
        return age < SIGNAL_TTL_MINUTES * 60

    @property
    def expires_at(self) -> datetime:
        return self.generated_at + timedelta(minutes=SIGNAL_TTL_MINUTES)


# ─────────────────────────────────────────────────────────────────────────────
# MT5 helpers  (all MT5 calls go through one shared terminal instance on VPS)
# ─────────────────────────────────────────────────────────────────────────────
_mt5_lock = threading.Lock()


def _init_mt5(account: Account) -> bool:
    """Initialise the MT5 terminal and log in to the given account."""
    kwargs: dict = {"login": account.login, "password": account.password, "server": account.server}
    if MT5_PATH:
        kwargs["path"] = MT5_PATH

    with _mt5_lock:
        if not mt5.initialize(**kwargs):
            log.error("MT5 init failed for account %s: %s", account.login, mt5.last_error())
            return False

        info = mt5.account_info()
        if info is None:
            log.error("Cannot get account info for login %s", account.login)
            mt5.shutdown()
            return False

        account.balance = info.balance
        account.equity = info.equity
        account.daily_start_equity = account.equity
        account.connected = True
        log.info("Connected → account %s | balance $%.2f | equity $%.2f",
                 account.login, account.balance, account.equity)
        return True


def _shutdown_mt5(account: Account) -> None:
    with _mt5_lock:
        mt5.shutdown()
        account.connected = False
    log.info("MT5 disconnected for account %s", account.login)


# ─────────────────────────────────────────────────────────────────────────────
# Trend & signal analysis
# ─────────────────────────────────────────────────────────────────────────────

def _candles(timeframe: int, count: int = 250) -> Optional[pd.DataFrame]:
    rates = mt5.copy_rates_from_pos(SYMBOL, timeframe, 0, count)
    if rates is None or len(rates) < EMA_PERIOD + 10:
        log.warning("Insufficient candle data for timeframe %s", timeframe)
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def _ema(df: pd.DataFrame, period: int = EMA_PERIOD) -> float:
    return float(df["close"].ewm(span=period, adjust=False).mean().iloc[-1])


def _atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> float:
    h, l, pc = df["high"], df["low"], df["close"].shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    val = tr.rolling(period).mean().iloc[-1]
    return float(val) if pd.notna(val) else 0.0


def analyse_and_generate_signal() -> Optional[Signal]:
    """
    Returns a Signal if H4+H1 50 EMA conditions are met, else None.
    Must be called while MT5 is initialised.
    """
    h4 = _candles(mt5.TIMEFRAME_H4)
    h1 = _candles(mt5.TIMEFRAME_H1)
    if h4 is None or h1 is None:
        return None

    h4_ema_val = _ema(h4)
    h1_ema_val = _ema(h1)
    h4_close = float(h4["close"].iloc[-1])
    h1_close = float(h1["close"].iloc[-1])

    h4_above = h4_close > h4_ema_val
    h1_above = h1_close > h1_ema_val

    if h4_above and h1_above:
        direction = "BUY"
    elif not h4_above and not h1_above:
        direction = "SELL"
    else:
        log.info("EMA filter: mixed trend — H4_above=%s H1_above=%s — no trade", h4_above, h1_above)
        return None

    atr_val = _atr(h1)
    if atr_val <= 0:
        log.warning("ATR returned 0 — skipping signal")
        return None

    sl_dist = atr_val * ATR_MULTIPLIER
    entry = h1_close

    if direction == "BUY":
        sl = entry - sl_dist
        tp = entry + sl_dist * MIN_RR
    else:
        sl = entry + sl_dist
        tp = entry - sl_dist * MIN_RR

    rr = abs(tp - entry) / abs(entry - sl) if abs(entry - sl) > 0 else 0

    if rr < MIN_RR:
        log.warning("R:R %.2f below minimum %.2f — skipping", rr, MIN_RR)
        return None

    log.info(
        "Signal → %s | entry=%.2f | SL=%.2f | TP=%.2f | R:R=%.2f | H4_EMA=%.2f | H1_EMA=%.2f | ATR=%.4f",
        direction, entry, sl, tp, rr, h4_ema_val, h1_ema_val, atr_val,
    )
    return Signal(
        direction=direction, entry=entry, stop_loss=sl, take_profit=tp,
        rr=rr, h4_ema=h4_ema_val, h1_ema=h1_ema_val, atr=atr_val,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Drawdown guard
# ─────────────────────────────────────────────────────────────────────────────

def _refresh_equity(account: Account) -> None:
    """Pull fresh equity from MT5 into the account object."""
    info = mt5.account_info()
    if info:
        account.equity = info.equity
        account.balance = info.balance


def check_drawdown(account: Account) -> bool:
    """
    Returns True if trading is allowed (within limit).
    Returns False and marks account.halted if daily loss ≥ DAILY_LOSS_LIMIT_PCT.
    """
    if account.daily_start_equity <= 0:
        return True

    _refresh_equity(account)
    loss_pct = ((account.daily_start_equity - account.equity) / account.daily_start_equity) * 100

    if loss_pct >= DAILY_LOSS_LIMIT_PCT:
        if not account.halted:
            log.error(
                "DRAWDOWN GUARD: account %s hit %.2f%% daily loss (limit %.2f%%) — halting",
                account.login, loss_pct, DAILY_LOSS_LIMIT_PCT,
            )
        account.halted = True
        return False

    if loss_pct >= DAILY_LOSS_LIMIT_PCT * 0.8:
        log.warning(
            "Drawdown WARNING: account %s at %.2f%% (limit %.2f%%)",
            account.login, loss_pct, DAILY_LOSS_LIMIT_PCT,
        )
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Lot sizing
# ─────────────────────────────────────────────────────────────────────────────

def calculate_lots(account: Account, sl_distance: float) -> float:
    """
    Dynamic lot size: risk RISK_PER_TRADE_PCT of equity across sl_distance.
    For XAUUSD: 1 lot = 100 oz; 1 USD/oz move = $100/lot → value per pip ≈ $1.
    """
    sym = mt5.symbol_info(SYMBOL)
    if sym is None:
        log.error("symbol_info returned None for %s", SYMBOL)
        return 0.0

    risk_usd = account.equity * (RISK_PER_TRADE_PCT / 100)

    # For Gold: 1 standard lot = 100 oz; point value depends on contract size
    # MT5 gives us trade_tick_value / trade_tick_size to compute $/point/lot
    if sym.trade_tick_size > 0:
        value_per_point_per_lot = sym.trade_tick_value / sym.trade_tick_size
    else:
        value_per_point_per_lot = 1.0  # fallback

    if sl_distance <= 0 or value_per_point_per_lot <= 0:
        return 0.0

    raw = risk_usd / (sl_distance * value_per_point_per_lot)

    # Snap to broker's lot step
    step = sym.volume_step if sym.volume_step > 0 else 0.01
    lots = round(round(raw / step) * step, 2)
    lots = max(sym.volume_min, min(sym.volume_max, lots))

    log.info("Lot size for account %s: %.2f (risk $%.2f over %.4f pts)",
             account.login, lots, risk_usd, sl_distance)
    return lots


# ─────────────────────────────────────────────────────────────────────────────
# Trade execution
# ─────────────────────────────────────────────────────────────────────────────

def execute_trade(account: Account, sig: Signal) -> Optional[int]:
    """
    Places a market order on the currently-initialised MT5 terminal.
    Returns the ticket number on success, None on failure.
    """
    if not account.connected or account.halted:
        return None

    if not check_drawdown(account):
        return None

    lots = calculate_lots(account, abs(sig.entry - sig.stop_loss))
    if lots <= 0:
        return None

    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None:
        log.error("No tick data for %s", SYMBOL)
        return None

    order_type = mt5.ORDER_TYPE_BUY if sig.direction == "BUY" else mt5.ORDER_TYPE_SELL
    price = tick.ask if sig.direction == "BUY" else tick.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": lots,
        "type": order_type,
        "price": price,
        "sl": sig.stop_loss,
        "tp": sig.take_profit,
        "deviation": 20,
        "magic": MAGIC,
        "comment": f"vps_agent {sig.direction}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result is None:
        log.error("order_send returned None for account %s: %s", account.login, mt5.last_error())
        return None

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        log.error("Order rejected for account %s: retcode=%s comment=%s",
                  account.login, result.retcode, result.comment)
        return None

    log.info("✅ Trade opened | account=%s | ticket=%s | %s %.2f lots @ %.2f | SL=%.2f TP=%.2f",
             account.login, result.order, sig.direction, lots, price, sig.stop_loss, sig.take_profit)
    return result.order


def emergency_close_all(account: Account) -> int:
    """Close every open position on the account. Returns closed count."""
    positions = mt5.positions_get() or []
    closed = 0
    for pos in positions:
        tick = mt5.symbol_info_tick(pos.symbol)
        if tick is None:
            continue
        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": close_type,
            "position": pos.ticket,
            "price": price,
            "deviation": 30,
            "magic": MAGIC,
            "comment": "emergency_close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(req)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            closed += 1
            log.warning("Emergency closed ticket #%s on account %s", pos.ticket, account.login)
        else:
            log.error("Failed to close ticket #%s: %s", pos.ticket, mt5.last_error())
    return closed


# ─────────────────────────────────────────────────────────────────────────────
# Supabase helpers
# ─────────────────────────────────────────────────────────────────────────────

def _supa() -> Optional[Client]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        log.error("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set in .env")
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def push_signal(db: Client, sig: Signal) -> None:
    """Upsert the current signal into `trading_signals`."""
    try:
        db.table("trading_signals").insert({
            "symbol": SYMBOL,
            "direction": sig.direction,
            "entry_price": round(sig.entry, 2),
            "stop_loss": round(sig.stop_loss, 2),
            "take_profit": round(sig.take_profit, 2),
            "risk_reward_ratio": round(sig.rr, 2),
            "h4_ema50": round(sig.h4_ema, 2),
            "h1_ema50": round(sig.h1_ema, 2),
            "atr_value": round(sig.atr, 4),
            "signal_time": sig.generated_at.isoformat(),
            "expires_at": sig.expires_at.isoformat(),
            "is_valid": True,
        }).execute()
    except Exception as exc:
        log.error("Failed to push signal to Supabase: %s", exc)


def expire_old_signals(db: Client) -> None:
    """Mark expired signals invalid."""
    try:
        db.table("trading_signals").update({"is_valid": False}).lt(
            "expires_at", datetime.utcnow().isoformat()
        ).eq("is_valid", True).execute()
    except Exception as exc:
        log.error("Failed to expire signals: %s", exc)


def check_emergency_command(db: Client) -> Optional[str]:
    """
    Returns the command_type string if a pending emergency command exists,
    and marks it executed. Returns None if no command pending.
    """
    try:
        res = (
            db.table("emergency_commands")
            .select("*")
            .eq("status", "pending")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not res.data:
            return None

        cmd = res.data[0]
        db.table("emergency_commands").update(
            {"status": "executed", "executed_at": datetime.utcnow().isoformat()}
        ).eq("id", cmd["id"]).execute()

        log.warning("Emergency command received: %s", cmd["command_type"])
        return cmd["command_type"]

    except Exception as exc:
        log.error("Error checking emergency commands: %s", exc)
        return None


def push_account_status(db: Client, account: Account) -> None:
    """Sync equity / daily P&L back to Supabase `trading_accounts`."""
    try:
        daily_pnl = account.equity - account.daily_start_equity
        db.table("trading_accounts").update({
            "balance": round(account.balance, 2),
            "equity": round(account.equity, 2),
            "daily_profit_loss": round(daily_pnl, 2),
            "connection_status": "connected" if account.connected else "disconnected",
            "last_sync": datetime.utcnow().isoformat(),
        }).eq("account_number", str(account.login)).execute()
    except Exception as exc:
        log.error("Failed to push account status for %s: %s", account.login, exc)


# ─────────────────────────────────────────────────────────────────────────────
# Account loader  (reads MT5_LOGIN_n / MT5_PASSWORD_n / MT5_SERVER_n from .env)
# ─────────────────────────────────────────────────────────────────────────────

def load_accounts() -> List[Account]:
    accounts: List[Account] = []
    for i in range(1, 6):  # slots 1 – 5
        login_str = os.getenv(f"MT5_LOGIN_{i}", "").strip()
        password = os.getenv(f"MT5_PASSWORD_{i}", "").strip()
        server = os.getenv(f"MT5_SERVER_{i}", "").strip()
        if login_str and password and server:
            accounts.append(Account(index=i, login=int(login_str), password=password, server=server))

    if not accounts:
        log.error("No MT5 accounts found. Set MT5_LOGIN_1, MT5_PASSWORD_1, MT5_SERVER_1 in .env")
    else:
        log.info("Loaded %d account(s): %s", len(accounts), [a.login for a in accounts])
    return accounts


# ─────────────────────────────────────────────────────────────────────────────
# Main agent loop
# ─────────────────────────────────────────────────────────────────────────────

class VPSAgent:
    def __init__(self) -> None:
        self.accounts: List[Account] = load_accounts()
        self.db: Optional[Client] = _supa()
        self._stop_event = threading.Event()
        self._emergency_stop = False
        self._equity_thread: Optional[threading.Thread] = None

        # Graceful shutdown on Ctrl-C / SIGTERM
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, *_) -> None:
        log.info("Shutdown signal received — stopping agent...")
        self._stop_event.set()

    # ── equity monitor (background thread) ────────────────────────────────────
    def _equity_monitor(self) -> None:
        log.info("Equity monitor started (polling every %ds)", EQUITY_POLL_SECONDS)
        while not self._stop_event.is_set() and not self._emergency_stop:
            time.sleep(EQUITY_POLL_SECONDS)
            for acc in self.accounts:
                if not acc.connected:
                    continue
                with _mt5_lock:
                    if not check_drawdown(acc):
                        log.error("Auto-halt: closing all positions on account %s", acc.login)
                        with _mt5_lock:
                            emergency_close_all(acc)
                if self.db:
                    push_account_status(self.db, acc)
        log.info("Equity monitor stopped")

    # ── connect one account ───────────────────────────────────────────────────
    def _connect(self, acc: Account) -> bool:
        for attempt in range(1, 4):
            log.info("Connecting account %s (attempt %d/3)...", acc.login, attempt)
            if _init_mt5(acc):
                return True
            time.sleep(15)
        log.error("Could not connect account %s after 3 attempts", acc.login)
        return False

    # ── single cycle ─────────────────────────────────────────────────────────
    def _cycle(self) -> None:
        """One full scan-and-execute cycle."""

        # Check Supabase for emergency commands
        if self.db:
            cmd = check_emergency_command(self.db)
            if cmd == "KILL_ALL":
                log.warning("KILL_ALL received — emergency closing all accounts")
                self._emergency_stop = True
                for acc in self.accounts:
                    if acc.connected:
                        with _mt5_lock:
                            _init_mt5(acc)  # ensure logged in for this account
                            emergency_close_all(acc)
                return
            expire_old_signals(self.db)

        # Iterate over each account, switch MT5 login, analyse, execute
        for acc in self.accounts:
            if self._emergency_stop or self._stop_event.is_set():
                break

            if acc.halted:
                log.info("Account %s is halted for today — skipping", acc.login)
                continue

            # (Re)connect if needed
            if not acc.connected:
                self._connect(acc)
            if not acc.connected:
                continue

            with _mt5_lock:
                # Switch active login
                if not mt5.initialize(
                    login=acc.login,
                    password=acc.password,
                    server=acc.server,
                    **({"path": MT5_PATH} if MT5_PATH else {}),
                ):
                    log.error("Re-init failed for account %s: %s", acc.login, mt5.last_error())
                    acc.connected = False
                    continue

                # Check drawdown before doing any analysis
                if not check_drawdown(acc):
                    emergency_close_all(acc)
                    continue

                # Generate signal
                sig = analyse_and_generate_signal()
                if sig is None:
                    log.info("Account %s — no signal this cycle", acc.login)
                    continue

                # Push signal to Supabase (first account wins; others reuse)
                if self.db and acc.index == self._first_connected_index():
                    push_signal(self.db, sig)

                # Execute
                execute_trade(acc, sig)

    def _first_connected_index(self) -> int:
        for acc in self.accounts:
            if acc.connected:
                return acc.index
        return 1

    # ── run ───────────────────────────────────────────────────────────────────
    def run(self) -> None:
        log.info("=" * 60)
        log.info("VPS Agent starting — symbol=%s | accounts=%d | drawdown_limit=%.1f%%",
                 SYMBOL, len(self.accounts), DAILY_LOSS_LIMIT_PCT)
        log.info("=" * 60)

        if not self.accounts:
            log.error("No accounts configured — exiting.")
            return

        if not self.db:
            log.warning("Supabase not configured — running in MT5-only mode (no remote sync)")

        # Initial connections
        for acc in self.accounts:
            self._connect(acc)

        # Start equity monitor thread
        self._equity_thread = threading.Thread(target=self._equity_monitor, daemon=True)
        self._equity_thread.start()

        # Main loop
        while not self._stop_event.is_set() and not self._emergency_stop:
            try:
                self._cycle()
            except Exception as exc:
                log.exception("Unhandled error in main cycle: %s", exc)

            # Wait for next interval (interruptible)
            self._stop_event.wait(timeout=SIGNAL_INTERVAL)

        # Cleanup
        log.info("Shutting down — disconnecting MT5...")
        for acc in self.accounts:
            if acc.connected:
                _shutdown_mt5(acc)

        log.info("VPS Agent stopped cleanly.")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    agent = VPSAgent()
    agent.run()
